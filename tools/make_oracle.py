#!/usr/bin/env python3
"""Build the trace oracle: pristine VLAK.ASM with only its hardware boundary
replaced by logging routines (same semantics as dos/HWTRACE.C).

Edits (everything else is the untouched upstream source):
  * Start: first instruction preceded by `call OInit` (loads SCENARIO.BIN)
  * `int 10h` / `int 16h` / `int 21h` -> calls to logging emulations
  * `int 20h` -> jump to OExit
  * BIOS tick read at 0:046Ch in TestTime -> `call OTicks`
  * crash sound reads code bytes at Start: redirected to ONoise, a copy of the
    pristine bytes (the edit above would otherwise shift them)
  * procedures DispObr, DispTit, SetSound, SoundOff, CekInit, Cekej replaced
"""

from __future__ import annotations

import re
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from dos_runner import tasm_com  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
UPSTREAM = ROOT / "reference/upstream/SRC"
PRISTINE_COM = ROOT / "build/pristine/VLAK.COM"
OUT = ROOT / "build/oracle"

ROUTINES = r"""
; ======================= oracle (not part of the game) =======================

OInit    PROC      NEAR
         push      ax
         push      bx
         push      cx
         push      dx
         mov       dx,offset OInName
         mov       ax,3d00h
         int       21h
         jc        OFail
         mov       bx,ax
         mov       dx,offset OHdr
         mov       cx,6
         mov       ah,3fh
         int       21h
         mov       ax,word ptr ds:[OHdr]
         mov       ds:[OLimLo],ax
         mov       ax,word ptr ds:[OHdr+2]
         mov       ds:[OLimHi],ax
         mov       ax,word ptr ds:[OHdr+4]
         cmp       ax,OMAXKEYS
         ja        OFail
         mov       ds:[OKeyCnt],ax
         mov       cx,6
         mul       cx
         mov       cx,ax
         mov       dx,offset OKeys
         mov       ah,3fh
         int       21h
         mov       ah,3eh
         int       21h
         mov       dx,offset OOutName
         xor       cx,cx
         mov       ah,3ch
         int       21h
         jc        OFail
         mov       ds:[OOutH],ax
         pop       dx
         pop       cx
         pop       bx
         pop       ax
         ret
OInit    ENDP

OFail:   mov       ax,4c02h
         int       21h

; ------ AL=type, CX=a, DX=b
OEmit    PROC      NEAR
         push      ax
         push      di
         mov       di,ds:[OBufLen]
         mov       byte ptr ds:[OBuf+di],al
         mov       ax,ds:[OVmsLo]
         mov       word ptr ds:[OBuf+di+1],ax
         mov       ax,ds:[OVmsHi]
         mov       word ptr ds:[OBuf+di+3],ax
         mov       word ptr ds:[OBuf+di+5],cx
         mov       word ptr ds:[OBuf+di+7],dx
         add       di,9
         mov       ds:[OBufLen],di
         cmp       di,504
         jb        OEmit9
         call      OFlush
OEmit9:  pop       di
         pop       ax
         ret
OEmit    ENDP

OFlush   PROC      NEAR
         push      ax
         push      bx
         push      cx
         push      dx
         mov       bx,ds:[OOutH]
         mov       cx,ds:[OBufLen]
         mov       dx,offset OBuf
         mov       ah,40h
         int       21h
         mov       word ptr ds:[OBufLen],0
         pop       dx
         pop       cx
         pop       bx
         pop       ax
         ret
OFlush   ENDP

; ------ DX=address, CX=length
OWrite   PROC      NEAR
         mov       bx,ds:[OOutH]
         mov       ah,40h
         int       21h
         ret
OWrite   ENDP

OExit:   mov       al,8
         xor       cx,cx
         xor       dx,dx
         call      OEmit
OFinish: mov       al,0feh
         xor       cx,cx
         xor       dx,dx
         call      OEmit
         call      OFlush
         mov       dx,offset Pole
         mov       cx,241
         call      OWrite
         mov       dx,offset MapVlak
         mov       cx,720
         call      OWrite
         mov       dx,offset Smer
         mov       cx,2
         call      OWrite
         mov       dx,offset Faze
         mov       cx,1
         call      OWrite
         mov       dx,offset CitVeci
         mov       cx,2
         call      OWrite
         mov       dx,offset PozVrat
         mov       cx,2
         call      OWrite
         mov       dx,offset Skore
         mov       cx,2
         call      OWrite
         mov       dx,offset Demon
         mov       cx,1
         call      OWrite
         mov       dx,offset CitTit
         mov       cx,1
         call      OWrite
         mov       dx,offset CitVyb
         mov       cx,2
         call      OWrite
         mov       dx,offset CitSound
         mov       cx,2
         call      OWrite
         mov       ax,ds:[AdrSound]
         or        ax,ax
         jnz       OFin2
         mov       ax,0ffffh
         jmp       short OFin3
OFin2:   sub       ax,offset TabSLok
OFin3:   mov       ds:[OTmp],ax
         mov       dx,offset OTmp
         mov       cx,2
         call      OWrite
         mov       dx,offset LastTime
         mov       cx,2
         call      OWrite
         mov       bx,ds:[OOutH]
         mov       ah,3eh
         int       21h
         mov       ax,4c00h
         int       21h

; ------ advance virtual time by 1 ms
OTick1   PROC      NEAR
         add       word ptr ds:[OVmsLo],1
         adc       word ptr ds:[OVmsHi],0
         inc       word ptr ds:[OSub]
         cmp       word ptr ds:[OSub],55
         jb        OTick2
         mov       word ptr ds:[OSub],0
         inc       word ptr ds:[OTicksW]
OTick2:  push      ax
         mov       ax,ds:[OVmsHi]
         cmp       ax,ds:[OLimHi]
         ja        OTickE
         jb        OTick3
         mov       ax,ds:[OVmsLo]
         cmp       ax,ds:[OLimLo]
         jae       OTickE
OTick3:  pop       ax
         ret
OTickE:  jmp       OFinish
OTick1   ENDP

OTicks   PROC      NEAR
         mov       ax,ds:[OTicksW]
         ret
OTicks   ENDP

; ------ move due scripted keys into the 15-key buffer
ODeliver PROC      NEAR
         push      ax
         push      bx
         push      si
ODel1:   mov       si,ds:[OKeyIdx]
         cmp       si,ds:[OKeyCnt]
         jae       ODel9
         mov       ax,6
         mul       si
         mov       si,ax
         mov       ax,word ptr ds:[OKeys+si+2]
         cmp       ax,ds:[OVmsHi]
         ja        ODel9
         jb        ODel2
         mov       ax,word ptr ds:[OKeys+si]
         cmp       ax,ds:[OVmsLo]
         ja        ODel9
ODel2:   cmp       byte ptr ds:[OKCnt],15
         jae       ODel3
         mov       al,ds:[OKHead]
         add       al,ds:[OKCnt]
         cmp       al,15
         jb        ODel25
         sub       al,15
ODel25:  mov       bl,al
         mov       bh,0
         shl       bx,1
         mov       ax,word ptr ds:[OKeys+si+4]
         mov       word ptr ds:[OKBuf+bx],ax
         inc       byte ptr ds:[OKCnt]
ODel3:   inc       word ptr ds:[OKeyIdx]
         jmp       ODel1
ODel9:   pop       si
         pop       bx
         pop       ax
         ret
ODeliver ENDP

; ------ INT 16h emulation (AH=0 read, AH=1 peek with ZF)
OInt16   PROC      NEAR
         push      bx
         push      cx
         push      dx
         call      ODeliver
         cmp       ah,1
         je        OI16P
OI16R:   cmp       byte ptr ds:[OKCnt],0
         jne       OI16H
         mov       bx,ds:[OKeyIdx]
         cmp       bx,ds:[OKeyCnt]
         jb        OI16W
         jmp       OFinish
OI16W:   call      OTick1
         call      ODeliver
         jmp       OI16R
OI16H:   mov       bl,ds:[OKHead]
         mov       bh,0
         shl       bx,1
         mov       ax,word ptr ds:[OKBuf+bx]
         inc       byte ptr ds:[OKHead]
         cmp       byte ptr ds:[OKHead],15
         jb        OI16H2
         mov       byte ptr ds:[OKHead],0
OI16H2:  dec       byte ptr ds:[OKCnt]
         push      ax
         mov       cx,ax
         xor       dx,dx
         mov       al,9
         call      OEmit
         pop       ax
         jmp       short OI16X
OI16P:   cmp       byte ptr ds:[OKCnt],0
         je        OI16Z
         mov       bl,ds:[OKHead]
         mov       bh,0
         shl       bx,1
         mov       ax,word ptr ds:[OKBuf+bx]
OI16Z:   cmp       byte ptr ds:[OKCnt],0
OI16X:   pop       dx
         pop       cx
         pop       bx
         ret
OInt16   ENDP

; ------ INT 10h emulation
OInt10   PROC      NEAR
         cmp       ah,12h
         jne       OI10a
         mov       bx,0003h
         ret
OI10a:   cmp       ah,0
         jne       OI10b
         push      ax
         push      cx
         push      dx
         mov       cl,al
         xor       ch,ch
         xor       dx,dx
         mov       al,6
         call      OEmit
         pop       dx
         pop       cx
         pop       ax
         ret
OI10b:   cmp       ah,2
         jne       OI10c
         mov       ds:[OCur],dx
         ret
OI10c:   cmp       ah,9
         jne       OI10d
         push      ax
         push      cx
         push      dx
         mov       ah,bl
         mov       cx,ax
         mov       dx,ds:[OCur]
         mov       al,3
         call      OEmit
         pop       dx
         pop       cx
         pop       ax
OI10d:   ret
OInt10   ENDP

; ------ INT 21h emulation (only AH=9 is used by the game)
OInt21   PROC      NEAR
         push      ax
         push      cx
         push      dx
         mov       cx,dx
         cmp       dx,offset CardTxt
         jne       OI21a
         mov       cx,1
OI21a:   cmp       dx,offset UvTxt
         jne       OI21b
         mov       cx,2
OI21b:   xor       dx,dx
         mov       al,7
         call      OEmit
         pop       dx
         pop       cx
         pop       ax
         ret
OInt21   ENDP
"""

