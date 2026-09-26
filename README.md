# vlak_c — VLAK.COM reimplemented in C for DOS

A C reimplementation of Miroslav Němeček's *Vlak* (`reference/upstream`, 1993,
8086 assembler) that runs under DOS exactly like the original: EGA mode 0Dh,
PC speaker, BIOS keyboard, same timing loops.

## Layout

| Path | What |
|---|---|
| `dos/VLAK.C` | Game logic; control flow mirrors `VLAK.ASM` labels (`Start2`, `Start4`, `Heslo`, ...) |
| `dos/HW.C` | Real hardware layer (inline asm): EGA planes, INT 10h text, speaker, `CekInit`/`Cekej`, INT 16h |
| `dos/HWTRACE.C` | Trace hardware layer used only for the equivalence proof |
| `dos/VLAKDATA.C` | Generated: scenes, passwords, texts, graphics (`tools/gen_dos_data.py`) |
| `tools/build_dos.py` | Builds `build/dos/VLAK.EXE` (game) and `VLAKTR.EXE` (trace) with Turbo C 2.0 |
| `tools/make_oracle.py` | Builds `build/oracle/VLAK.COM`: pristine ASM with only its hardware boundary logged |
| `tools/compare.py` | Runs both on the same key scripts and byte-compares the traces |
| `tools/solver.py` | Finds scene solutions (`tests/solutions.txt`) so scripts can complete levels |
| `build/original/VLAK.COM` | The original game assembled from upstream (A.BAT layout), for side-by-side play |

## Build & run

Needs Python, MS-DOS Player (`C:\tools\nmlgcdos\msdos.exe`), TASM 2.01 and
Turbo C 2.0 at the paths in `tools/dos_runner.py`.

```
python tools/dos_runner.py build/pristine   # pristine upstream build (needs VLAK.ASM/SCENY.ASM copied there)
python tools/build_dos.py                   # build/dos/VLAK.EXE
```

Run `build/dos/VLAK.EXE` in DOS / DOSBox (machine=ega or vga).

## Equivalence proof

`python tools/compare.py --seeds 30`

The original `VLAK.ASM` is kept untouched except where it touches hardware:
`int 10h/16h/21h/20h`, the 0:046Ch tick read and the procedures `DispObr`,
`DispTit`, `SetSound`, `SoundOff`, `CekInit` and `Cekej` are replaced by
routines that log every call with a virtual timestamp. `HWTRACE.C` implements
the same boundary for the C game. Both use the same deterministic time model:
1 ms per `Cekej` unit, a BIOS tick every 55 ms, and scripted keys fed into a
15-key BIOS-style buffer. Each run ends with a dump of the game state (`Pole`,
`AktScen`, `MapVlak` and all variables).

Everything visible or audible passes through this boundary. So identical
traces mean identical screens, sounds and timing for that input.

Current suite: 47 scenarios, all byte-identical:
- demo, ESC and the farewell text
- crash and restart, ESC back to the demo
- password entry and editing, all 51 passwords
- level campaigns through fanfare, wall close/open and the winner screen
- 30 random fuzz sessions of up to 4 minutes

Faithfully reproduced quirks of the original:
- The move sound counter is set from byte lengths but steps through words, so
  it plays 6 notes. The item sound plays 36 words, and 18 of them are live game
  variables (`Smer`, `Skore`, `MapVlak`, ...) read from memory.
- The crash noise uses the program's own code bytes at `Start` as random data
  (`StartCode`).
- The score is shown ×10 (a literal "0" is appended) and survives restarts.
- An invalid password returns straight into the move logic (`Start60`).

`HW.C` itself is not covered by the trace. It was checked visually against
the original in DOSBox (`tools/dosbox_shot.ps1`).

`attic/` holds the earlier headless prototype and is not used.
