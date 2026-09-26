/* HWTRACE.C - deterministic trace backend used for the equivalence proof.
 *
 * Mirrors the oracle routines injected into VLAK.ASM by tools/make_oracle.py:
 *  - virtual time advances only in Cekej (1 ms per unit); a BIOS tick is 55 ms
 *  - keys come from SCENARIO.BIN: u32 limit_ms, u16 count, count x (u32 t, u16 ax)
 *    and enter a 15-key BIOS-like buffer when t <= now at a keyboard call
 *  - every hardware access is written to TRACE.BIN as a 9-byte record
 *    (u8 type, u32 time, u16 a, u16 b); the run ends with a state dump. */

#include "VLAK.H"

#define MAXKEYS 2000

static word vlo, vhi, subms, ticks, limlo, limhi;
static word hout;
static byte obuf[512];
static word olen;
static word keycnt, keyidx;
static word keys[3 * MAXKEYS];
static word kbuf[15];
static byte khead, kcnt;
static word cursor;
static byte hdr[6];

static void dos_exit(byte code)
{
    asm mov al,code
    asm mov ah,4ch
    asm int 21h
}

static word dos_open(char *name)
{
    word h, fail = 0;
    asm push ds
    asm lds dx,name
    asm mov ax,3d00h
    asm int 21h
    asm pop ds
    asm mov h,ax
    asm jnc open_ok
    fail = 1;
open_ok:
    if (fail) dos_exit(2);
    return h;
}

static word dos_create(char *name)
{
    word h, fail = 0;
    asm push ds
    asm lds dx,name
    asm xor cx,cx
    asm mov ah,3ch
    asm int 21h
    asm pop ds
    asm mov h,ax
    asm jnc create_ok
    fail = 1;
create_ok:
    if (fail) dos_exit(3);
    return h;
}

static void dos_rw(byte fn, word h, void *p, word n)
{
    asm push ds
    asm lds dx,p
    asm mov cx,n
    asm mov bx,h
    asm mov ah,fn
    asm int 21h
    asm pop ds
}

static void dos_close(word h)
{
    asm mov bx,h
    asm mov ah,3eh
    asm int 21h
}

static void flush(void)
{
    dos_rw(0x40, hout, obuf, olen);
    olen = 0;
}

static void emit(byte type, word a, word b)
{
    byte *p = obuf + olen;
    p[0] = type;
    p[1] = (byte)vlo; p[2] = (byte)(vlo >> 8);
    p[3] = (byte)vhi; p[4] = (byte)(vhi >> 8);
    p[5] = (byte)a;   p[6] = (byte)(a >> 8);
    p[7] = (byte)b;   p[8] = (byte)(b >> 8);
    olen += 9;
    if (olen >= 504) flush();
}

static void put_word(word w)
{
    byte b[2];
    b[0] = (byte)w;
    b[1] = (byte)(w >> 8);
    dos_rw(0x40, hout, b, 2);
}

static void put_byte(byte v)
{
    dos_rw(0x40, hout, &v, 1);
}

static void finish(void)
{
    emit(0xFE, 0, 0);
    flush();
    dos_rw(0x40, hout, Mem, 241);           /* Pole + AktScen */
    dos_rw(0x40, hout, MapVlak, sizeof MapVlak);
    put_word(Smer);
    put_byte(Faze);
    put_word(CitVeci);
    put_word(PozVrat);
    put_word(Skore);
    put_byte(Demon);
    put_byte(CitTit);
    put_word(CitVyb);
    put_word(CitSound);
    put_word(AdrSound);
    put_word(LastTime);
    dos_close(hout);
    dos_exit(0);
}

static void tick1(void)
{
    if (++vlo == 0) ++vhi;
    if (++subms == 55) {
        subms = 0;
        ++ticks;
    }
    if (vhi > limhi || (vhi == limhi && vlo >= limlo)) finish();
}

static void deliver(void)
{
    while (keyidx < keycnt) {
        word *k = keys + 3 * keyidx;
        if (k[1] > vhi || (k[1] == vhi && k[0] > vlo)) break;
        if (kcnt < 15) {
            kbuf[(khead + kcnt) % 15] = k[2];
            ++kcnt;
        }
        ++keyidx;
    }
}

void hw_start(void)
{
    word h = dos_open("SCENARIO.BIN");
    dos_rw(0x3F, h, hdr, 6);
    limlo = hdr[0] | (hdr[1] << 8);
    limhi = hdr[2] | (hdr[3] << 8);
    keycnt = hdr[4] | (hdr[5] << 8);
    if (keycnt > MAXKEYS) dos_exit(4);
    dos_rw(0x3F, h, keys, keycnt * 6);
    dos_close(h);
    hout = dos_create("TRACE.BIN");
}

void hw_ega_info(byte *pbh, byte *pbl)
{
    *pbh = 0;
    *pbl = 3;
}

void hw_set_mode(byte mode)       { emit(6, mode, 0); }
void hw_cursor(word position)     { cursor = position; }
void hw_char(byte ch, byte attr)  { emit(3, ch | ((word)attr << 8), cursor); }
void hw_obr(byte tile, word pos)  { emit(1, tile, pos); }
void hw_tit(byte width)           { emit(2, width, 0); }
void hw_sound(word divisor)       { emit(4, divisor, 0); }
void hw_sound_off(void)           { emit(5, 0, 0); }
void hw_cek_init(void)            { }
word hw_ticks(void)               { return ticks; }

void hw_cekej(word ms)
{
    while (ms--) tick1();
}

int hw_kb_peek(word *pax)
{
    deliver();
    if (kcnt == 0) return 0;
    *pax = kbuf[khead];
    return 1;
}

word hw_kb_read(void)
{
    word ax;
    deliver();
    while (kcnt == 0) {
        if (keyidx >= keycnt) finish();
        tick1();
        deliver();
    }
    ax = kbuf[khead];
    khead = (byte)((khead + 1) % 15);
    --kcnt;
    emit(9, ax, 0);
    return ax;
}

void hw_print(byte *text, int id)
{
    (void)text;
    emit(7, id, 0);
}

void hw_exit(void)
{
    emit(8, 0, 0);
    finish();
}