DATA = r"""
OMAXKEYS EQU       2000
OInName  db        'SCENARIO.BIN',0
OOutName db        'TRACE.BIN',0
OOutH    dw        0
OHdr     db        6 dup(0)
OLimLo   dw        0
OLimHi   dw        0
OVmsLo   dw        0
OVmsHi   dw        0
OSub     dw        0
OTicksW  dw        0
OCur     dw        0
OTmp     dw        0
OKeyCnt  dw        0
OKeyIdx  dw        0
OKHead   db        0
OKCnt    db        0
OKBuf    dw        15 dup(0)
OBufLen  dw        0
OBuf     db        512 dup(0)
OKeys    db        6*OMAXKEYS dup(0)
"""

PROCS = {
    "DispObr": """
         push      ax
         push      cx
         push      dx
         mov       cl,al
         xor       ch,ch
         mov       al,1
         call      OEmit
         pop       dx
         pop       cx
         pop       ax
         ret""",
    "DispTit": """
         push      ax
         push      cx
         push      dx
         mov       cl,ds:[CitTit]
         xor       ch,ch
         xor       dx,dx
         mov       al,2
         call      OEmit
         pop       dx
         pop       cx
         pop       ax
         ret""",
    "SetSound": """
         push      ax
         push      cx
         push      dx
         mov       cx,ax
         xor       dx,dx
         mov       al,4
         call      OEmit
         pop       dx
         pop       cx
         pop       ax
         ret""",
    "SoundOff": """
         push      ax
         push      cx
         push      dx
         xor       cx,cx
         xor       dx,dx
         mov       al,5
         call      OEmit
         pop       dx
         pop       cx
         pop       ax
         ret""",
    "CekInit": """
         ret""",
    "Cekej": """
         push      cx
         jcxz      OCek9
OCek1:   call      OTick1
         loop      OCek1
OCek9:   pop       cx
         ret""",
}


