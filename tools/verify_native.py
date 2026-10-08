#!/usr/bin/env python3
"""Isolated optional source+target audit and ARMv4T native consumer tests."""
import argparse,hashlib,json,os,shutil,subprocess,sys
from pathlib import Path
from project import read_source
p=argparse.ArgumentParser(description=__doc__);p.add_argument('--rom',type=Path,required=True);p.add_argument('--build',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args()
source=read_source(a.rom.resolve());b=a.build.resolve();out=a.out.resolve()
if out.exists():raise SystemExit('Output exists; choose a new directory')
m=json.loads((b/'manifest.json').read_text('utf-8'));target=(b/'slime-cn.gba').read_bytes()
if hashlib.sha256(target).hexdigest()!=m['target_sha256']:raise SystemExit('Target/manifest mismatch')
out.mkdir(parents=True)
for d in ['tools','data','assets','upstream']:shutil.copytree(b/d,out/d,ignore=shutil.ignore_patterns('__pycache__','.git'))
# Use verifier source from the repository, not from an older build snapshot.
root=Path(__file__).resolve().parents[1]
for f in ['test_engine.py','test_gba_name.py','audit_gba.py']:shutil.copyfile(root/'tools'/f,out/'tools'/f)
(out/'build').mkdir();(out/'evidence').mkdir()
(out/'build/slime-cn.gba').write_bytes(target);shutil.copyfile(b/'manifest.json',out/'build/manifest.json');shutil.copyfile(b/'build/font-map.json',out/'build/font-map.json')
env=os.environ.copy();env['PYTHONUTF8']='1';env['GENKI_SOURCE_ROM']=str(a.rom.resolve());reports=[]
for f in ['audit_gba.py','test_engine.py','test_gba_name.py']:
 with (out/(f+'.log')).open('w',encoding='utf-8') as log:
  result=subprocess.run([sys.executable,str(out/'tools'/f)],cwd=out,env=env,stdout=log,stderr=subprocess.STDOUT)
 reports.append({'script':f,'exit_code':result.returncode})
report={'target_sha256':m['target_sha256'],'source_sha256':hashlib.sha256(source).hexdigest(),'scripts':reports,'scope':'exact author-token digests/readback/static write bounds + ARMv4T dialogue/plain/small/name consumers; controlled tests only, no natural playthrough'}
(out/'summary.json').write_text(json.dumps(report,indent=2)+'\n','utf-8');print(json.dumps(report,indent=2));raise SystemExit(any(r['exit_code'] for r in reports))
