/* VLAK - C reimplementation of VLAK.ASM.
 *
 * The control flow deliberately mirrors the original labels (Start2, Start4,
 * ...) so every branch can be checked against the assembler source.  All
 * hardware access goes through the hw_* layer declared in VLAK.H. */

#include "VLAK.H"

/* ------ variables of the original data segment */
word Smer;                  /* direction: low byte dx, high byte dy */
byte Demon;                 /* 1 = demonstration */
byte CitTit;                /* width of the title in bytes */
word CitVeci;               /* items left */
word PozVrat;               /* gate position (high row, low column) */
word Skore;
byte MapVlak[3 * 12 * 20];  /* train: base sprite, X, Y; base 0 = end */
word LastTime;
byte Faze;
word CitVyb;                /* crash counter */
word CitSound;              /* sound length counter (0 = none) */
word AdrSound = 0xFFFF;     /* byte offset from TabSLok (0xFFFF = unset) */

static byte BuffHes[5];

/* The sound tables are followed in memory by live variables; the original
 * sound counters run past the tables, so they read those too. */
static word TabSound[] = {
    166, 254, 365,                                              /* TabSLok */
    400, 600, 800, 1000, 1200, 1400, 1600, 1800, 2000, 1800,    /* TabSVec */
    1600, 1400, 1200, 1000, 800, 600, 400, 200
};
#define SLOK_OFS  0
#define SLOK_CNT  (3 * 2 + 1)       /* offset(TabSLok0-TabSLok) + 1 */
#define SVEC_OFS  6
#define SVEC_CNT  (18 * 2 + 1)      /* offset(TabSVec0-TabSVec) + 1 */

static word sound_word(word ofs)
{
    word i = ofs >> 1;
    if (i < 21) return TabSound[i];
    switch (i) {
    case 21: return Smer;
    case 22: return Demon | (CitTit << 8);
    case 23: return CitVeci;
    case 24: return PozVrat;
    case 25: return Skore;
    }
    i = (i - 26) * 2;
    return MapVlak[i] | (MapVlak[i + 1] << 8);
}

/* ------ demonstration path, word per step: low = dx, high = dy */
static word DemoPos[179];

static void init_demo(void)
{
    int n = 0, i, k;
#define PUT(dl, dh, cnt) for (i = 0; i < (cnt); ++i) \
        DemoPos[n++] = (byte)(dl) | ((word)(byte)(dh) << 8)
    PUT(1, 0, 19);
    PUT(0, -1, 8);
    for (k = 0; k < 3; ++k) {
        PUT(-1, 0, 19); PUT(0, 1, 1); PUT(1, 0, 19); PUT(0, 1, 1);
    }
    PUT(-1, 0, 19);
    PUT(0, 1, 3);
    PUT(1, 0, 9); PUT(0, 1, 1);
#undef PUT
}

static char SkorTxt[] = "SKORE";
static char ScenTxt[] = " SCENA ";
static char HeslTxt[] = "F4 HESLO";
static char Hes2Txt[] = " heslo ";
static char Bla1Txt[] = "                              ";
static char Bla2Txt[] = "    B L A H O P R E J I  !    ";
static char Bla3Txt[] = "   Stal jste se absolutnim    ";
static char Bla4Txt[] = "      vitezem teto hry !      ";

/* ------------------------------------------------------------------ text */

static word pos;            /* DX of DispChr/DispTxt/DispNum */

static void DispChr(byte al, byte ah)
{
    hw_cursor(pos);
    hw_char(al, ah);
    ++pos;
}

static void DispTxt(char *s, byte ah)
{
    while (*s) DispChr((byte)*s++, ah);
}

static void DispNum(word ax, byte ch)
{
    byte digits[5];
    int n = 0;
    do {
        digits[n++] = (byte)(ax % 10);
        ax /= 10;
    } while (ax != 0);
    while (n) DispChr((byte)(digits[--n] + '0'), ch);
}

static void ClearInf(void)
{
    int i;
    pos = 24 * 256;
    for (i = 0; i < 40; ++i) DispChr(' ', 15);
}

static void DispSkor(void)
{
    word saved = pos;
    if (Demon == 0) {
        pos = 24 * 256 + 6;
        if (Skore != 0) DispNum(Skore, 14);
        DispChr('0', 14);
    }
    pos = saved;
}

