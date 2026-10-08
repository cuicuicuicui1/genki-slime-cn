#!/usr/bin/env python3
"""Owner-ROM-only graphics/native verification; never ROM downloads, never user saves."""
from pathlib import Path
import argparse,sys,json,struct
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'tools'),str(ROOT/'upstream/Translimeation/tools'),str(ROOT/'upstream/Translimeation/agent-tools')]
from project import read_source
p=argparse.ArgumentParser(description=__doc__);p.add_argument('--rom',type=Path,required=True);p.add_argument('--build',type=Path,required=True);p.add_argument('--out',type=Path,required=True);args=p.parse_args()
if args.out.exists():raise SystemExit('Choose a new verification output')
args.out.mkdir(parents=True)
from gba_graphic_labels_v22 import digest
from gba_title_graphics_v22 import frames
from slime_gfx import Decompressor
from unicorn import Uc,UC_ARCH_ARM,UC_MODE_THUMB,UC_HOOK_MEM_WRITE
from unicorn.arm_const import *
source=read_source(args.rom);build=args.build;target=(build/'slime-cn.gba').read_bytes();metas=json.loads((build/'graphics-profiles.json').read_text('utf-8'));report={'target_sha256':digest(target),'checks':[],'scope':'Actual target ARMv4T source consumers in controlled fragments; DMA copies modeled, not GBA timing or natural full gameplay'}
def cpu(rom):
 c=Uc(UC_ARCH_ARM,UC_MODE_THUMB);c.ctl_set_cpu_model(UC_CPU_ARM_TI925T)
 for a,n in [(0x8000000,len(rom)),(0x2000000,0x40000),(0x3000000,0x8000),(0x4000000,0x1000),(0x5000000,0x1000),(0x6000000,0x20000)]:c.mem_map(a,n)
 c.mem_write(0x8000000,rom)
 def dma(c,access,a,size,value,_):
  if a==0x40000dc and value&0x80000000:
   src,dst=struct.unpack('<II',c.mem_read(0x40000d4,8));unit=4 if value&(1<<26) else 2;count=value&0xffff or 0x10000;fixed=(value>>23)&3;assert fixed in (0,2);data=bytes(c.mem_read(src,unit if fixed==2 else unit*count));c.mem_write(dst,data*count if fixed==2 else data)
 c.hook_add(UC_HOOK_MEM_WRITE,dma,begin=0x40000dc,end=0x40000dc);return c
regs=[UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_R2,UC_ARM_REG_R3]
def call(c,at,args=(),lr=0x3000001):
 for reg,v in zip(regs,args):c.reg_write(reg,v)
 c.reg_write(UC_ARM_REG_SP,0x3007000);c.reg_write(UC_ARM_REG_LR,lr);c.emu_start(at|1,lr&~1,count=10000000);assert c.reg_read(UC_ARM_REG_PC)==lr&~1,(hex(at),hex(c.reg_read(UC_ARM_REG_PC)));return c.reg_read(UC_ARM_REG_R0)
c=cpu(target)
for group,m in metas.items():
 if 'private_archive' not in m:continue
 arc=m['private_archive'];cnt=struct.unpack_from('<I',target,arc)[0];base=arc+4+cnt*8
 for i in m['localized_resource_IDs']:
  rel,n=struct.unpack_from('<II',target,arc+4+i*8);at=(base+rel)&0xffffffff
  got=call(c,0x8000858,[0x8000000+arc,i]);assert got==0x8000000+at
  raw=target[at:at+n]
  if raw[0]==0x70:
   data=Decompressor(raw,0).decompress()[0];dest=0x2020000;c.mem_write(dest-2,b'\xa5'*(len(data)+4));count=call(c,0x8098ac8,[got,dest]);assert count==len(data);assert bytes(c.mem_read(dest,len(data)))==data;assert bytes(c.mem_read(dest-2,2))==b'\xa5'*2 and bytes(c.mem_read(dest+len(data),2))==b'\xa5'*2
   report['checks'].append({'group':group,'id':i,'kind':'native-getter-decompressor-guard','bytes':len(data)})
  else:
   if group=='title' and i==0x2be:
    anim,rows=frames(raw);ctx=0x2001000;call(c,0x80020c4,[ctx,got]);assert struct.unpack('<II',c.mem_read(ctx,8))==(got+4,got+anim)
    # 2140 selects an animation program, NOT a raw frame. Validate every directory entry with actual native getter math.
    for frame in range(31):
     pointer=got+4+(struct.unpack_from('<H',raw,4+frame*2)[0]&~1);assert struct.unpack('<H',c.mem_read(pointer,2))[0]==len(rows[frame])
    report['checks'].append({'group':'title','kind':'native-context-init-plus31-live-ROM-template-directory-readback','frame_count':31,'animation_anchor':anim})
for group,m in metas.items():
 for row in m.get('source_qualified_entries',[]):
  ptr=call(c,0x8000858,[0x8000000+row['archive'],row['ID']]);assert ptr==0x8000000+row['offset']
  raw=target[row['offset']:row['offset']+row['stored_bytes']]
  if raw[0]==0x70:
   expected=Decompressor(raw,0).decompress()[0];c.mem_write(0x2020000,b'\xa5'*(len(expected)+2));got=call(c,0x8098ac8,[ptr,0x2020000]);assert got==len(expected) and bytes(c.mem_read(0x2020000,len(expected)))==expected
  report['checks'].append({'group':group,'kind':'native-source-qualified-archive-entry','archive':row['archive'],'ID':row['ID']})
