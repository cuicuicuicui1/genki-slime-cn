"""Bitmap generation and ARM7TDMI Thumb stubs, assembled reproducibly by Keystone.
All existing main and small glyphs remain byte-identical in ROM.
"""
from pathlib import Path
from functools import lru_cache
import sys,struct,hashlib,json
from PIL import Image,ImageDraw
from cn_codec import ROOT,BASE,FIRST,COMPACT
sys.path.insert(0,str(ROOT/'tools/deps'))
from keystone import Ks,KS_ARCH_ARM,KS_MODE_THUMB,KS_MODE_LITTLE_ENDIAN

@lru_cache(maxsize=4)
def load_bdf(path):
 glyphs={};lines=path.read_text(encoding='utf-8').splitlines();cp=None;box=None;i=0
 while i<len(lines):
  line=lines[i].strip()
  if line.startswith('ENCODING '):cp=int(line.split()[1])
  elif line.startswith('BBX '):box=tuple(map(int,line.split()[1:]))
  elif line=='BITMAP':
   w,h,x,y=box;bits=[]
   for s in lines[i+1:i+1+h]:
    n=int(s,16);bits.append([(n>>(len(s)*4-1-j))&1 for j in range(w)])
   glyphs[cp]=(box,bits);i+=h
  i+=1
 return glyphs

def bitmap(char,bdf,size):
 if ord(char) not in bdf:raise ValueError('Font lacks '+repr(char))
 (w,h,x,y),bits=bdf[ord(char)];img=Image.new('1',(size,16))
 # BDF baseline: 12px ascent10, 8px ascent7; center vertically, preserve native bitmap.
 top=(16-size)//2+size-(y+h)-(2 if size in (12,16) else 1)
 for yy,row in enumerate(bits):
  for xx,ink in enumerate(row):
   dx=xx+x;dy=top+yy
   if ink and 0<=dx<size and 0<=dy<16:img.putpixel((dx,dy),1)
 if not img.getbbox() and not char.isspace():raise ValueError('Empty font glyph '+repr(char))
 return img

def main_bits(img,shadow_enabled=True):
 # Exact native 2bpp row-major format: shade3 (palette4) ink; shade2 down-right shadow.
 w,h=img.size;px=[]
 for y in range(h):
  for x in range(w):
   ink=img.getpixel((x,y));shadow=shadow_enabled and x>0 and y>0 and img.getpixel((x-1,y-1))
   px.append(3 if ink else 2 if shadow else 0)
 return bytes(sum(px[i+j]<<(6-j*2) for j in range(4)) for i in range(0,len(px),4))

def small_bits(img,shadow_enabled=True):
 # 8x16 4bpp tiles: same palette indexes as stock small font.
 data=bytearray()
 for y in range(16):
  for x in range(0,8,2):
   v=[]
   for dx in range(2):
    xx=x+dx;ink=img.getpixel((xx,y));shadow=shadow_enabled and xx>0 and y>0 and img.getpixel((xx-1,y-1))
    v.append(4 if ink else 3 if shadow else 1)
   data.append(v[0]|v[1]<<4)
 return bytes(data)

def veneer(target,reg=0):return struct.pack('<HHI',0x4800|(reg<<8),0x4700|(reg<<3),target|1)

def asm(source,address):
 k=Ks(KS_ARCH_ARM,KS_MODE_THUMB|KS_MODE_LITTLE_ENDIAN)
 result,_=k.asm(source,addr=address,as_bytes=True)
 return bytes(result)

