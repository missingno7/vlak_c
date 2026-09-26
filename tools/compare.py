#!/usr/bin/env python3
"""Equivalence check: original VLAK.ASM (trace oracle) vs C reimplementation.

Both programs run under MS-DOS Player with the same SCENARIO.BIN; their
TRACE.BIN files (every hardware access with its virtual timestamp, plus a
final dump of the game state) must be byte-identical.

usage: compare.py [--seeds N] [--only NAME] [--keep]
"""

from __future__ import annotations

import argparse
import random
import shutil
import struct
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from dos_runner import run_dos  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
ORACLE = ROOT / "build/oracle/VLAK.COM"
CPORT = ROOT / "build/dos/VLAKTR.EXE"

UP, LEFT, RIGHT, DOWN = 0x4800, 0x4B00, 0x4D00, 0x5000
ARROWS = (UP, LEFT, RIGHT, DOWN)
ESC, F4, ENTER, BKSP, DEL = 0x011B, 0x3E00, 0x1C0D, 0x0E08, 0x5300
SPACE = 0x3920
SCAN = dict(zip("QWERTYUIOP", range(0x10, 0x1A)))
SCAN.update(zip("ASDFGHJKL", range(0x1E, 0x27)))
SCAN.update(zip("ZXCVBNM", range(0x2C, 0x33)))
STEP = 110  # ~ one game step (2 BIOS ticks) in virtual ms


def letter(ch: str) -> int:
    return (SCAN[ch.upper()] << 8) | ord(ch)


def word_keys(text: str) -> list[int]:
    return [letter(c) for c in text]


class Script:
    def __init__(self, limit: int):
        self.limit = limit
        self.keys: list[tuple[int, int]] = []

    def at(self, t: int, *keys: int) -> "Script":
        for i, k in enumerate(keys):
            self.keys.append((t + i, k))
        return self

    def binary(self) -> bytes:
        keys = sorted(self.keys, key=lambda k: k[0])
        out = struct.pack("<IH", self.limit, len(keys))
        for t, k in keys:
            out += struct.pack("<IH", t, k)
        return out


def password(scene: int) -> str:
    import re
    asm = (ROOT / "reference/upstream/SRC/VLAK.ASM").read_text(encoding="latin-1")
    rows = re.findall(r"(?m)^\s+db\s+'(\w)' XOR X,'(\w)' XOR X,'(\w)' XOR X,'(\w)' XOR X,'(\w)' XOR X", asm)
    assert len(rows) == 51
    return "".join(rows[scene - 1])


def fixed_scenarios() -> dict[str, Script]:
    s: dict[str, Script] = {}
    s["demo_long"] = Script(90_000)
    s["demo_esc"] = Script(60_000).at(4_000, ESC)
    s["card_ok_start_idle"] = Script(20_000).at(1_000, SPACE)
    s["scene1_crash"] = Script(30_000).at(500, SPACE).at(2_000, UP)
    s["scene1_crash_restart"] = (Script(40_000).at(500, SPACE).at(2_000, UP)
                                 .at(8_000, SPACE).at(9_000, RIGHT).at(9_500, DOWN))
    s["scene1_esc_back_to_demo"] = Script(40_000).at(500, SPACE).at(3_000, ESC).at(10_000, SPACE)
    s["password_escape"] = Script(30_000).at(500, SPACE).at(2_000, F4).at(4_000, ESC)
    s["password_edit"] = (Script(40_000).at(500, SPACE).at(2_000, F4)
                          .at(3_000, *word_keys("ab"), LEFT, BKSP, DEL, RIGHT, RIGHT, RIGHT,
                              RIGHT, RIGHT, letter("z"), 0x0231, ENTER))
    for n in (2, 17, 51):
        s[f"password_scene{n}"] = (Script(40_000).at(500, SPACE).at(2_000, F4)
                                   .at(3_000, *word_keys(password(n)), ENTER)
                                   .at(8_000, RIGHT).at(9_000, DOWN).at(10_000, LEFT))
    sols = load_solutions()
    if sols:
        for name, first, last in (("campaign_1_10", 1, 10), ("campaign_11_25", 11, 25),
                                  ("campaign_26_40", 26, 40), ("campaign_41_51_winner", 41, 51)):
            sc, done = campaign(first, last, sols)
            sc.expect_fanfares = done
            s[name] = sc
    tour = Script(0)
    t = 1_000
    tour.at(t, SPACE)
    for n in range(1, 52):
        t += 1_500
        tour.at(t, F4)
        tour.at(t + 300, *word_keys(password(n)), ENTER)
    tour.limit = t + 3_000
    s["all_scene_passwords"] = tour
    s["key_flood"] = Script(20_000).at(500, SPACE).at(2_000, *([RIGHT, DOWN, LEFT, UP] * 10))
    return s


