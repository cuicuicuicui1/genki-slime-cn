"""Run actual target-ROM ARM7 text routines, not a rewritten text model.
Unicorn handles instructions; the DMA4 emulation used by upstream is explicitly
part of this fixture and does not claim complete GBA timing/gameplay fidelity.
"""
import sys,json,struct,hashlib
from pathlib import Path
from cn_codec import ROOT,BASE,CNCodec,SOURCE_SHA
sys.path.insert(0,str(ROOT/'tools/deps'))
sys.path.insert(0,str(ROOT/'upstream/Translimeation/agent-tools'))
from unicorn import UC_HOOK_CODE,UC_HOOK_MEM_WRITE
from unicorn.arm_const import *
from PIL import Image,ImageDraw

from project_paths import SOURCE_PATH
source=SOURCE_PATH.read_bytes()
if hashlib.sha256(source).hexdigest()!=SOURCE_SHA:raise ValueError('Wrong source ROM')
target=(ROOT/'build/slime-cn.gba').read_bytes()
ids=json.loads((ROOT/'build/font-map.json').read_text(encoding='utf-8'));codec=CNCodec(ids)
manifest=json.loads((ROOT/'build/manifest.json').read_text(encoding='utf-8'))
main_width=manifest['engine'].get('main_width',12);main_stride=main_width*4
probe=(ROOT/'upstream/Translimeation/agent-tools/probe_text_renderer.py').read_text(encoding='utf-8')
probe=probe.replace("ROM = Path('slime_original.gba').read_bytes()","ROM = SOURCE_ROM")
ns={'SOURCE_ROM':source,'__name__':'renderer_fixture'};exec(compile(probe,'upstream-real-renderer-fixture','exec'),ns)
def new_arm7(arch,mode):
 from unicorn import Uc
 c=Uc(arch,mode);c.ctl_set_cpu_model(UC_CPU_ARM_TI925T);return c
ns['create_cpu'].__globals__['Uc']=new_arm7
cpu=ns['create_cpu'](target);reset=ns['reset'];draw=ns['draw'];checks=0
# All stock glyphs and cursor alignments against source, independent of new table.
for code in range(0x10,0x1b9):
 for cursor in (0,1,207):
  reset(cpu);expect=ns['descriptor'](code)[2]+bool(cursor)
  assert draw(cpu,code,cursor)==expect,(hex(code),cursor);checks+=1
