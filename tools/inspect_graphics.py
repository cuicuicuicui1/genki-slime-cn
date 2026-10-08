#!/usr/bin/env python3
"""Extract requested archive resources from the owner's ROM, never downloads ROMs."""
import argparse,json,hashlib,sys
from pathlib import Path
from project import read_source,verify_upstream,UP
p=argparse.ArgumentParser(description=__doc__);p.add_argument('--rom',type=Path,required=True);p.add_argument('--ids',required=True,help='Comma-separated hex archive IDs, e.g. 2BD,2BE');p.add_argument('--out',type=Path,required=True);a=p.parse_args()
source=read_source(a.rom);verify_upstream();sys.path[:0]=[str(UP/'tools'),str(UP/'agent-tools')]
from gba_main_menu_graphics import resources
get,_=resources(source)
if a.out.exists():raise SystemExit('Choose a new output directory')
a.out.mkdir(parents=True);rows=[]
for text in a.ids.split(','):
 i=int(text,16)
 if not 0<=i<737:raise SystemExit('Archive ID outside 0..2E0')
 offset,stored,decoded=get(i);(a.out/f'resource-{i:03X}.bin').write_bytes(decoded)
 rows.append({'id':f'{i:03X}','offset_hex':f'{offset:X}','stored_bytes':stored,'decoded_bytes':len(decoded),'decoded_sha256':hashlib.sha256(decoded).hexdigest()})
(a.out/'resources.json').write_text(json.dumps(rows,indent=2)+'\n','utf-8');print(json.dumps(rows,indent=2))
