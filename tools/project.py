#!/usr/bin/env python3
"""Public project entry point. Fresh isolated rebuilds; never changes source ROM."""
import argparse,contextlib,hashlib,json,os,shutil,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
LOCK=json.loads((ROOT/'dependencies.lock.json').read_text('utf-8'))
UP=ROOT/'upstream/Translimeation'
def sha(b):return hashlib.sha256(b).hexdigest()
def canonical(x):return json.dumps(x,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode('utf-8')
def write_json(p,x):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n','utf-8')
def run(*args):return subprocess.check_output(args,text=True).strip()
def verify_upstream():
 if not UP.exists():raise ValueError('Run: python tools/project.py bootstrap')
 if run('git','-C',str(UP),'rev-parse','HEAD')!=LOCK['upstream']['commit']:raise ValueError('Upstream revision mismatch')
 if run('git','-C',str(UP),'status','--porcelain','--untracked-files=no'):raise ValueError('Modified upstream dependency')
def bootstrap():
 if not UP.exists():
  UP.parent.mkdir(parents=True,exist_ok=True)
  subprocess.run(['git','clone','--no-checkout',LOCK['upstream']['url'],str(UP)],check=True)
  subprocess.run(['git','-C',str(UP),'checkout','--detach',LOCK['upstream']['commit']],check=True)
 verify_upstream();print('Pinned upstream dependency ready (not part of this repository)')
def read_source(path):
 b=path.read_bytes()
 if len(b)!=0x800000 or sha(b)!=LOCK['source_sha256']:raise ValueError('Wrong ROM: exact unmodified 8MiB A9KJ source SHA256 required')
 return b
def extract(source):
 verify_upstream();sys.path.insert(0,str(UP/'tools'))
 import extract_text
 # Public interface accepts precisely our independently verified dump, not arbitrary ROMs.
 extract_text.SHA256=LOCK['source_sha256']
 records,report=extract_text.extract(source,UP)
 return records,report
@contextlib.contextmanager
def staged_project(out):
 """Existing modules use ROOT-relative assets. Stage only a new build directory."""
 shutil.copytree(ROOT/'data',out/'data')
 shutil.copytree(ROOT/'assets',out/'assets')
 shutil.copytree(ROOT/'tools',out/'tools',ignore=shutil.ignore_patterns('__pycache__'))
 (out/'upstream').mkdir();shutil.copytree(UP,out/'upstream/Translimeation',ignore=shutil.ignore_patterns('.git','__pycache__'))
 (out/'build').mkdir();(out/'evidence').mkdir();(out/'work').mkdir()
 yield out

def compose_assets(stage,source,rom,manifest):
 from gba_resident_font12 import candidate
 from gba_main_menu_graphics import build_candidate
 from gba_resident_scroll12 import extend as redraw
 from gba_town_resident_graphics import extend as town
 from gba_resident_obj_labels import extend as labels
 from gba_resident_status_cards import extend as cards
 ids=json.loads((stage/'build/font-map.json').read_text('utf-8'))
 contract={'rom':sha(rom),'manifest':sha(canonical(manifest)),'registry':sha(canonical(ids))}
 rom,m1=candidate(rom,manifest,ids,input_contract=contract)
 rom,m2,_,_,_=build_candidate(rom,m1)
 rom,m3=redraw(rom,m1,m2,source)
 rom,m4,_=town(rom,m3['append_end'],expected_baseline_sha=sha(rom))
 rom,m5,_=labels(rom,m4['append_end'],backplate=True,font_px=16,expected_baseline_sha=sha(rom))
 rom,m6,_=cards(rom,m5['append_end'],m4,expected_baseline_sha=sha(rom))
 profiles={'resident12':m1,'main_menu':m2,'resident_redraw':m3,'town_menus':m4,'resident_OBJ':m5,'resident_cards':m6}
 regions=[{'offset':m1['hook_offset'],'length':8,'purpose':'resident12'},
          {'offset':m2['hook'],'length':8,'purpose':'main_menu'},
          {'offset':m2['caption_hook'],'length':8,'purpose':'area_captions'},
          {'offset':m3['hook'],'length':8,'purpose':'resident_redraw'},
          {'offset':m4['hook'],'length':m4['hook_bytes'],'purpose':'town_menus'},
          {'offset':m5['hook_literal'],'length':4,'purpose':'resident_OBJ'}]
 regions.extend({'offset':x['entry'],'length':8,'purpose':'main_menu_map'} for x in m2['map_entries'])
 regions.extend({'offset':x['hook'],'length':x['hook_bytes'],'purpose':'resident_card'} for x in m6['card_profiles'])
 manifest['write_regions'].extend(regions)
 allowed=bytearray(len(source))
 for x in manifest['write_regions']:
  a=x['offset'];b=min(a+x['length'],len(source))
  if a<len(source):allowed[a:b]=b'\1'*(b-a)
 unexpected=[i for i,(a,b) in enumerate(zip(source,rom)) if a!=b and not allowed[i]]
 if unexpected:raise ValueError('Unexpected original-ROM diff: '+str(unexpected[:20]))
 return rom,profiles,m6['append_end']
def build(args):
 source=read_source(args.rom.resolve());verify_upstream()
 out=args.out.resolve()
 if out.exists():raise ValueError('Output directory exists; choose a NEW --out (no overwrite)')
 if out==ROOT or out in ROOT.parents:raise ValueError('Unsafe output directory')
 records,coverage=extract(source);out.mkdir(parents=True)
 # Run child interpreter so staged imports cannot retain modules from another build.
 with staged_project(out):
  write_json(out/'data/inventory.json',records);write_json(out/'source-coverage.json',coverage)
  if args.translations:
   author=json.loads((out/'data/review-overrides.json').read_text('utf-8'));index={r['id']:r for r in author}
   edits=json.loads(args.translations.resolve().read_text('utf-8-sig'))
   if not isinstance(edits,list):raise ValueError('Translations must be a JSON list of {id,tokens}')
   if len({r['id'] for r in edits})!=len(edits):raise ValueError('Duplicate translation IDs')
   for row in edits:
    if row['id'] not in index:raise ValueError('Unknown reviewed ID: '+row['id'])
    index[row['id']]=row
   write_json(out/'data/review-overrides.json',[index[r['id']] for r in author])
  env=os.environ.copy();env['PYTHONUTF8']='1';env['GENKI_SOURCE_ROM']=str(args.rom.resolve())
  with (out/'build.log').open('w',encoding='utf-8') as log:
   subprocess.run([sys.executable,str(out/'tools/build_cn.py'),'--rom',str(args.rom.resolve())],env=env,stdout=log,stderr=subprocess.STDOUT,check=True)
  bare=json.loads((out/'build/manifest.json').read_text('utf-8'))
  if bare['rejected']:raise ValueError('Rejected translation records; inspect build.log; no final artifact published')
  if any(not 0x714091<=int(h['id'].split('-')[-1],16)<0x714144 for h in bare['holds']):raise ValueError('Unexpected held text record; inspect build.log')
  cmd=[sys.executable,str(ROOT/'tools/project.py'),'_compose','--stage',str(out),'--rom',str(args.rom.resolve()),'--profile',args.profile]
  with (out/'assets.log').open('w',encoding='utf-8') as log:subprocess.run(cmd,env=env,stdout=log,stderr=subprocess.STDOUT,check=True)
  target=(out/'slime-cn.gba').read_bytes()
  if not args.translations and args.profile=='v20' and sha(target)!=LOCK['v20_sha256']:raise ValueError('Exact v20 reproduction failed')
  # Fresh patched output is a development build unless it equals the verified release.
  sys.path.insert(0,str(ROOT/'tools'));from bps_patch import make,apply
  patch=make(source,target,b'genki-slime-cn source build');assert apply(source,patch)==target
  (out/'genki-slime-cn.bps').write_bytes(patch)
  write_json(out/'build-report.json',{'source_sha256':sha(source),'target_sha256':sha(target),'patch_sha256':sha(patch),'profile':args.profile,'exact_v20':sha(target)==LOCK['v20_sha256'],'modified_authoring':bool(args.translations),'upstream_commit':LOCK['upstream']['commit'],'validation':'structural build gates + final encoded readback + BPS replay; NOT natural playthrough'})
 print(json.dumps(json.loads((out/'build-report.json').read_text('utf-8')),ensure_ascii=False,indent=2))
def compose(args):
 stage=args.stage.resolve();sys.path[:0]=[str(stage/'tools'),str(stage/'upstream/Translimeation/tools'),str(stage/'upstream/Translimeation/agent-tools')]
 source=read_source(args.rom.resolve());manifest=json.loads((stage/'build/manifest.json').read_text('utf-8'));rom=(stage/'build/slime-cn.gba').read_bytes()
 if args.profile!='text-only':rom,profiles,end=compose_assets(stage,source,rom,manifest);write_json(stage/'asset-profiles.json',profiles);manifest['appended_used']=end-0x800000
 if args.profile=='ui-candidate':
  from gba_user_ui_v21 import build as ui
  rom,meta=ui(source,rom,manifest);write_json(stage/'ui-candidate.json',meta)
  manifest['appended_used']=meta['append_end']-0x800000
  manifest['write_regions'].extend({'offset':r['offset'],'length':r['bytes'],'purpose':r['tag']} for r in meta['writes'])
  from cn_codec import CNCodec
  codec=CNCodec(json.loads((stage/'build/font-map.json').read_text('utf-8')))
  record=next(r for r in manifest['records'] if r['id']=='plain-713F08')
  record['offset']=meta['choice']['offset'];record['bytes']=len(bytes.fromhex(meta['choice']['encoded_hex']))
  record['tokens']=codec.decode(rom,record['offset'],'plain')[0]
  record['layout']['ui_candidate_padding']=meta['choice']
 manifest['stage']='public-source-'+args.profile;manifest['target_sha256']=sha(rom)
 (stage/'slime-cn.gba').write_bytes(rom);write_json(stage/'manifest.json',manifest)
 print(sha(rom))
def main():
 parser=argparse.ArgumentParser(description=__doc__);sub=parser.add_subparsers(dest='command',required=True)
 sub.add_parser('bootstrap')
 e=sub.add_parser('extract');e.add_argument('--rom',type=Path,required=True);e.add_argument('--out',type=Path,required=True)
 b=sub.add_parser('build');b.add_argument('--rom',type=Path,required=True);b.add_argument('--out',type=Path,required=True);b.add_argument('--translations',type=Path);b.add_argument('--profile',choices=['v20','text-only','ui-candidate'],default='v20')
 c=sub.add_parser('_compose',help=argparse.SUPPRESS);c.add_argument('--stage',type=Path,required=True);c.add_argument('--rom',type=Path,required=True);c.add_argument('--profile',required=True)
 args=parser.parse_args()
 if args.command=='bootstrap':bootstrap()
 elif args.command=='build':build(args)
 elif args.command=='_compose':compose(args)
 else:
  source=read_source(args.rom);records,report=extract(source)
  if args.out.exists():raise ValueError('Output exists (no overwrite)')
  args.out.mkdir(parents=True);write_json(args.out/'inventory.json',records);write_json(args.out/'coverage.json',report)
  print('Extracted',len(records),'source records, byte-for-byte roundtrip')
if __name__=='__main__':
 try:main()
 except (ValueError,subprocess.CalledProcessError) as exc:raise SystemExit(str(exc))