static void DispInf(void)
{
    ClearInf();
    pos = 24 * 256;
    DispTxt(SkorTxt, 10);
    pos = (pos & 0xFF00) | (40 - 6 - 3);
    DispTxt(ScenTxt, 10);
    pos = (pos & 0xFF00) | 16;
    DispTxt(HeslTxt, 12);
    pos = (pos & 0xFF00) | (40 - 2);
    DispNum(AktScen, 14);
    DispSkor();
}

/* ------------------------------------------------------------------ misc */

static void FlushKey(void)
{
    word ax;
    while (hw_kb_peek(&ax)) hw_kb_read();
}

static word cell(word dx)
{
    return 20 * (dx >> 8) + (dx & 0xFF);
}

/* TestTime: returns 1 when a step elapsed (CF clear in the original) */
static int TestTime(void)
{
    word ax;
    hw_cekej(1);
    if (CitSound != 0) {
        if (--CitSound == 0) {
            hw_sound_off();
        } else {
            ax = sound_word(AdrSound);
            AdrSound += 2;
            hw_sound(ax);
        }
    }
    ax = hw_ticks() - LastTime;
    if (ax < 2) return 0;
    LastTime += ax;
    return 1;
}

static void DispScen(void)
{
    word dx;
    for (dx = 0; dx < 12 * 256; dx += 256) {
        int i;
        for (i = 0; i < 20; ++i) hw_obr(Pole[cell(dx + i)], dx + i);
    }
}

static void ClosScen(void)
{
    word dx;
    for (dx = 0; dx < 12 * 256; dx += 256) {
        int i;
        for (i = 0; i < 20; ++i) hw_obr(ZED, dx + i);
        hw_cekej(60);
    }
}

static void OpenScen(void)
{
    int row, i;
    for (row = 11; row >= 0; --row) {
        for (i = 0; i < 20; ++i)
            hw_obr(Pole[row * 20 + i], ((word)row << 8) + i);
        hw_cekej(60);
    }
}

static void OpenVrat(void)
{
    byte al;
    if (CitVeci != 0) return;
    al = Mem[cell(PozVrat)];
    if (al < VRA || al >= VRA + 5) return;
    ++al;
    Mem[cell(PozVrat)] = al;
    hw_obr(al, PozVrat);
}

static void IncFaze(void)
{
    word dx;
    int i;
    if (++Faze >= 3) Faze = 0;
    for (dx = 0; dx < 12 * 256; dx += 256) {
        for (i = 0; i < 20; ++i) {
            byte *p = &Pole[cell(dx + i)];
            byte al = *p;
            if (al >= VECI) {
                ++al;
                if (Faze == 0) al -= 3;
            } else if (al >= LO1 && al <= LOC && MapVlak[0] != 0) {
                al = (byte)(((al - LO1) & 3) + (Faze << 2) + 1);
            } else {
                continue;
            }
            *p = al;
            hw_obr(al, dx + i);
        }
    }
}

static void InitScen(byte scene)
{
    word dx;
    int i;
    byte al;
    hw_cek_init();
    for (i = 0; i < 240; ++i) Pole[i] = Sceny[(word)scene * 240 + i];
    CitVeci = 0;
    for (dx = 0; dx < 12 * 256; dx += 256) {
        for (i = 0; i < 20; ++i) {
            al = Pole[cell(dx + i)];
            if (al == VRA) PozVrat = dx + i;
            if (al >= VECI) ++CitVeci;
            if (al >= LO1 && al <= LO4) {
                MapVlak[0] = al;
                MapVlak[1] = (byte)i;
                MapVlak[2] = (byte)(dx >> 8);
                MapVlak[3] = 0;
            }
        }
    }
    MapVlak[0] = LO1;
    Faze = 0;
    Smer = 0;
}

/* PosVlak: move the train by DX; registers of the original kept as names */
static byte bh;

