"""Chinese/Latin name entry without applying dialogue escapes to name grids.
Keep four u16 save cells and legacy kana. Convert directly to four 64-byte small
font tiles, avoiding the original unbounded main->small lookup and 8-byte stream
buffer. The name renderer's stock centering/copy tail is retained.
"""
import json,struct
from cn_codec import ROOT,BASE,FIRST,COMPACT
from cn_engine import asm,veneer


def config():return json.loads((ROOT/'data/gba-name-entry.json').read_text(encoding='utf-8'))
def name_font_rows():
 c=config();return [{'tokens':[c['default']+''.join(c['cn_rows'])]}]


def name_engine(rom,codec,eng,append):
 writes=[];c=config()
 def resource(data,tag):
  at=append(data);writes.append((at,data,tag));return BASE+at
 def stub(tag,text):
  at=append(b'\0'*512);code=asm(text,BASE+at)
  if len(code)>512:raise ValueError('Name stub overflow '+tag)
  writes.append((at,code,tag));(ROOT/'build'/f'{tag}.s').write_text(text,encoding='utf-8');return BASE+at
 def glyph(s):return codec.ids[s] if s in codec.ids else codec.stock.inverse[s]
 def stock_stream(pos,n=None):
  out=[]
  while (n is None or len(out)<n) and rom[pos]:
   k=rom[pos];pos+=1
   if k==1:k=256+rom[pos];pos+=1
   out.append(k)
  return out
 cn=''.join(c['cn_rows']);assert len(cn)==120
 grid=[glyph(s) for s in cn]+stock_stream(0x713f9e,180)[120:]
 assert len(grid)==180 and all(v not in (14,15) for v in grid[:120])
 grid_at=resource(struct.pack('<180H',*grid),'cn-name-u16-grid')
 writes.append((0xd2118,struct.pack('<I',grid_at),'cn-name-grid-pointer'))
 grid_stub=stub('name-grid-reader',f'''ldr r3, ={grid_at}
cmp r0,r3
beq chinese
push {{r4,r5,lr}}
mov r4,r0
lsls r2,r2,#16
lsrs r2,r2,#16
ldr r3, =0x080D3471
bx r3
chinese:
push {{r4,lr}}
mov r4,r2
cmp r2,#0
beq done
loop:
ldrh r3,[r0]
strh r3,[r1]
adds r0,#2
adds r1,#2
subs r2,#1
bne loop
done:
mov r0,r4
pop {{r4}}
pop {{r3}}
bx r3''')
 writes.append((0xd3468,veneer(grid_stub,3),'name-grid-reader-hook'))
 default_ids=[glyph(s) for s in c['default']]
 if len(default_ids)>4:raise ValueError('Default name exceeds four cells')
 default_at=resource(struct.pack('<5H',*(default_ids+[0]*(5-len(default_ids)))),'cn-default-name-u16')
 default_stub=stub('name-default',f'''ldr r1, ={default_at}
ldr r2, =0x02010280
movs r3,#5
loop:
ldrh r0,[r1]
strh r0,[r2]
adds r1,#2
adds r2,#2
subs r3,#1
bne loop
bx lr''')
 writes.append((0xd33c8,veneer(default_stub),'name-default-hook'))
 # The comparison parser alone may read a CN stream; the original grid cannot.
 stream_at=resource(codec.text(c['default'])+b'\0','cn-default-name-comparison')
 writes.append((0xd31fc,struct.pack('<I',stream_at),'cn-default-name-comparison-pointer'))
 compare=stub('name-compare',f'''push {{r4,r5,r6,lr}}
mov r4,r0
ldr r5, =0x02010280
movs r6,#0
loop:
ldrb r0,[r4]
adds r4,#1
cmp r0,#0
beq zero
cmp r0,#1
beq prefix
cmp r0,#15
beq extended
b match
zero:
subs r4,#1
b match
prefix:
ldrb r0,[r4]
adds r4,#1
movs r1,#1
lsls r1,r1,#8
adds r0,r0,r1
b match
extended:
ldrb r0,[r4]
subs r0,#16
lsls r1,r0,#8
lsls r0,r0,#4
subs r1,r1,r0
ldrb r0,[r4,#1]
subs r0,#16
adds r0,r0,r1
movs r1,#2
lsls r1,r1,#8
adds r0,r0,r1
adds r4,#2
match:
ldrh r1,[r5]
cmp r0,r1
bne fail
adds r5,#2
adds r6,#1
cmp r6,#4
blo loop
ldrb r0,[r4]
cmp r0,#0
bne fail
movs r0,#1
b exit
fail:
movs r0,#0
exit:
pop {{r4,r5,r6}}
pop {{r1}}
bx r1''')
 writes.append((0xd32c4,veneer(compare,3),'name-bounded-comparison-hook'))
 # Independent bounded mapping for legacy saved kana/Latin. Unsupported stock
 # codes fall back to '?' rather than walking beyond the end of the old table.
 small_question=codec.stock.small_inverse['？'];mapping=[small_question]*FIRST
 for small_code,big_code in enumerate(stock_stream(0x7140c1),16):
  if small_code>255:raise ValueError('Original small-name mapping exceeds byte range')
  if big_code<FIRST:mapping[big_code]=small_code
 mapping_at=resource(struct.pack('<512H',*mapping),'legacy-main-to-small-map')
 small_stub=stub('name-small-conversion',f'''add r1,sp,#8
mov r9,r1
movs r0,#0
movs r2,#1
lsls r2,r2,#8
ldr r3, =0x0800089D
bl call_r3
ldr r4, =0x02010280
mov r5,r9
movs r6,#0
charloop:
ldrh r0,[r4]
cmp r0,#0
beq done
ldr r1, ={FIRST}
cmp r0,r1
blo legacy
ldr r2, ={eng['primary_count']}
cmp r0,r2
bhs fallback
subs r0,r0,r1
lsls r0,r0,#6
ldr r1, ={BASE+eng['small_bitmap']}
adds r0,r0,r1
b copy
legacy:
lsls r0,r0,#1
ldr r1, ={mapping_at}
ldrh r0,[r1,r0]
b stock
fallback:
movs r0,#{small_question}
stock:
lsls r0,r0,#6
ldr r1, =0x0873CAE8
adds r0,r0,r1
copy:
movs r7,#16
wordloop:
ldr r1,[r0]
str r1,[r5]
adds r0,#4
adds r5,#4
subs r7,#1
bne wordloop
adds r4,#2
adds r6,#1
cmp r6,#4
blo charloop
done:
mov r8,r6
ldr r0, =0x08084075
bx r0
call_r3:
bx r3''')
 writes.append((0x8400c,veneer(small_stub),'name-small-conversion-hook'))
 # Fixed-size four-cell input banner keeps native 12px compact glyphs, while the
 # saved cells and ordinary dialogue player-name renderer remain primary IDs.
 banner=stub('name-banner',f'''push {{r4,r5,r6,lr}}
sub sp,#0x108
ldr r1, =0x0600FC00
mov r0,sp
ldr r3, =0x080970A1
bl call_r3
ldr r4, =0x03007280
movs r5,#0
loop:
ldr r0,[r4,#0x14]
movs r1,#0x89
lsls r1,r1,#2
adds r0,r0,r1
lsls r1,r5,#1
ldrh r1,[r0,r1]
ldr r2, ={FIRST}
cmp r1,r2
blo stock
ldr r3, ={eng['primary_count']}
cmp r1,r3
bhs stock
ldr r2, ={COMPACT-FIRST}
adds r1,r1,r2
stock:
mov r0,sp
ldr r3, =0x08096BC9
bl call_r3
adds r5,#1
cmp r5,#4
blo loop
add sp,#0x108
pop {{r4,r5,r6}}
pop {{r3}}
bx r3
call_r3:
bx r3''')
 writes.append((0xd349c,veneer(banner),'name-banner-hook'))
 return writes,{'grid':grid_at-BASE,'grid_count':180,'cn_cells':120,'default':c['default'],'default_ids':default_ids,'default_data':default_at-BASE,'comparison_stream':stream_at-BASE,'legacy_small_map':mapping_at-BASE,'stubs':{'grid':grid_stub,'default':default_stub,'compare':compare,'small_conversion':small_stub,'banner':banner},'save_format':'four original u16 cells; stable glyph registry','scope':'Chinese + original Latin pages; legacy voiced grid decoder retained; stock small-name centering retained'}