def random_script(seed: int) -> Script:
    rng = random.Random(seed)
    sc = Script(rng.choice((60_000, 120_000, 240_000)))
    t = rng.randint(100, 3_000)
    sc.at(t, SPACE)
    if rng.random() < 0.6:
        t += rng.randint(200, 2_000)
        sc.at(t, F4, *word_keys(password(rng.randint(1, 51))), ENTER)
    while t < sc.limit:
        t += int(rng.expovariate(1 / (STEP * rng.choice((1, 3, 6)))))
        r = rng.random()
        if r < 0.85:
            k = rng.choice(ARROWS)
        elif r < 0.90:
            k = rng.choice((SPACE, ENTER, letter("a"), 0x0231))
        elif r < 0.95:
            k = F4
        elif r < 0.985:
            k = rng.choice((BKSP, DEL, letter(rng.choice("QWERTYUIOPASDFGHJKLZXCVBNM"))))
        else:
            k = ESC
        sc.at(t, k)
    return sc


KEY_OF = {"L": LEFT, "U": UP, "R": RIGHT, "D": DOWN}


class Clock:
    """Timing model of TestTime under the trace backend (1 ms per call,
    BIOS tick = 55 ms, step when ticks - LastTime >= 2)."""

    def __init__(self) -> None:
        self.vms = 0
        self.last = 0

    def test_time(self) -> bool:
        self.vms += 1
        t = self.vms // 55
        if (t - self.last) & 0xFFFF >= 2:
            self.last = t
            return True
        return False

    def run_until(self, t: int) -> None:
        while self.vms < t:
            self.test_time()

    def next_step(self) -> None:
        while not self.test_time():
            pass


def play(sc: Script, clk: Clock, moves: str) -> None:
    """Scene just initialised at clk.vms (Faze = 0): schedule keys for MOVES."""
    faze = 0
    direction = None
    for d in moves:
        while True:
            clk.next_step()
            faze = (faze + 1) % 3
            if faze == 0:
                break
        if d != direction:
            sc.at(clk.vms - 100, KEY_OF[d])
            direction = d


def load_solutions() -> dict[int, str]:
    path = ROOT / "tests/solutions.txt"
    if not path.exists():
        return {}
    out = {}
    for line in path.read_text().splitlines():
        n, s = line.split()
        out[int(n)] = s
    return out


def campaign(first: int, last: int, sols: dict[int, str], limit_pad: int = 5_000) -> tuple[Script, int]:
    """Play scenes FIRST..LAST in a row; unsolved scenes are skipped with F4."""
    sc = Script(0)
    clk = Clock()
    clk.run_until(1_000)
    sc.at(1_000, SPACE)                 # demo -> scene 1
    scene = 1
    completed = 0

    def jump(target: int) -> None:
        clk.next_step()                 # Start5 peeks only on a step
        sc.at(clk.vms, F4)
        t = clk.vms + 10
        sc.at(t, *word_keys(password(target)), ENTER)
        clk.run_until(t + 5)            # Heslo consumes one key per 1 ms loop

    if first != 1:
        jump(first)
        scene = first
    while scene <= last:
        if scene not in sols:
            nxt = next((n for n in range(scene + 1, last + 1) if n in sols), None)
            if nxt is None:
                break
            jump(nxt)
            scene = nxt
            continue
        play(sc, clk, sols[scene])
        completed += 1
        clk.vms += 250 * 4 + 12 * 60    # fanfare + ClosScen
        key_t = clk.vms + 300
        sc.at(key_t, SPACE)             # "SCENA n heslo XXXXX" -> any key
        clk.vms = key_t + 12 * 60       # OpenScen
        scene += 1
        if scene > MAXSCEN:
            break
    sc.limit = clk.vms + limit_pad
    return sc, completed


