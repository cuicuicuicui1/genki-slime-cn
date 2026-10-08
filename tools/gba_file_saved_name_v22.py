"""File-card four-u16 saved names: native12 inside stock16px cells, bounded bank.
Exact eight file callers only; all other fixed-cell callers replay stock entry.
"""
import struct
from PIL import Image
from capstone import Cs,CS_ARCH_ARM,CS_MODE_THUMB
from cn_codec import ROOT,BASE,FIRST,SOURCE_SHA
from cn_engine import asm,veneer,bitmap,load_bdf
from gba_title_graphics_v22 import pack_image
from gba_graphic_labels_v22 import digest
HOOK=0x96BC8
PREFIX=bytes.fromhex('f0b5474680b4051c')
def extend(source,baseline,append_end,ids):
 if digest(source)!=SOURCE_SHA or source[HOOK:HOOK+8]!=PREFIX:raise ValueError('Wrong source/fixed-cell renderer')
 if baseline[HOOK:HOOK+8]!=PREFIX or baseline[0xD7988:0xD7BCE]!=source[0xD7988:0xD7BCE]:raise ValueError('File-name consumer already changed')
 values=sorted(ids.items(),key=lambda row:row[1]);assert [v for c,v in values]==list(range(FIRST,FIRST+len(values)))
 calls=[i.address-BASE for i in Cs(CS_ARCH_ARM,CS_MODE_THUMB).disasm(source[0xD7988:0xD7BCE],BASE+0xD7988) if i.mnemonic=='bl' and i.op_str=='#0x8096bc8'];assert len(calls)==8
 font=load_bdf(ROOT/'assets/fonts/fusion12/fusion-pixel-12px-monospaced-zh_hans.bdf');bank=bytearray();profiles=[]
 for ch,code in values:
  native=bitmap(ch,font,12);im=Image.new('P',(16,16),1)
  for y in range(16):
   for x in range(12):
    if native.getpixel((x,y)):im.putpixel((x+2,y),4)
  bank+=pack_image(im);profiles.append({'char':ch,'id':code,'bitmap_sha256':digest(native.tobytes())})
 assert len(bank)==len(values)*128
 rom=bytearray(baseline);cursor=(append_end+3)&~3;start=cursor;writes=[]
 def append(data,tag):
  nonlocal cursor
  cursor=(cursor+3)&~3;a=cursor
  if a+len(data)>len(rom) or any(b!=255 for b in rom[a:a+len(data)]):raise ValueError('Occupied/overflow tail')
  rom[a:a+len(data)]=data;cursor+=len(data);writes.append({'offset':a,'length':len(data),'purpose':tag});return a
 bankat=append(bank,'native12-four-tile-saved-name-bank');blank=append(bytes([0x11])*128,'bounded-invalid-name-blank')
 codeat=(cursor+3)&~3
 gate='\n'.join(f'ldr r2, ={BASE+a+5}\ncmp r3,r2\nbeq qualified' for a in calls)
 text=f"""mov r3,lr
{gate}
fallback:
push {{r4,r5,r6,r7,lr}}
mov r7,r8
push {{r7}}
mov r5,r0
ldr r3, ={BASE+HOOK+9}
bx r3
qualified:
ldr r2, ={FIRST}
cmp r1,r2
blo fallback
push {{r4,r5,r6,lr}}
mov r5,r0
subs r1,r1,r2
ldr r2, ={len(values)}
cmp r1,r2
bhs invalid
lsls r1,r1,#7
ldr r4, ={BASE+bankat}
adds r4,r4,r1
b draw
invalid:
ldr r4, ={BASE+blank}
draw:
mov r6,r5
adds r6,#0xff
adds r6,#1
ldr r1,[r6]
movs r2,#64
copy:
ldrh r3,[r4]
strh r3,[r1]
adds r4,#2
adds r1,#2
subs r2,#1
bne copy
str r1,[r6]
movs r0,#0
strh r0,[r6,#4]
strb r0,[r6,#6]
pop {{r4,r5,r6}}
pop {{r3}}
bx r3
"""
 code=asm(text,BASE+codeat);assert len(code)<512
 # Every branch is local Thumb1. Do not permit accidental Thumb2 or BLX.
 instructions=list(Cs(CS_ARCH_ARM,CS_MODE_THUMB).disasm(code,BASE+codeat))
 if any(i.mnemonic=='blx' or i.mnemonic.endswith('.w') for i in instructions):raise ValueError('Not ARMv4T')
 assert append(code,'file-only-native12-name-dispatch')==codeat
 rom[HOOK:HOOK+8]=veneer(BASE+codeat,3);writes.append({'offset':HOOK,'length':8,'purpose':'source-qualified-fixed-cell-entry'})
 changed=[i for i,(a,b) in enumerate(zip(baseline,rom)) if a!=b];assert all(any(w['offset']<=i<w['offset']+w['length'] for w in writes) for i in changed)
 return bytes(rom),{'schema':'gba-file-saved-name-native12-v22','status':'candidate','source_sha256':SOURCE_SHA,'baseline_sha256':digest(baseline),'target_sha256':digest(rom),'append_start':start,'append_end':cursor,'writes':writes,'hook':HOOK,'stub':codeat,'bank':bankat,'glyph_count':len(values),'caller_return_CPU_addresses':[BASE+a+5 for a in calls],'caller_source_sha256':digest(source[0xD7988:0xD7BCE]),'cell_size':[16,16],'native_font_px':12,'ID_registry_unchanged':True,'saved_u16_cells_unchanged':True,'legacy_and_other_callers_fallback':True,'bounded_invalid_CN_ids':True,'VRAM_writes':'aligned halfwords only, 64 per glyph','glyph_profiles':profiles,'assembly':text}
