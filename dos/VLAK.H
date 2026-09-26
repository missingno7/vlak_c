/* VLAK - C reimplementation of VLAK.COM (Miroslav Nemecek, GOLEM).
 * Turbo C 2.0, compact model, no system headers. */

#ifndef VLAK_H
#define VLAK_H

typedef unsigned char byte;
typedef unsigned int word;

/* ------ EQU block of VLAK.ASM */
#define X        0xBA            /* password key */
#define MAXSCEN  51
#define FRSTSCEN 1
#define POCVECI  18
#define LOK      1
#define LO1      (LOK + 0)
#define LO4      (LOK + 3)
#define LOC      (LOK + 11)
#define SRAZKA   (LOK + 12)
#define SR1      (SRAZKA + 0)
#define SR8      (SRAZKA + 7)
#define SRA      (SRAZKA + 9)
#define ZED      (SRAZKA + 10)
#define VRA      (ZED + 1)
#define VAGONY   (VRA + 6)
#define VECI     (VAGONY + 4 * POCVECI)

/* ------ data (VLAKDATA.C, generated) */
#define MEM_SIZE (240 + 1 + 52 * 240)
extern byte Mem[MEM_SIZE];       /* Pole | AktScen | Sceny */
#define Pole    (Mem)
#define AktScen (Mem[240])
#define Sceny   (Mem + 241)
extern byte TabHesel[255];
extern byte UvTxt[];
extern byte CardTxt[];
extern byte StartCode[122];      /* first bytes of the original code at Start */
extern byte Titulek[2048];
extern byte Obrazky[156 * 128];

/* ------ game state (VLAK.C), exported for the trace harness */
extern word Smer, CitVeci, PozVrat, Skore, CitVyb, CitSound, AdrSound, LastTime;
extern byte Demon, CitTit, Faze;
extern byte MapVlak[3 * 12 * 20];

/* ------ platform layer (HW.C = real hardware, HWTRACE.C = oracle trace).
 * Every function corresponds 1:1 to a hardware access of VLAK.ASM. */
void hw_start(void);                   /* program entry hook */
void hw_ega_info(byte *bh, byte *bl);  /* INT 10h AH=12h BL=10h */
void hw_set_mode(byte mode);           /* INT 10h AH=0 */
void hw_cursor(word dx);               /* INT 10h AH=2, page 0 */
void hw_char(byte ch, byte attr);      /* INT 10h AH=9, CX=1 */
void hw_obr(byte tile, word dx);       /* DispObr */
void hw_tit(byte width);               /* DispTit */
void hw_sound(word divisor);           /* SetSound */
void hw_sound_off(void);               /* SoundOff */
void hw_cek_init(void);                /* CekInit */
void hw_cekej(word ms);                /* Cekej */
word hw_ticks(void);                   /* word at 0:046Ch */
int  hw_kb_peek(word *ax);             /* INT 16h AH=1, returns !ZF */
word hw_kb_read(void);                 /* INT 16h AH=0 */
void hw_print(byte *text, int id);     /* INT 21h AH=9 (id: 1 card, 2 farewell) */
void hw_exit(void);                    /* INT 20h */

#endif