MAXSCEN = 51


def run(program: Path, script: Script, workdir: Path) -> bytes:
    workdir.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(program, workdir / program.name)
    (workdir / "SCENARIO.BIN").write_bytes(script.binary())
    trace = workdir / "TRACE.BIN"
    if trace.exists():
        trace.unlink()
    run_dos(workdir / program.name, [], workdir, check=False, timeout=1800)
    return trace.read_bytes() if trace.exists() else b""


NAMES = {1: "obr", 2: "tit", 3: "chr", 4: "snd", 5: "off", 6: "mode", 7: "print",
         8: "exit", 9: "key", 0xFE: "end"}


def records(trace: bytes) -> list[tuple]:
    out = []
    i = 0
    while i + 9 <= len(trace):
        typ, t, a, b = struct.unpack_from("<BIHH", trace, i)
        out.append((typ, t, a, b))
        i += 9
        if typ == 0xFE:
            break
    return out


def fmt(r: tuple) -> str:
    typ, t, a, b = r
    return f"t={t:>7} {NAMES.get(typ, typ):>5} a={a:04X} b={b:04X}"


def describe(a: bytes, b: bytes) -> str:
    ra, rb = records(a), records(b)
    for i, (x, y) in enumerate(zip(ra, rb)):
        if x != y:
            lines = [f"first differing event #{i}:"]
            for j in range(max(0, i - 4), min(i + 4, len(ra), len(rb))):
                mark = ">>" if j == i else "  "
                lines.append(f"{mark} asm {fmt(ra[j])} | c {fmt(rb[j])}")
            return "\n".join(lines)
    if len(ra) != len(rb):
        return f"event count differs: asm {len(ra)} c {len(rb)}"
    end = 9 * len(ra)
    for i in range(end, min(len(a), len(b))):
        if a[i] != b[i]:
            return f"final state differs at dump byte {i - end}"
    return f"trace length differs: asm {len(a)} c {len(b)}"


def check(name: str, script: Script, base: Path) -> tuple[str, bool, str]:
    ta = run(ORACLE, script, base / name / "asm")
    tc = run(CPORT, script, base / name / "c")
    events = len(records(ta))
    if not ta:
        return name, False, "oracle produced no trace"
    want = getattr(script, "expect_fanfares", None)
    if want is not None:
        got = sum(1 for r in records(ta) if r[0] == 4 and r[2] == 2200)
        if got != want:
            return name, False, f"script desynchronised: {got} scenes completed, expected {want}"
    if ta == tc:
        kinds = {}
        for r in records(ta):
            kinds[NAMES.get(r[0], r[0])] = kinds.get(NAMES.get(r[0], r[0]), 0) + 1
        return name, True, f"{events} events, {len(ta)} bytes identical {kinds}"
    return name, False, describe(ta, tc)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", type=int, default=20)
    ap.add_argument("--only")
    ap.add_argument("--keep", action="store_true")
    ap.add_argument("--jobs", type=int, default=8)
    args = ap.parse_args()

    scenarios = fixed_scenarios()
    for seed in range(args.seeds):
        scenarios[f"random{seed:03d}"] = random_script(seed)
    if args.only:
        scenarios = {k: v for k, v in scenarios.items() if args.only in k}

    base = Path(tempfile.mkdtemp(prefix="vlakcmp_"))
    failures = 0
    with ThreadPoolExecutor(args.jobs) as pool:
        for name, ok, info in pool.map(lambda kv: check(kv[0], kv[1], base), scenarios.items()):
            print(f"{'PASS' if ok else 'FAIL'} {name}: {info}", flush=True)
            failures += not ok
    if args.keep or failures:
        print(f"work dir: {base}")
    else:
        shutil.rmtree(base, ignore_errors=True)
    print(f"{len(scenarios) - failures}/{len(scenarios)} scenarios identical")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
