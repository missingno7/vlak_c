#!/usr/bin/env python3
"""Find move sequences that complete Vlak scenes (used to drive the
equivalence check through scene transitions and the winner screen).

Depth-first search over the order in which items are collected. Paths
between targets come from a time-aware BFS (a body segment k of a train of
length n frees its cell for arrivals at step >= n - k + 1); every candidate
path is then replayed exactly with the original movement rules."""

from __future__ import annotations

import sys
import time
from collections import deque
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
W, H = 20, 12
LO1, LO4, VRA, VECI = 1, 4, 24, 102
DIRS = (("L", -1, 0), ("U", 0, -1), ("R", 1, 0), ("D", 0, 1))


def scenes() -> list[list[int]]:
    sys.path.insert(0, str(ROOT / "tools"))
    from gen_dos_data import PRISTINE, listing_offsets
    off = listing_offsets(PRISTINE / "VLAK.LST")
    com = (PRISTINE / "VLAK.COM").read_bytes()
    base = off["Sceny"] - 0x100
    return [list(com[base + 240 * n:base + 240 * (n + 1)]) for n in range(52)]


class Level:
    def __init__(self, scene: list[int]):
        self.free = set()
        self.items = set()
        for i, v in enumerate(scene):
            p = (i % W, i // W)
            if LO1 <= v <= LO4:
                self.head = p
                self.free.add(p)
            elif v == VRA:
                self.gate = p
            elif v >= VECI:
                self.items.add(p)
                self.free.add(p)
            elif v == 0:
                self.free.add(p)


def step(level: Level, body: tuple, items: frozenset, d: str):
    """Exact original rules. Returns (body, items, done) or None on crash."""
    dx, dy = {"L": (-1, 0), "U": (0, -1), "R": (1, 0), "D": (0, 1)}[d]
    t = (body[0][0] + dx, body[0][1] + dy)
    if t == level.gate:
        return (body, items, True) if not items else None
    if t not in level.free or t in body:
        return None
    if t in items:
        return (t,) + body, items - {t}, False
    return (t,) + body[:-1], items, False


def paths(level: Level, body: tuple, items: frozenset, goals: set):
    """Time-aware BFS from the head; other items are obstacles.
    Yields (goal, path) in order of distance."""
    n = len(body)
    free_at = {c: n - k + 1 for k, c in enumerate(body)}
    start = body[0]
    prev = {start: None}
    dist = {start: 0}
    q = deque([start])
    while q:
        c = q.popleft()
        s = dist[c] + 1
        for d, dx, dy in DIRS:
            t = (c[0] + dx, c[1] + dy)
            if t in prev:
                continue
            if t in goals:
                prev[t] = (c, d)
                path = []
                x = t
                while prev[x] is not None:
                    x, dd = prev[x]
                    path.append(dd)
                yield t, "".join(reversed(path))
                continue
            if t not in level.free or t in items:
                continue
            if s < free_at.get(t, 0):
                continue
            prev[t] = (c, d)
            dist[t] = s
            q.append(t)


def reachable_ok(level: Level, body: tuple, items: frozenset) -> bool:
    """Cheap prune: every item and the gate must lie in the head's region
    (body except the tail counted as walls)."""
    walls = set(body[:-1])
    seen = {body[0]}
    q = deque([body[0]])
    while q:
        c = q.popleft()
        for _, dx, dy in DIRS:
            t = (c[0] + dx, c[1] + dy)
            if t in seen or t in walls:
                continue
            if t == level.gate or t in level.free:
                seen.add(t)
                if t != level.gate:
                    q.append(t)
    return level.gate in seen and all(i in seen for i in items)


def solve(scene: list[int], budget: float = 30.0, width: int = 4) -> str | None:
    level = Level(scene)
    deadline = time.time() + budget
    visited = set()

    def dfs(body: tuple, items: frozenset, moves: str) -> str | None:
        if time.time() > deadline:
            return None
        key = (body, items)
        if key in visited:
            return None
        visited.add(key)
        goals = set(items) if items else {level.gate}
        tried = 0
        for _goal, path in paths(level, body, items, goals):
            b, it, done = body, items, False
            for d in path:
                r = step(level, b, it, d)
                if r is None:
                    break
                b, it, done = r
            else:
                if done:
                    return moves + path
                if reachable_ok(level, b, it):
                    found = dfs(b, it, moves + path)
                    if found:
                        return found
            tried += 1
            if tried >= width:
                break
        return None

    sys.setrecursionlimit(10000)
    return dfs((level.head,), frozenset(level.items), "")


def verify(scene: list[int], moves: str) -> bool:
    level = Level(scene)
    body, items = (level.head,), frozenset(level.items)
    for i, d in enumerate(moves):
        r = step(level, body, items, d)
        if r is None:
            return False
        body, items, done = r
        if done:
            return i == len(moves) - 1
    return False


def main() -> int:
    budget = float(sys.argv[1]) if len(sys.argv) > 1 else 30.0
    path = ROOT / "tests/solutions.txt"
    out: dict[int, str] = {}
    if path.exists():
        for line in path.read_text().splitlines():
            n, s = line.split()
            out[int(n)] = s
    all_scenes = scenes()
    for n in range(1, 52):
        if n in out and verify(all_scenes[n], out[n]):
            continue
        t = time.time()
        sol = None
        for width in (2, 3, 5, 8):
            sol = solve(all_scenes[n], budget / 4, width)
            if sol:
                break
        ok = bool(sol) and verify(all_scenes[n], sol)
        print(f"scene {n:2d}: {len(sol) if ok else '-':>4} moves  {time.time() - t:5.1f}s", flush=True)
        if ok:
            out[n] = sol
            path.write_text("".join(f"{k} {s}\n" for k, s in sorted(out.items())))
    print(f"{len(out)}/51 solved -> {path.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
