/* HW.C - real hardware backend: EGA mode 0Dh, PC speaker, BIOS keyboard.
 * Each function reproduces the corresponding routine of VLAK.ASM. */

#include "VLAK.H"

void __outportb__(int port, unsigned char value);
unsigned char __inportb__(int port);

#define MK_FP(s, o) ((void far *)(((unsigned long)(s) << 16) | (unsigned)(o)))

static word Cit1ms;

void hw_start(void)
{
}

void hw_ega_info(byte *pbh, byte *pbl)
{
    byte h, l;
    asm mov ah,12h
    asm mov bx,7a10h
    asm int 10h
    asm mov h,bh
    asm mov l,bl
    *pbh = h;
    *pbl = l;
}

void hw_set_mode(byte mode)
{
    asm mov al,mode
    asm mov ah,0
    asm int 10h
}

void hw_cursor(word position)
{
    asm mov dx,position
    asm mov bh,0
    asm mov ah,2
    asm int 10h
}

void hw_char(byte glyph, byte attr)
{
    asm mov al,glyph
    asm mov bl,attr
    asm mov bh,0
    asm mov ah,9
    asm mov cx,1
    asm int 10h
}

/* DispObr: 16x16 tile, 4 planes x 16 lines x 2 bytes */
void hw_obr(byte tile, word position)
{
    byte far *src = (byte far *)Obrazky + ((word)tile << 7);
    byte far *base = (byte far *)MK_FP(0xA000,
        (position >> 8) * (16 * 40) + ((position & 0xFF) << 1));
    byte far *dst;
    byte plane;
    int line;

    __outportb__(0x3C4, 2);
    for (plane = 1; plane != 0x10; plane <<= 1) {
        __outportb__(0x3C5, plane);
        dst = base;
        for (line = 0; line < 16; ++line) {
            dst[0] = src[0];
            dst[1] = src[1];
            src += 2;
            dst += 40;
        }
    }
}

/* DispTit: title 32 bytes x 16 lines x 4 planes, CitTit bytes wide */
void hw_tit(byte width)
{
    byte far *src = (byte far *)Titulek;
    byte far *base = (byte far *)MK_FP(0xA000, 9 * 16 * 40 + 4);
    byte plane;
    int line, i;

    __outportb__(0x3C4, 2);
    for (plane = 1; plane != 0x10; plane <<= 1) {
        __outportb__(0x3C5, plane);
        for (line = 0; line < 16; ++line)
            for (i = 0; i < width; ++i)
                base[line * 40 + i] = src[line * 32 + i];
        src += 16 * 32;
    }
}

void hw_sound(word divisor)
{
    asm cli
    asm mov al,0b6h
    asm out 43h,al
    asm mov ax,divisor
    asm out 42h,al
    asm xchg ah,al
    asm out 42h,al
    asm in al,61h
    asm or al,3
    asm out 61h,al
    asm sti
}

void hw_sound_off(void)
{
    asm in al,61h
    asm and al,0fch
    asm out 61h,al
}

/* CekInit: count loop passes during one BIOS tick (55 ms) */
void hw_cek_init(void)
{
    word result;
    asm sti
    asm push ds
    asm xor ax,ax
    asm mov ds,ax
    asm xor dx,dx
    asm mov bx,46ch
    asm mov cx,[bx]
wait1:
    asm cmp cx,[bx]
    asm je wait1
    asm mov cx,[bx]
count:
    asm add ax,1
    asm adc dx,0
    asm cmp cx,[bx]
    asm je count
    asm pop ds
    asm mov bx,55
    asm cmp dx,bx
    asm jb divide
    asm mov dx,54
divide:
    asm div bx
    asm or ax,ax
    asm jnz store
    asm inc ax
store:
    asm mov result,ax
    Cit1ms = result;
}

/* Cekej: busy wait CX milliseconds */
void hw_cekej(word ms)
{
    word limit = Cit1ms;
    asm mov cx,ms
    asm jcxz done
ms_loop:
    asm xor ax,ax
    asm xor dx,dx
one_ms:
    asm add ax,1
    asm adc dx,0
    asm cmp ax,limit
    asm jne one_ms
    asm loop ms_loop
done:
    ;
}

word hw_ticks(void)
{
    return *(word far *)MK_FP(0, 0x46C);
}

int hw_kb_peek(word *pax)
{
    word key;
    asm mov ah,1
    asm int 16h
    asm jz no_key
    asm mov key,ax
    *pax = key;
    return 1;
no_key:
    return 0;
}

word hw_kb_read(void)
{
    word key;
    asm mov ah,0
    asm int 16h
    asm mov key,ax
    return key;
}

void hw_print(byte *text, int id)
{
    (void)id;
    asm push ds
    asm lds dx,text
    asm mov ah,9
    asm int 21h
    asm pop ds
}

void hw_exit(void)
{
    asm mov ax,4c00h
    asm int 21h
}
