#!/usr/bin/env python3
"""Build the DOS C reimplementation with Turbo C 2.0 (compact model).

  build/dos/VLAK.EXE    - the game (real EGA / PC speaker / keyboard)
  build/dos/VLAKTR.EXE  - same game logic linked with the trace backend
"""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from dos_runner import TC_DIR, run_dos  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "dos"
OUT = ROOT / "build/dos"
TCC_FLAGS = ["-c", "-mc", "-1-", "-f-", "-N-", "-O", "-w"]
CRLF = bytes([13, 10])
LF = bytes([10])


def tcc(name: str) -> None:
    proc = run_dos(TC_DIR / "TCC.EXE", [*TCC_FLAGS, f"{name}.C"], OUT, check=False)
    failed = re.search(r"(?m)^(Error|Fatal) \S+ \d+:|\*\*\* \d+ errors", proc.stdout)
    if proc.returncode != 0 or failed or not (OUT / f"{name}.OBJ").exists():
        raise RuntimeError(f"TCC {name}.C failed:\n{proc.stdout}\n{proc.stderr}")
    for line in proc.stdout.splitlines():
        if re.match(r"Warning \S+ \d+:", line) and "Restarting compile" not in line:
            print(line)


def tlink(exe: str, objs: list[str]) -> None:
    for f in ("C0C.OBJ", "CC.LIB"):
        shutil.copyfile(TC_DIR / f, OUT / f)
    rsp = exe.replace(".EXE", ".RSP")
    line = f"/c /x C0C.OBJ {' '.join(objs)},{exe},,CC.LIB"
    (OUT / rsp).write_bytes(line.encode() + CRLF)
    proc = run_dos(TC_DIR / "TLINK.EXE", [f"@{rsp}"], OUT, check=False)
    if proc.returncode != 0 or not (OUT / exe).exists() or "Error:" in proc.stdout:
        raise RuntimeError(f"TLINK {exe} failed:\n{proc.stdout}\n{proc.stderr}")


def main() -> int:
    subprocess.run([sys.executable, str(ROOT / "tools/gen_dos_data.py")], check=True)
    OUT.mkdir(parents=True, exist_ok=True)
    for f in OUT.glob("*"):
        f.unlink()
    for f in SRC.glob("*.[CH]"):
        data = f.read_bytes().replace(CRLF, LF).replace(LF, CRLF)
        (OUT / f.name).write_bytes(data)
    for name in ("VLAK", "VLAKDATA", "HW", "HWTRACE"):
        tcc(name)
    tlink("VLAK.EXE", ["VLAK.OBJ", "VLAKDATA.OBJ", "HW.OBJ"])
    tlink("VLAKTR.EXE", ["VLAK.OBJ", "VLAKDATA.OBJ", "HWTRACE.OBJ"])
    for exe in ("VLAK.EXE", "VLAKTR.EXE"):
        print(f"built build/dos/{exe} ({(OUT / exe).stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
