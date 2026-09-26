"""Run DOS tools under MS-DOS Player with a clean, reproducible environment."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

PLAYER = Path(os.environ.get("VLAK_MSDOS_PLAYER", r"C:\tools\nmlgcdos\msdos.exe"))
TASM_DIR = Path(r"C:\tools\tasm-2.01\files\disk01\expanded\TASM")
TC_DIR = Path(r"C:\tools\borland-turbo-c-2.00-empires")


def run_dos(program: Path | str, args: list[str], cwd: Path, tool_dir: Path | None = None,
            check: bool = True, timeout: float = 600) -> subprocess.CompletedProcess:
    program = Path(program)
    tool_dir = tool_dir or program.parent
    env = {
        "MSDOS_PATH": str(tool_dir),
        "PATH": str(tool_dir),
        "MSDOS_TEMP": str(cwd),
        "TEMP": str(cwd),
        "TMP": str(cwd),
        "SYSTEMROOT": os.environ.get("SYSTEMROOT", r"C:\Windows"),
    }
    cmd = [str(PLAYER), "-e", "-v5.00", str(program), *args]
    proc = subprocess.run(cmd, cwd=cwd, env=env, capture_output=True, text=True,
                          errors="replace", timeout=timeout)
    if check and proc.returncode != 0:
        raise RuntimeError(f"{' '.join(cmd)} failed ({proc.returncode}):\n{proc.stdout}\n{proc.stderr}")
    return proc


def tasm_com(src_dir: Path, name: str = "VLAK") -> Path:
    """Assemble and link NAME.ASM to a .COM exactly like upstream A.BAT."""
    run_dos(TASM_DIR / "TASM.EXE", ["/z/zi", f"{name}.ASM,{name}.OBJ"], src_dir)
    run_dos(TASM_DIR / "TLINK.EXE", ["/t/l/v/s/m", f"{name}.OBJ,{name}.COM,{name}.MAP"], src_dir)
    return src_dir / f"{name}.COM"


if __name__ == "__main__":
    import sys
    print(tasm_com(Path(sys.argv[1])))