static void PosVlak(word delta)
{
    word si = 0, cx, dx, s;
    byte al, ah, dl, dh, old;

    dl = (byte)((delta & 0xFF) + MapVlak[1]);
    dh = (byte)((delta >> 8) + MapVlak[2]);
    for (;;) {
        cx = MapVlak[si + 1] | (MapVlak[si + 2] << 8);
        MapVlak[si + 1] = dl;
        MapVlak[si + 2] = dh;
        dx = dl | ((word)dh << 8);

        al = MapVlak[si];
        if ((cx & 0xFF) == 0xFF) {
            al += bh;
        } else {
            ah = (byte)(dl - (byte)cx);
            bh = 0;
            if (ah == 0) {
                ++al;                                   /* up */
                bh = 1;
                ah = (byte)(dh - (byte)(cx >> 8));
                if (!(ah & 0x80)) { al += 2; bh = 3; }  /* down */
            } else if (!(ah & 0x80)) {
                bh = 2;                                 /* right */
                al += 2;
            }
        }
        hw_obr(al, dx);

        old = Mem[cell(dx)];
        Mem[cell(dx)] = al;
        if (old >= VECI) {
            old -= VECI;
            --CitVeci;
            if (Demon == 0) {
                if (Skore != 0xFFFF) ++Skore;
                DispSkor();
            }
            al = (byte)((old / 3) * 4 + VAGONY);
            s = si;
            do s += 3; while (MapVlak[s] != 0);
            MapVlak[s] = al;
            MapVlak[s + 1] = 0xFF;
            MapVlak[s + 2] = 0xFF;
            MapVlak[s + 3] = 0;
        }

        si += 3;
        dl = (byte)cx;
        dh = (byte)(cx >> 8);
        if (MapVlak[si] == 0) break;
    }
    if (dl != 0xFF) {
        dx = dl | ((word)dh << 8);
        hw_obr(0, dx);
        Mem[cell(dx)] = 0;
    }
}

static void DispTit(void)
{
    hw_tit(CitTit);
}

/* ------------------------------------------------------------------ main */

