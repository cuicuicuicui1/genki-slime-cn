"""Native 12px speaker labels, composed inside the original name-tile bank.
Do not widen the separate 8px saved-name/list consumers. The NAME stream and
its 05 terminator are unchanged; only tile count/metadata use composed width.
"""
from PIL import Image
from cn_codec import ROOT,BASE
from cn_engine import load_bdf,bitmap,small_bits,asm,veneer


def speaker_engine(rom,codec,append):
 font=load_bdf(ROOT/'assets/fonts/fusion12/fusion-pixel-12px-monospaced-zh_hans.bdf')
 glyphs=bytearray()
 for c in codec.chars:
  image=Image.new('1',(16,16));image.paste(bitmap(c,font,12),(0,0))
  glyphs+=small_bits(image.crop((0,0,8,16)),False)+small_bits(image.crop((8,0,16,16)),False)
 bank=append(glyphs);stub=append(bytes(512));writes=[(bank,bytes(glyphs),'speaker-native12-font')]
 assembly=f'''push {{r4,r5,r6,r7,lr}}
mov r0,r8
mov r1,r9
mov r2,r10
mov r3,r11
push {{r0,r1,r2,r3}}
ldr r5, =0x02001080
mov r11,r5
movs r0,#0x84
lsls r0,r0,#1
ldr r0,[r5,r0]
ldr r1, =0xFA000D00
adds r1,r0,r1
lsls r1,r1,#17
lsrs r7,r1,#22
ldr r1, =0xD00
adds r0,r0,r1
mov r9,r0
ldr r1, =0x11111111
movs r2,#192
clear:
str r1,[r0]
adds r0,#4
subs r2,#1
bne clear
movs r0,#0x86
lsls r0,r0,#1
ldr r0,[r5,r0]
mov r8,r0
movs r0,#0
mov r10,r0
next:
mov r0,r8
ldrb r1,[r0]
cmp r1,#5
beq finished
cmp r1,#15
beq chinese
adds r0,#1
mov r8,r0
lsls r0,r1,#6
ldr r1, =0x0873CAE8
adds r0,r0,r1
movs r1,#8
b compose
chinese:
ldrb r1,[r0,#1]
subs r1,#16
lsls r2,r1,#8
lsls r1,r1,#4
subs r2,r2,r1
ldrb r1,[r0,#2]
subs r1,#16
adds r1,r1,r2
adds r0,#3
mov r8,r0
lsls r0,r1,#7
ldr r1, ={BASE+bank}
adds r0,r0,r1
movs r1,#12
compose:
mov r2,r10
adds r3,r2,r1
cmp r3,#96
bhi overflow
mov r10,r3
mov r3,r9
bl glyph
b next
overflow:
mov r0,r8
scan:
ldrb r1,[r0]
cmp r1,#5
beq finished_scan
adds r0,#1
cmp r1,#15
bne scan
adds r0,#2
b scan
finished_scan:
mov r8,r0
finished:
mov r0,r8
mov r5,r11
movs r1,#0x86
lsls r1,r1,#1
str r0,[r5,r1]
mov r0,r10
adds r0,#7
lsrs r6,r0,#3
pop {{r0,r1,r2,r3}}
mov r8,r0
mov r9,r1
mov r10,r2
mov r11,r3
ldr r0, =0x080965C5
bx r0
glyph:
push {{r4,r5,r6,r7,lr}}
mov r4,r0
mov r5,r1
mov r6,r2
mov r7,r3
movs r2,#0
row:
movs r3,#0
pixel:
lsrs r0,r3,#3
lsls r0,r0,#6
adds r0,r0,r4
lsls r1,r2,#2
adds r0,r0,r1
movs r1,#7
ands r1,r3
lsrs r1,r1,#1
adds r0,r0,r1
ldrb r0,[r0]
lsrs r1,r3,#1
bcc low_src
lsrs r0,r0,#4
low_src:
movs r1,#15
ands r0,r1
cmp r0,#1
beq skip
mov r12,r0
adds r0,r3,r6
movs r1,#7
ands r1,r0
lsrs r1,r1,#1
lsrs r0,r0,#3
lsls r0,r0,#6
adds r0,r0,r7
adds r0,r0,r1
lsls r1,r2,#2
adds r0,r0,r1
lsrs r1,r3,#1
bcs high_dst
ldrb r1,[r0]
lsrs r1,r1,#4
lsls r1,r1,#4
add r1,r12
b store_byte
high_dst:
mov r1,r12
lsls r1,r1,#4
mov r12,r1
ldrb r1,[r0]
lsls r1,r1,#28
lsrs r1,r1,#28
add r1,r12
store_byte:
mov r12,r1
lsrs r1,r0,#1
bcs odd_byte
ldrh r1,[r0]
lsrs r1,r1,#8
lsls r1,r1,#8
add r1,r12
strh r1,[r0]
b skip
odd_byte:
subs r0,#1
mov r1,r12
lsls r1,r1,#8
mov r12,r1
ldrh r1,[r0]
lsls r1,r1,#24
lsrs r1,r1,#24
add r1,r12
strh r1,[r0]
skip:
adds r3,#1
cmp r3,r5
blo pixel
adds r2,#1
cmp r2,#16
blo row
pop {{r4,r5,r6,r7}}
pop {{r0}}
bx r0'''
 code=asm(assembly,BASE+stub)
 if len(code)>512:raise ValueError('Speaker compositor exceeds allocation '+str(len(code)))
 if rom[0x96580:0x96588]!=bytes.fromhex('f0b51e4984225200'):raise ValueError('Speaker entry prologue moved')
 writes.extend([(stub,code,'speaker-native12-compositor'),(0x96580,veneer(BASE+stub),'speaker-native12-entry-hook')])
 (ROOT/'build/speaker-wide.s').write_text(assembly,'utf-8')
 return writes,{'bitmap':bank,'glyph_stride':128,'native_px':12,'advance_cn':12,'advance_legacy':8,'max_pixels':96,'reserved_bank_bytes':768,'background_palette_index':1,'shadow':False,'vram_write_contract':'aligned halfword RMW, never byte stores (GBA VRAM duplicates byte writes)','entry_hook':0x96580,'stub':BASE+stub,'scope':'NAME speaker bars only; original 8px saved-name/list consumers remain separate'}