m=metas['extra_file_BG']
for request,ma,ta in m['pairs']:
 c.mem_write(0x6000000,b'\xa5'*32768);c.mem_write(0x2020000,b'\xa5'*4096);got=call(c,0x8098ac8,[request,0x2020000])
 expecttiles=Decompressor(target,ta-0x8000000).decompress()[0];expectmap=Decompressor(target,ma-0x8000000).decompress()[0]
 assert bytes(c.mem_read(0x6000000,32768))==expecttiles and bytes(c.mem_read(0x2020000,len(expectmap)))==expectmap and got==len(expectmap)
 report['checks'].append({'group':'extra_file_BG','kind':'chained previous native gateway paired atlas+map','source_request':hex(request),'bytes':got})
# The outer gateway must retain every old warning/sleep pair and stock fallback.
oldmeta=json.loads((build/'ui-candidate.json').read_text('utf-8'));oldtable=next(w['offset'] for w in json.loads((build/'manifest.json').read_text('utf-8'))['write_regions'] if w['purpose']=='file-ui-decode-pairs')
for at in range(oldtable,oldtable+128,16):
 request,ma,ta,dst=struct.unpack_from('<4I',target,at)
 if request==0:break
 if not ta:continue
 call(c,0x8098ac8,[request,0x2020000]);expected=Decompressor(target,ma-0x8000000).decompress()[0];atlas=Decompressor(target,ta-0x8000000).decompress()[0]
 assert bytes(c.mem_read(dst,len(atlas)))==atlas and bytes(c.mem_read(0x2020000,len(expected)))==expected
 report['checks'].append({'group':'extra_file_BG','kind':'retained old warning/sleep pair','source_request':hex(request)})
# Actual rescue result-loader fragment loads all four source maps + shared atlas.
c.reg_write(UC_ARM_REG_R5,0x5000002);c.reg_write(UC_ARM_REG_R6,0x600c000);c.reg_write(UC_ARM_REG_R8,0x600c800);c.reg_write(UC_ARM_REG_R9,0x600d000);c.reg_write(UC_ARM_REG_SP,0x3007000)
c.emu_start(0x80bb95d,0x80bb9d4,count=10000000);assert c.reg_read(UC_ARM_REG_PC)==0x80bb9d4
arc=metas['rescue']['private_archive'];ptr=call(c,0x8000858,[0x8000000+arc,0x169]);expect=Decompressor(target,ptr-0x8000000).decompress()[0];assert bytes(c.mem_read(0x6000000,32768))==expect
report['checks'].append({'group':'rescue','kind':'actual BB95C..BB9D4 loader fragment','all_source_map_calls_executed':True})
m=metas['saved_names'];ctx=0x2001000;dest=0x6005000
for lr in m['caller_return_CPU_addresses']:
 for code in [512,513,520,700,512+m['glyph_count']-1,65535]:
  c.mem_write(ctx,bytes(0x108));c.mem_write(ctx+0x100,struct.pack('<I',dest));c.mem_write(dest-2,b'\xa5'*132)
  call(c,0x8096bc8,[ctx,code],lr)
  expected=target[m['bank']+(code-512)*128:m['bank']+(code-511)*128] if code<512+m['glyph_count'] else bytes([0x11])*128
  assert bytes(c.mem_read(dest,128))==expected;assert bytes(c.mem_read(dest-2,2))==b'\xa5'*2 and bytes(c.mem_read(dest+128,2))==b'\xa5'*2
  assert struct.unpack('<I',c.mem_read(ctx+0x100,4))[0]==dest+128
report['checks'].append({'group':'saved_names','kind':'8 exact file callers, CJK/bounds/VRAM halfword guard','count':48})
# Compare legacy and unrelated callers with unmodified v21 base, same native output.
old=cpu(source)
for lr in [m['caller_return_CPU_addresses'][0],0x3000001]:
 for code in [0,0x10,0x20,0x60,0x141]:
  results=[]
  for cc in [old,c]:
   cc.mem_write(ctx,bytes(0x108));cc.mem_write(ctx+0x100,struct.pack('<I',dest));cc.mem_write(dest,bytes([0xa5])*128);call(cc,0x8096bc8,[ctx,code],lr);results.append((bytes(cc.mem_read(dest,128)),bytes(cc.mem_read(ctx+0x100,8))))
  assert results[0]==results[1],(lr,code)
report['checks'].append({'group':'saved_names','kind':'legacy file/nonfile paired output','count':10})
# Full stock file records, both slots. Fresh fixtures only; no user saves.
ids=json.loads((build/'build/font-map.json').read_text('utf-8'));codes=[ids[ch] for ch in '史拉林']+[0]
for slot in [0,1]:
 obj=0x2003000;c.mem_write(obj,bytes(0x300));c.mem_write(0x3007294,struct.pack('<I',obj));nameoff=0x100 if slot==0 else 0x214;flagoff=0x112 if slot==0 else 0x226;c.mem_write(obj+nameoff,struct.pack('<4H',*codes));c.mem_write(obj+flagoff,b'\x01');call(c,0x80d7988,[slot])
 expected=b''.join(target[m['bank']+(code-512)*128:m['bank']+(code-511)*128] if code>=512 else bytes([0x11])*128 for code in codes[:3])
 # Destination is a stock literal selected by slot; dynamic map is also stock.
 name_dest=0x6007680 if slot==0 else 0x6007b40
 assert bytes(c.mem_read(name_dest,len(expected)))==expected,(slot,hex(name_dest))
 report['checks'].append({'group':'saved_names','kind':'full original D7988 record compositor','slot':slot,'VRAM':hex(name_dest),'fixture_name':'史拉林','u16_cells_unchanged':bytes(c.mem_read(obj+nameoff,8))==struct.pack('<4H',*codes)})
report['status']='pass';(args.out/'native-graphics-verification.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n','utf-8');print(json.dumps(report,ensure_ascii=False,indent=2))