int main(void)
{
    word ax, dx, si;
    byte al, bl, i, di;

    hw_start();
    init_demo();

    /* ------ card test */
    hw_ega_info(&bh, &bl);
    if (bh > 1 || bl > 3) {
        hw_print(CardTxt, 1);
        hw_exit();
    }
    hw_set_mode(0x0D);
    hw_cek_init();

    /* ------ demonstration */
Start2:
    InitScen(0);
    Demon = 1;
    ClearInf();
    DispScen();
    CitTit = 0;
    si = 0;
Start23:
    if (!TestTime()) goto Start3;
    IncFaze();
    OpenVrat();
    if (Faze != 0) goto Start3;
    if (MapVlak[1] == 9 && MapVlak[2] == 11) goto Start2;
    PosVlak(DemoPos[si++]);
    al = (byte)(MapVlak[1] << 1);
    if (al <= 4) goto Start3;
    al -= 4;
    if (al > 32 || CitTit >= 32) goto Start3;
    CitTit = al;
    DispTit();
Start3:
    if (!hw_kb_peek(&ax)) goto Start23;
    ax = hw_kb_read();
    if (ax != 0 && (ax & 0xFF) != 27) goto Start4;
    hw_sound_off();
    hw_set_mode(3);
    hw_print(UvTxt, 2);
    hw_exit();

    /* ------ start of scene */
Start4:
    Demon = 0;
    InitScen(AktScen);
    DispScen();
    DispInf();
Start41:
    FlushKey();
Start5:
    if (!TestTime()) goto Start5;
    if (hw_kb_peek(&ax)) {
        if (ax == 0x3E00) { hw_kb_read(); goto Heslo; }
        if (ax == 0 || (ax & 0xFF) == 27) { hw_kb_read(); goto Start61; }
    }
    IncFaze();
    OpenVrat();
    if (Faze != 0) goto Start5;
Start60:
    if (!hw_kb_peek(&ax)) goto Start69;
    ax = hw_kb_read();
    if (ax == 0x3E00) goto Heslo;
    if (ax == 0 || (ax & 0xFF) == 27) goto Start61;
    switch (ax >> 8) {
    case 0x48: dx = 0xFF00; break;          /* up */
    case 0x4B: dx = 0x00FF; break;          /* left */
    case 0x4D: dx = 0x0001; break;          /* right */
    case 0x50: dx = 0x0100; break;          /* down */
    default: goto Start60;
    }
    if (dx == Smer) goto Start60;
    Smer = dx;
Start69:
    dx = Smer;
    if (dx == 0) goto Start5;
    al = Mem[20 * (byte)((dx >> 8) + MapVlak[2]) + (byte)((dx & 0xFF) + MapVlak[1])];
    if (al == 0) goto Start6A;
    if (al >= VECI) {
        AdrSound = SVEC_OFS;
        CitSound = SVEC_CNT;
        goto Start6a4;
    }
    if (al <= VRA || al >= VRA + 6) goto Start8;
Start6A:
    AdrSound = SLOK_OFS;
    CitSound = SLOK_CNT;
Start6a4:
    PosVlak(dx);
    if ((MapVlak[1] | (MapVlak[2] << 8)) == PozVrat) goto Start7;
    goto Start5;

Start61:
    hw_sound_off();
    goto Start2;

    /* ------ scene completed */
Start7:
    CitSound = 0;
    {
        word a = 800, b = 2200, t, n;
        for (n = 250; n != 0; --n) {
            hw_sound(a); t = a; a = b; b = t; hw_cekej(2);
            hw_sound(a); t = a; a = b; b = t; hw_cekej(2);
            b -= 8;
        }
    }
    hw_sound_off();
    ClosScen();
    ClearInf();
    if (++AktScen > MAXSCEN) {
        AktScen = 1;
        goto Absol;
    }
    pos = (24 / 2 - 1) * 256 + (40 - 10) / 2;
    DispTxt(ScenTxt, 10);
    DispNum(AktScen, 14);
    DispChr(' ', 0);                        /* AH is still 0 from DispNum */
    pos = (24 / 2 + 1) * 256 + (40 - 13) / 2;
    DispTxt(Hes2Txt, 10);
    for (i = 0; i < 5; ++i)
        DispChr((byte)(TabHesel[5 * (AktScen - 1) + i] ^ X), 14);
    DispChr(' ', 14);
    FlushKey();
    hw_kb_read();
    InitScen(AktScen);
    OpenScen();
    DispInf();
    goto Start41;

    /* ------ crash */
Start8:
    MapVlak[0] = 0;
    CitVyb = 120;
    al = SR1;
Start80:
    hw_obr(al, MapVlak[1] | (MapVlak[2] << 8));
Start81:
    if (CitVyb != 0) {
        if (--CitVyb == 0) {
            hw_sound_off();
        } else {
            word bx = StartCode[CitVyb] | (StartCode[CitVyb + 1] << 8);
            hw_sound((word)((420 - CitVyb) << 4) + (bx & 0x0FFF));
        }
    }
    hw_cekej(9);
    if (!TestTime()) goto Start81;
    IncFaze();
    ++al;
    if (al < SRA + 1) goto Start80;
    al = SR8;
    if (!hw_kb_peek(&ax)) goto Start80;
    hw_sound_off();
    FlushKey();
    goto Start4;

    /* ------ absolute winner */
Absol:
    pos = 9 * 256 + 5;  DispTxt(Bla1Txt, 14);
    pos = 10 * 256 + 5; DispTxt(Bla2Txt, 14);
    pos = 11 * 256 + 5; DispTxt(Bla1Txt, 14);
    pos = 12 * 256 + 5; DispTxt(Bla3Txt, 10);
    pos = 13 * 256 + 5; DispTxt(Bla4Txt, 10);
    pos = 14 * 256 + 5; DispTxt(Bla1Txt, 10);
    FlushKey();
    hw_kb_read();
    goto Start2;

    /* ------ password entry */
Heslo:
    for (i = 0; i < 5; ++i) BuffHes[i] = TabHesel[5 * (AktScen - 1) + i];
    di = 0;
Heslo2:
    pos = 24 * 256 + 14;
    DispTxt(Hes2Txt, 12);
    for (i = 0; i < 5; ++i) {
        byte attr = 14;
        if (i == di) {
            DispChr(0xDB, 9);
            --pos;
            attr = 14 ^ 9 + 0x80;
        }
        DispChr((byte)(BuffHes[i] ^ X), attr);
    }
Heslo24:
    if (TestTime()) {
        IncFaze();
        OpenVrat();
    }
    if (!hw_kb_peek(&ax)) goto Heslo24;
    ax = hw_kb_read();
    al = (byte)ax;
    if (al == 13) goto Heslo5;
    if (ax == 0 || al == 27) goto Heslo27;
    if (ax == 0x4D00) goto Heslo42;
    if (al == 8 || al == 0x7F || ax == 0x5300 || ax == 0x4B00) {
        if (di > 0) --di;
        goto Heslo2;
    }
    if (al >= 'a' && al <= 'z') al -= 32;
    if (al < 'A' || al > 'Z') goto Heslo24;
    BuffHes[di] = (byte)(al ^ X);
Heslo42:
    if (di < 4) ++di;
    goto Heslo2;
Heslo5:
    for (dx = 1; dx <= MAXSCEN; ++dx) {
        for (i = 0; i < 5; ++i)
            if (TabHesel[5 * (dx - 1) + i] != BuffHes[i]) break;
        if (i == 5) {
            AktScen = (byte)dx;
            goto Start4;
        }
    }
Heslo27:
    DispInf();
    goto Start60;
}