# Every CN glyph, every alignment, actual composited VRAM matches exact source bitmap.
pixel_checks=0
for code in codec.by_id:
 for lead in range(8):
  reset(cpu);cursor=0
  for _ in range(lead):cursor+=draw(cpu,0x10,cursor)
  start=cursor;adv=draw(cpu,code,cursor)
  address,first,width,stride=struct.unpack_from('<IHBB',target,manifest['engine']['descriptor']+code*8)
  assert adv==width+bool(cursor)
  assert first==code and width in (12,main_width) and stride==width*4
  bits=target[address-BASE:address-BASE+stride];px=[(b>>s)&3 for b in bits for s in (6,4,2,0)]
  data=cpu.mem_read(ns['DEST'],((start+adv+7)//8)*64)
  for y in range(16):
   for x in range(width):
    screen_x=start+bool(start)+x;v=data[(screen_x//8)*64+y*4+(screen_x%8)//2]
    actual=(v>>((screen_x&1)*4))&15
    expected=px[y*width+x]+1
    assert actual==expected,(code,lead,x,y,actual,expected)
  pixel_checks+=1
# Real dispatcher and plain-reader extension consume exactly 3 bytes.
reader_checks=0;entry=0x02030000;ctx=0x02001080
for code,c in codec.by_id.items():
 data=codec.escape(code);cpu.mem_write(entry,data+b'\0')
 cpu.mem_write(ctx+0x10c,struct.pack('<I',entry))
 cpu.reg_write(UC_ARM_REG_R2,ctx);cpu.reg_write(UC_ARM_REG_SP,0x03007000)
 cpu.emu_start(0x080961e9,0x08096288,count=1000)
 assert cpu.reg_read(UC_ARM_REG_PC)==0x08096288 and cpu.reg_read(UC_ARM_REG_R3)==code
 assert struct.unpack('<I',cpu.mem_read(ctx+0x10c,4))[0]==entry+3
 cpu.reg_write(UC_ARM_REG_R4,entry)
 cpu.emu_start(0x08096c71,0x08096cb8,count=1000)
 assert cpu.reg_read(UC_ARM_REG_PC)==0x08096cb8 and cpu.reg_read(UC_ARM_REG_R1)==code
 assert cpu.reg_read(UC_ARM_REG_R4)==entry+3
 reader_checks+=2
# Full ordinary UI text renderer: stock ALIGN grammar and actual CN rendering.
ui_checks=0
for compact in (False,True):
 for text in ('是','初级','谢谢你救了我！','汉字边界验证'):
  if any(c not in codec.ids and c not in codec.stock.inverse for c in text):continue
  data=codec.text(text,compact=compact)+b'\0';cpu.mem_write(entry,data);cpu.mem_write(ns['DEST'],b'\x11'*4096)
  for reg,val in [(UC_ARM_REG_R0,ns['DEST']),(UC_ARM_REG_R1,entry),(UC_ARM_REG_R2,0),(UC_ARM_REG_SP,0x03007000),(UC_ARM_REG_LR,0x03000001)]:cpu.reg_write(reg,val)
  cpu.emu_start(0x08096c41,0x03000000,count=1000000)
  assert cpu.reg_read(UC_ARM_REG_PC)==0x03000000
  ui_checks+=1
# Full small-font routine consumes the new glyph stream; compare actual VRAM tiles.
small_checks=0
for c,code in codec.ids.items():
 data=codec.glyph(c)+b'\0';cpu.mem_write(entry,data);cpu.mem_write(ns['DEST'],b'\0'*128)
 for reg,val in [(UC_ARM_REG_R0,ns['DEST']),(UC_ARM_REG_R1,entry),(UC_ARM_REG_R2,0),(UC_ARM_REG_SP,0x03007000),(UC_ARM_REG_LR,0x03000001)]:cpu.reg_write(reg,val)
 cpu.emu_start(0x08096fe9,0x03000000,count=50000)
 assert cpu.reg_read(UC_ARM_REG_PC)==0x03000000 and cpu.reg_read(UC_ARM_REG_R0)==2
 offset=manifest['engine']['small_bitmap']+(code-0x200)*64
 assert bytes(cpu.mem_read(ns['DEST'],64))==target[offset:offset+64],code
 small_checks+=1
# Real name-label loop/copy. Only its tilemap metadata callee is stubbed.
metadata=[]
def speaker_boundary(uc,address,size,user):
 if address==0x08097d6c:
  metadata.append((uc.reg_read(UC_ARM_REG_R0),uc.reg_read(UC_ARM_REG_R1)))
  uc.reg_write(UC_ARM_REG_PC,uc.reg_read(UC_ARM_REG_LR))
handle=cpu.hook_add(UC_HOOK_CODE,speaker_boundary,begin=0x08097d6c,end=0x08097d6c)
# Model GBA VRAM byte-write duplication. A normal byte-addressable Unicorn
# fixture accepted the earlier strb compositor but mGBA showed checkerboard
# corruption; all destination read/modify/writes must now use halfwords.
def gba_vram_alias(uc,access,address,size,value,user):
 if size==1:uc.mem_write(address&~1,bytes([value&255])*2)
vram_write_handle=cpu.hook_add(UC_HOOK_MEM_WRITE,gba_vram_alias,begin=0x06000000,end=0x06017fff)
speaker_checks=0
speaker_meta=manifest['engine']['speaker_label']
def expected_speaker(name):
 glyphs=[];cursor=0
 for unit in codec.units(name,True):
  if unit in codec.ids:
   at=speaker_meta['bitmap']+(codec.ids[unit]-0x200)*128;width=12
  else:
   at=0x73cae8+codec.stock.small_inverse[unit]*64;width=8
  data=target[at:at+(128 if width==12 else 64)]
  if cursor+width>speaker_meta['max_pixels']:break
  glyphs.append((cursor,width,data));cursor+=width
 buf=bytearray(b'\x11'*768)
 for x,width,data in glyphs:
  for y in range(16):
   for xx in range(width):
    b=data[xx//8*64+y*4+(xx%8)//2];value=(b>>((xx&1)*4))&15
    if value==1:continue
    dx=x+xx;pos=dx//8*64+y*4+(dx%8)//2;shift=(dx&1)*4
    buf[pos]=(buf[pos]&~(15<<shift))|(value<<shift)
 return bytes(buf),(cursor+7)//8
speaker_cases=[c+c for c in list(codec.ids)[:4]+list(codec.ids)[239:242]+list(codec.ids)[-2:]]
speaker_cases+=['史拉林','多拉哈尔特Ｊｒ．','史拉林八世','ＡＢＣＤ','米伊洪爸爸','史'*8,'史'*9]
all_names={t[1] for r in manifest['records'] for t in r['tokens'] if isinstance(t,list) and t[0]=='NAME'}
for name in sorted(all_names):
 width=sum(12 if c in codec.ids else 8 for c in codec.units(name,True))
 assert width<=speaker_meta['max_pixels'],('NAME exceeds speaker bank',name,width)
speaker_cases+=sorted(all_names)
for name in speaker_cases:
 stream=codec.text(name,True)+b'\x05'
 cpu.mem_write(entry,stream);cpu.mem_write(ctx+0x108,struct.pack('<I',ns['DEST']))
 cpu.mem_write(ctx+0x10c,struct.pack('<I',entry));cpu.mem_write(ns['DEST'],b'\xA5'*0x1040)
 cpu.reg_write(UC_ARM_REG_SP,0x03007000);cpu.reg_write(UC_ARM_REG_LR,0x03000001)
 high_regs=[UC_ARM_REG_R8,UC_ARM_REG_R9,UC_ARM_REG_R10,UC_ARM_REG_R11]
 for i,r in enumerate(high_regs):cpu.reg_write(r,0x12340000+i)
 cpu.emu_start(0x08096581,0x03000000,count=400000)
 assert cpu.reg_read(UC_ARM_REG_PC)==0x03000000
 assert struct.unpack('<I',cpu.mem_read(ctx+0x10c,4))[0]==entry+len(stream)
 expected,cells=expected_speaker(name)
 assert cpu.mem_read(ctx+0x13e,1)==bytes([cells]) and metadata[-1][1]==cells
 assert bytes(cpu.mem_read(ns['DEST']+0xd00,768))==expected,name
 assert cpu.mem_read(ns['DEST'],0xd00)==b'\xA5'*0xd00
 assert cpu.mem_read(ns['DEST']+0x1000,64)==b'\xA5'*64
 for i,r in enumerate(high_regs):assert cpu.reg_read(r)==0x12340000+i
 speaker_checks+=1
cpu.hook_del(handle)
# Actual name-entry hint ticker with glyph IDs beyond the old 9-bit range.
ticker_checks=0
ui_global=struct.unpack_from('<I',source,0xD2A40)[0];obj=0x02008000
for c in list(codec.ids)[:2]+list(codec.ids)[239:242]+list(codec.ids)[-2:]:
 cpu.mem_write(ui_global+0x14,struct.pack('<I',obj));cpu.mem_write(entry,codec.glyph(c)+b'\0')
 cpu.mem_write(obj+0x23c,b'\x11'*256+struct.pack('<I',ns['DEST'])+b'\0'*256)
 cpu.mem_write(obj+0x344,struct.pack('<I',entry));cpu.mem_write(obj+0x350,b'\0'*4);cpu.reg_write(UC_ARM_REG_SP,0x03007000);cpu.reg_write(UC_ARM_REG_LR,0x03000001)
 cpu.emu_start(0x080d2a1d,0x03000000,count=50000)
 assert cpu.reg_read(UC_ARM_REG_PC)==0x03000000
 assert struct.unpack('<I',cpu.mem_read(obj+0x344,4))[0]==entry+3
 assert struct.unpack('<H',cpu.mem_read(obj+0x350,2))[0]==13
 ticker_checks+=1
# Actual credits copy loop: canary protects its live SP+0x20 local.
credit_checks=0;stack=0x03006000
for rec in manifest.get('credits',[]):
 pos=rec['offset']
 for line in rec['lines']:
  assert target[pos]==line['tile_row'];pos+=2
  start=pos
  while target[pos] not in (0,2):pos+=1
  encoded=target[start:pos];assert len(encoded)<=31
  cpu.mem_write(stack,b'\xAA'*32+b'\xEF\xBE\xAD\xDE'+b'\xBB'*16)
  for reg,val in [(UC_ARM_REG_SP,stack),(UC_ARM_REG_R0,target[start]),(UC_ARM_REG_R2,0),(UC_ARM_REG_R3,0),(UC_ARM_REG_R4,BASE+start)]:cpu.reg_write(reg,val)
  cpu.emu_start(0x0807fcdd,0x0807fcec,count=20000)
  assert cpu.reg_read(UC_ARM_REG_PC)==0x0807fcec
  assert bytes(cpu.mem_read(stack,len(encoded)+1))==encoded+b'\0'
  assert bytes(cpu.mem_read(stack+32,4))==b'\xEF\xBE\xAD\xDE'
  credit_checks+=1;pos+=1
 assert pos==rec['offset']+rec['bytes']
report={'rom_sha256':hashlib.sha256(target).hexdigest(),'status':'pass','cpu_model':'Unicorn TI925T ARMv4T instruction model; fixture DMA, not full GBA timing','stock_advance_checks':checks,'cn_pixel_checks':pixel_checks,'reader_checks':reader_checks,'ui_checks':ui_checks,'small_checks':small_checks,'speaker_checks':speaker_checks,'speaker_vram_byte_duplication_model':True,'ticker_checks':ticker_checks,'credit_copy_checks':credit_checks,'not_proven':['whole-game emulation','hardware','natural scene reachability','human review of every glyph']}
(ROOT/'evidence/engine-tests.json').write_text(json.dumps(report,indent=2),encoding='utf-8');print(report)