def engine(rom,codec,append):
 """APPEND(data,align=4) returns file offset; collect verified original code writes."""
 profile=json.loads((ROOT/'data/gba-font-profile.json').read_text('utf-8'))
 bigbdf=load_bdf(ROOT/profile['main_bdf'])
 main_width=codec.main_px;main_stride=main_width*4
 smallbdf=load_bdf(ROOT/'assets/fonts/fusion8/fusion-pixel-8px-monospaced-zh_hans.bdf')
 primary_count=FIRST+len(codec.chars);count=COMPACT+len(codec.chars);descriptors=bytearray(count*8)
 compactbdf=load_bdf(ROOT/'assets/fonts/fusion12/fusion-pixel-12px-monospaced-zh_hans.bdf')
 compact=bytearray()
 descriptor_at=append(descriptors)
 main=bytearray();small=bytearray();sheet=Image.new('RGB',(20*24,32*((len(codec.chars)+23)//24)),(238,232,198));draw=ImageDraw.Draw(sheet)
 for n,c in enumerate(codec.chars):
  im=bitmap(c,bigbdf,main_width);sm=bitmap(c,smallbdf,8);main+=main_bits(im,profile['main_shadow']);small+=small_bits(sm,profile.get('small_shadow',True))
  compact+=main_bits(bitmap(c,compactbdf,12),profile.get('compact_shadow',True))
  x=(n%24)*20;y=(n//24)*32
  for yy in range(16):
   for xx in range(main_width):
    if im.getpixel((xx,yy)):sheet.putpixel((x+xx,y+yy),(15,15,15))
  for yy in range(16):
   for xx in range(8):
    if sm.getpixel((xx,yy)):sheet.putpixel((x+xx,y+yy+16),(15,15,15))
 big_at=append(main);compact_at=append(compact);small_at=append(small)
 ends=(0x13,0x18,0x23,0x3d,0x66,0x97,0xce,0x10c,0x141,0x1b8)
 for code in range(count):
  if code<FIRST or primary_count<=code<COMPACT:
   safe=min(code,0x1b8);group=next(i for i,v in enumerate(ends) if safe<=v)
   rec=rom[0x713eb8+group*8:0x713eb8+group*8+8]
  elif code<COMPACT:rec=struct.pack('<IHBB',BASE+big_at+(code-FIRST)*main_stride,code,main_width,main_stride)
  else:rec=struct.pack('<IHBB',BASE+compact_at+(code-COMPACT)*48,code,12,48)
  descriptors[code*8:code*8+8]=rec
 writes=[(descriptor_at,bytes(descriptors),'font-descriptors')]
 def stub(name,source):
  offset=append(b'\0'*512);code=asm(source,BASE+offset)
  if len(code)>512:raise ValueError('stub exceeds allocation')
  writes.append((offset,code,'stub-'+name));(ROOT/'build'/f'{name}.s').write_text(source,encoding='utf-8')
  return BASE+offset
 selector=stub('selector',f'''lsls r0,r0,#16
lsrs r0,r0,#16
ldr r1, ={primary_count}
cmp r0,r1
blo valid
ldr r1, ={COMPACT}
cmp r0,r1
blo fallback
ldr r1, ={count}
cmp r0,r1
blo valid
fallback:
movs r0,#16
valid:
lsls r0,r0,#3
ldr r1, ={BASE+descriptor_at}
adds r0,r0,r1
bx lr''')
 writes.append((0x971ec,veneer(selector,1),'selector-hook'))
 # Dispatcher input R2=context. Resume stock dispatcher for all stock bytes.
 dialog=stub('dialogue',f'''movs r3,#0x86
lsls r3,r3,#1
adds r1,r2,r3
ldr r0,[r1]
ldrb r3,[r0]
adds r0,#1
cmp r3,#15
beq extended
str r0,[r1]
ldr r0, =0x080961F7
bx r0
extended:
ldrb r3,[r0]
subs r3,#16
lsls r2,r3,#8
lsls r3,r3,#4
subs r2,r2,r3
ldrb r3,[r0,#1]
subs r3,#16
adds r3,r3,r2
movs r2,#2
lsls r2,r2,#8
adds r3,r3,r2
adds r0,#2
str r0,[r1]
ldr r0, =0x08096289
bx r0''')
 writes.append((0x961e8,veneer(dialog,0),'dialogue-hook'))
 # Plain/UI reader uses R4=source; supports same escape and preserves ALIGN.
 plain=stub('plain',f'''ldrb r1,[r4]
adds r4,#1
cmp r1,#15
beq extended
cmp r1,#1
beq prefix
cmp r1,#2
beq align
ldr r0, =0x08096CB9
bx r0
prefix:
ldr r0, =0x08096C7F
bx r0
align:
ldr r0, =0x08096C8D
bx r0
extended:
ldrb r1,[r4]
subs r1,#16
lsls r0,r1,#8
lsls r1,r1,#4
subs r0,r0,r1
ldrb r1,[r4,#1]
subs r1,#16
adds r1,r1,r0
movs r0,#2
lsls r0,r0,#8
adds r1,r1,r0
adds r4,#2
ldr r0, =0x08096CB9
bx r0''')
 writes.append((0x96c70,veneer(plain,0),'plain-hook'))
 # NAME label inner reader: the original copy, metadata and name-bar layout remain.
 speaker=stub('speaker',f'''ldrb r1,[r0]
cmp r1,#15
beq extended
lsls r0,r1,#6
ldr r1, =0x0873CAE8
adds r0,r0,r1
ldr r1, =0x080965AD
bx r1
extended:
ldrb r1,[r0,#1]
subs r1,#16
lsls r2,r1,#8
lsls r1,r1,#4
subs r2,r2,r1
ldrb r1,[r0,#2]
subs r1,#16
adds r2,r2,r1
adds r0,#2
str r0,[r5]
lsls r0,r2,#6
ldr r1, ={BASE+small_at}
adds r0,r0,r1
ldr r1, =0x080965AD
bx r1''')
 writes.append((0x965a4,veneer(speaker,1),'speaker-hook'))
 smallstub=stub('small',f'''ldrb r1,[r6]
adds r6,#1
cmp r1,#15
beq extended
lsls r0,r1,#6
mov r7,r10
ldr r2, =0x0809701D
bx r2
extended:
ldrb r1,[r6]
subs r1,#16
lsls r0,r1,#8
lsls r1,r1,#4
subs r0,r0,r1
ldrb r1,[r6,#1]
subs r1,#16
adds r0,r0,r1
lsls r0,r0,#6
ldr r7, ={BASE+small_at}
adds r6,#2
ldr r2, =0x0809701D
bx r2''')
 writes.append((0x97014,veneer(smallstub,0),'small-hook'))
 ticker=stub('ticker',f'''ldr r0,[r1]
ldrb r3,[r0]
adds r0,#1
adds r4,r2,#0
cmp r3,#15
beq extended
str r0,[r1]
ldr r0, =0x080D2A33
bx r0
extended:
ldrb r3,[r0]
subs r3,#16
lsls r2,r3,#8
lsls r3,r3,#4
subs r2,r2,r3
ldrb r3,[r0,#1]
subs r3,#16
adds r3,r3,r2
movs r2,#2
lsls r2,r2,#8
adds r3,r3,r2
ldr r2, ={COMPACT-FIRST}
adds r3,r3,r2
adds r0,#2
str r0,[r1]
ldr r0, =0x080D2A69
bx r0''')
 writes.append((0xD2A28,veneer(ticker,0),'name-instruction-ticker-hook'))
 from gba_speaker_font import speaker_engine
 speaker_writes,speaker_meta=speaker_engine(rom,codec,append)
 writes+=speaker_writes
 sheet.save(ROOT/'build/font-sheet.png')
 return writes,{'main_width':main_width,'main_stride':main_stride,'main_font':profile['main_font'],'main_shadow':profile['main_shadow'],'small_shadow':profile.get('small_shadow',True),'compact_shadow':profile.get('compact_shadow',True),'small_width':8,'descriptor':descriptor_at,'big_bitmap':big_at,'small_bitmap':small_at,'count':count,'primary_count':primary_count,'compact_base':COMPACT,'compact_bitmap':compact_at,'compact_width':12,'chinese_count':len(codec.chars),'speaker_label':speaker_meta,'stubs':{'selector':selector,'dialogue':dialog,'plain':plain,'speaker':speaker_meta['stub'],'small':smallstub,'ticker':ticker}}

