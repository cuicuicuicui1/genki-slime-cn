"""Execute actual default-name, grid, comparison and small-name ROM consumers.
Compare legacy conversions with original ROM. DMA is fixture-emulated, not a
complete GBA timing model. CJK cases check pre-centering tiles and stack guards.
"""
import json,struct,hashlib,sys
from pathlib import Path
from cn_codec import ROOT,BASE,SOURCE_SHA
sys.path.insert(0,str(ROOT/'tools/deps'))
sys.path.insert(0,str(ROOT/'upstream/Translimeation/agent-tools'))
from unicorn.arm_const import *
from unicorn import UC_HOOK_CODE
from project_paths import SOURCE_PATH
source=SOURCE_PATH.read_bytes()
if hashlib.sha256(source).hexdigest()!=SOURCE_SHA:raise ValueError('Wrong source ROM')
target=(ROOT/'build/slime-cn.gba').read_bytes();manifest=json.loads((ROOT/'build/manifest.json').read_text('utf-8'));name=manifest['engine']['name_entry']
probe=(ROOT/'upstream/Translimeation/agent-tools/probe_text_renderer.py').read_text('utf-8').replace("ROM = Path('slime_original.gba').read_bytes()","ROM = SOURCE_ROM")
ns={'SOURCE_ROM':source,'__name__':'renderer_fixture'};exec(compile(probe,'fixture','exec'),ns)
def new_arm7(arch,mode):
 from unicorn import Uc
 c=Uc(arch,mode);c.ctl_set_cpu_model(UC_CPU_ARM_TI925T);return c
ns['create_cpu'].__globals__['Uc']=new_arm7
cpu=ns['create_cpu'](target);original=ns['create_cpu'](source)
SP=0x03007000;RET=0x03000000;RAM=0x02010280;checks={}
stop_request=[RET]
cpu.hook_add(UC_HOOK_CODE,lambda uc,a,n,u:uc.emu_stop() if stop_request[0]==a else None,begin=0x08084074,end=0x08084074)
def run(c,entry,r0=0,r1=0,r2=0,stop=RET):
 for r,v in [(UC_ARM_REG_SP,SP),(UC_ARM_REG_LR,RET|1),(UC_ARM_REG_R0,r0),(UC_ARM_REG_R1,r1),(UC_ARM_REG_R2,r2)]:c.reg_write(r,v)
 stop_request[0]=stop
 c.emu_start(entry|1,RET,count=300000)
 assert c.reg_read(UC_ARM_REG_PC)==stop,(hex(entry),hex(c.reg_read(UC_ARM_REG_PC)))
 return c.reg_read(UC_ARM_REG_R0)
def put(c,codes):c.mem_write(RAM,struct.pack('<5H',*(codes+[0]*(5-len(codes)))))
# Default writes precisely five halfwords, including the unused fifth terminator.
cpu.mem_write(RAM-4,b'\xA5'*18);run(cpu,0x080d33c8)
assert list(struct.unpack('<5H',cpu.mem_read(RAM,10)))==name['default_ids']+[0,0]
assert cpu.mem_read(RAM-4,4)==b'\xA5'*4 and cpu.mem_read(RAM+10,4)==b'\xA5'*4
checks['default_with_guards']=1
# New u16 grid vs original voiced grid (0E/0F retain their grid meanings).
DEST=0x02030000;grid=BASE+name['grid'];cpu.mem_write(DEST,b'\xA5'*364)
run(cpu,0x080d3468,grid,DEST,180)
assert bytes(cpu.mem_read(DEST,360))==target[name['grid']:name['grid']+360]
assert cpu.mem_read(DEST+360,4)==b'\xA5'*4
for c in [cpu,original]:run(c,0x080d3468,0x08714054,DEST,50)
assert cpu.mem_read(DEST,100)==original.mem_read(DEST,100)
checks['grids']=230
# Default, kana/Latin reserved comparisons and all classification results.
run(cpu,0x080d33c8);assert run(cpu,0x080d31e8)==1
compare_ptr=BASE+name['comparison_stream'];assert run(cpu,0x080d32c4,compare_ptr)==1
cpu.mem_write(RAM,struct.pack('<H',name['default_ids'][0]+1));assert run(cpu,0x080d32c4,compare_ptr)==0
checks['comparison']=3
for ptr,classification in [(0x0871409b,2),(0x0871409f,2),(0x087140a3,2),(0x087140a8,2),(0x087140ad,2),(0x087140b2,2),(0x087140b7,3)]:
 pos=ptr-BASE;ids=[]
 while source[pos]:
  v=source[pos];pos+=1
  if v==1:v=source[pos]+256;pos+=1
  ids.append(v)
 put(cpu,ids);assert run(cpu,0x080d32c4,ptr)==1;assert run(cpu,0x080d31e8)==classification
 checks['comparison']+=2
