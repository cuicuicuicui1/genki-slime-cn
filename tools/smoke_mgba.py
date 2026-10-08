"""Isolated fresh HLE early-route smoke test, never uses a user save or BIOS."""
import argparse,hashlib,json,time
from pathlib import Path
from libretro_frontend import Core
p=argparse.ArgumentParser();p.add_argument('--rom',type=Path,required=True);p.add_argument('--core',type=Path,required=True);p.add_argument('--out',type=Path,required=True);p.add_argument('--frames',type=int,default=7000);a=p.parse_args()
if a.out.exists():raise SystemExit('Choose a NEW --out (no overwrite)')
a.out.mkdir(parents=True);c=Core(a.rom,a.core,a.out/'hle-system');t=time.time();seen=[]
try:
 for f in range(1,a.frames+1):
  keys=[]
  if 600<=f<620 or 820<=f<840:keys=['start']
  if 3100<=f<3108:keys=['start']
  if f>=1000 and f%90<8:keys=['a']
  c.run(keys)
  if f%150==0:c.frame.save(a.out/f'f{f:05d}.png')
 c.frame.save(a.out/'end.png')
 report={**c.info,'rom_sha256':hashlib.sha256(c.data).hexdigest(),'frames':a.frames,'seconds':time.time()-t,'bios':'HLE; no external BIOS','RAM_writes':False,'save_loaded':False,'scope':'early deterministic natural-input route; NOT full playthrough or save compatibility'}
 (a.out/'run.json').write_text(json.dumps(report,indent=2)+'\n','utf-8');print(json.dumps(report,indent=2))
finally:c.close()