def sub_once(pattern: str, repl: str, text: str) -> str:
    result, n = re.subn(pattern, repl, text, count=1, flags=re.M | re.I)
    if n != 1:
        raise ValueError(f"pattern not found: {pattern}")
    return result


def replace_proc(text: str, name: str, body: str) -> str:
    pat = re.compile(rf"(?ims)^{name}\s+PROC\b[^\n]*\n.*?^{name}\s+ENDP[^\n]*")
    result, n = pat.subn(lambda _: f"{name}   PROC      NEAR\n{body.strip(chr(10))}\n{name}   ENDP", text, count=1)
    if n != 1:
        raise ValueError(f"proc {name} not found")
    return result


def instr(text: str, mnemonic: str, operand: str, repl: str) -> tuple[str, int]:
    """Replace an instruction (not in comments) keeping any label prefix."""
    pat = re.compile(rf"(?im)^([^;\n]*?)\b{mnemonic}\s+{operand}\b")
    return pat.subn(lambda m: m.group(1) + repl, text)


def main() -> int:
    text = (UPSTREAM / "VLAK.ASM").read_text(encoding="latin-1").replace("\r\n", "\n")

    text = sub_once(r"^Start:(\s+)mov(\s+)ah,12h", r"Start:\1call      OInit\n\1mov\2ah,12h", text)
    text = sub_once(
        r"^\s+push\s+ds\n\s+xor\s+ax,ax\n\s+mov\s+ds,ax\n\s+mov\s+ax,ds:\[46ch\]\n\s+pop\s+ds\n",
        "         call      OTicks\n", text)
    text = sub_once(r"\[bx\+Start\]", "[bx+ONoise]", text)

    for proc, body in PROCS.items():
        text = replace_proc(text, proc, body)

    counts = {}
    for num, repl in (("10h", "call      OInt10"), ("16h", "call      OInt16"),
                      ("21h", "call      OInt21"), ("20h", "jmp       OExit")):
        text, counts[num] = instr(text, "int", num, repl)
    expected = {"10h": 5, "16h": 14, "21h": 2, "20h": 2}
    if counts != expected:
        raise ValueError(f"unexpected interrupt counts {counts} (expected {expected})")
    if re.search(r"(?im)^[^;\n]*\b(in|out)\s", text):
        raise ValueError("port I/O left in oracle source")

    noise = PRISTINE_COM.read_bytes()[:122]
    noise_db = "ONoise   db        " + ",".join(f"{b:03d}" for b in noise) + "\n"

    end = re.search(r"(?im)^Titulek\s+db", text)
    assert end is not None
    text = text[:end.start()] + DATA.lstrip() + noise_db + ROUTINES + "\n" + text[end.start():]

    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "VLAK.ASM").write_bytes(text.replace("\n", "\r\n").encode("latin-1"))
    shutil.copyfile(UPSTREAM / "SCENY.ASM", OUT / "SCENY.ASM")
    com = tasm_com(OUT)
    print(f"built {com.relative_to(ROOT)} ({com.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