# All mapped legacy glyphs, lengths 1..4, full original centering/copy result.
mp=struct.unpack_from('<512H',target,name['legacy_small_map']);mapped=set();pos=0x7140c1
while source[pos]:
 v=source[pos];pos+=1
 if v==1:v=source[pos]+256;pos+=1
 mapped.add(v)
for code in sorted(mapped):
 for length in range(1,5):
  for c in [cpu,original]:
   c.mem_write(0x06007f00,b'\xA5'*256);put(c,[code]*length);run(c,0x08083ffc)
  assert cpu.mem_read(0x06007f00,256)==original.mem_read(0x06007f00,256),(code,length)
checks['legacy_small_full']=len(mapped)*4
# CJK and mixed names check direct tile copies before the retained centering.
allcodes=list(struct.unpack_from('<180H',target,name['grid']));small=manifest['engine']['small_bitmap']
for code in sorted(set(allcodes[:120])):
 for length in range(1,5):
  codes=[code]*length;put(cpu,codes);cpu.mem_write(SP-0x128,b'\xA5'*0x128)
  run(cpu,0x08083ffc,stop=0x08084074)
  actualsp=cpu.reg_read(UC_ARM_REG_SP);buf=cpu.reg_read(UC_ARM_REG_R9)
  at=small+(code-512)*64
  assert cpu.reg_read(UC_ARM_REG_R8)==length
  assert cpu.mem_read(buf,256)==target[at:at+64]*length+b'\0'*(256-length*64)
  assert cpu.mem_read(actualsp+4,4)==b'\xA5'*4
  run(cpu,0x08083ffc) # full function returns (no lookup hang)
checks['cjk_small_with_guards']=len(set(allcodes[:120]))*4
for codes in [[0xffff],[name['default_ids'][0],0x10,0xffff,0x20],[]]:
 put(cpu,codes);run(cpu,0x08083ffc)
checks['invalid_or_empty_bounded']=3
# Full four-cell input banner, actual stock fixed-cell compositor and DMA.
ui=0x03007280;obj=0x02008000;cpu.mem_write(ui+0x14,struct.pack('<I',obj))
for codes in [name['default_ids']+[0x1d],allcodes[:4],[allcodes[80],allcodes[81],0x20,0x1d]]:
 cpu.mem_write(obj+0x224,struct.pack('<4H',*codes));cpu.mem_write(0x0600fbfc,b'\xA5'*520)
 run(cpu,0x080d349c)
 assert cpu.mem_read(0x0600fbfc,4)==b'\xA5'*4 and cpu.mem_read(0x0600fe00,4)==b'\xA5'*4
 data=cpu.mem_read(0x0600fc00,512)
 for n,code in enumerate(codes):
  if code<512:continue
  compact=code-512+0x4000
  at,first,w,stride=struct.unpack_from('<IHBB',target,manifest['engine']['descriptor']+compact*8)
  bits=target[at-BASE:at-BASE+stride];px=[(b>>z)&3 for b in bits for z in (6,4,2,0)]
  for y in range(16):
   for x in range(16):
    v=data[n*128+x//8*64+y*4+(x%8)//2];actual=(v>>((x&1)*4))&15
    expect=px[y*12+x-2]+1 if 2<=x<14 else 1
    assert actual==expect,(n,code,x,y,actual,expect)
checks['input_banner_pixels']=3*16*16
report={'status':'pass','cpu_model':'Unicorn TI925T ARMv4T instruction model; fixture DMA, not full GBA timing','rom_sha256':hashlib.sha256(target).hexdigest(),'checks':checks,'total':sum(checks.values()),'scope':'Actual ROM Thumb consumers, original centering and fixture DMA; not full save/playthrough evidence'}
(ROOT/'evidence/gba-name-tests.json').write_text(json.dumps(report,indent=2),'utf-8');print(json.dumps(report))
