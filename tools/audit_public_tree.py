#!/usr/bin/env python3
"""Audit tracked and non-ignored files before publication; never inspects ignored ROMs."""
import json,re,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
files=subprocess.check_output(['git','-C',str(ROOT),'ls-files','--cached','--others','--exclude-standard','-z']).decode('utf-8').split('\0')
forbidden={'.gba','.gb','.gbc','.nds','.sfc','.smc','.sav','.srm','.sa1','.state','.bios','.dll','.so','.dylib','.bin','.pem','.key'}
errors=[]
for name in sorted(set(filter(None,files))):
 p=ROOT/name
 if p.suffix.lower() in forbidden or set(p.relative_to(ROOT).parts)&{'upstream','local-input','.venv','outputs','work'}:errors.append(name+': forbidden input/dependency')
 if not p.is_file():continue
 if p.stat().st_size>10*1024*1024:errors.append(name+': unexpectedly large')
 if p.suffix=='.bps':continue
 try:text=p.read_text('utf-8-sig')
 except UnicodeError:errors.append(name+': unreviewed binary');continue
 if re.search(r'[A-Za-z]:[\\/](?:Users|gamework|Codex|勇气史莱姆)',text) or re.search('/'+'Users'+r'/[^/]+/',text):errors.append(name+': personal path')
 # Split prefixes to avoid matching this scanner itself.
 prefixes=['gh'+'p_','github_'+'pat_','sk-'+'proj-']
 if any(re.search(re.escape(v)+r'[A-Za-z0-9_]{16,}',text) for v in prefixes):errors.append(name+': credential-like token')
 if 'BEGIN '+'PRIVATE KEY' in text:errors.append(name+': private key')
print(json.dumps({'status':'fail' if errors else 'pass','files':len(set(filter(None,files))),'errors':errors},indent=2))
raise SystemExit(bool(errors))
