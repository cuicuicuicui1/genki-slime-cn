"""Final source/translation/ID/ROM readback audit for the active GBA branch."""
from pathlib import Path
import json,sys,struct,hashlib,collections
from cn_codec import ROOT,SOURCE_SHA,BASE,CNCodec,same_controls
from build_cn import merge
from gba_plain_layout import apply_plain_profile
from gba_resident_layout import fit_resident_cells
from project_paths import SOURCE_PATH
source=SOURCE_PATH.read_bytes()
if hashlib.sha256(source).hexdigest()!=SOURCE_SHA:raise ValueError('Wrong source ROM')
target=(ROOT/'build/slime-cn.gba').read_bytes();m=json.loads((ROOT/'build/manifest.json').read_text('utf-8'))
assert hashlib.sha256(target).hexdigest()==m['target_sha256'];assert source[:192]==target[:192]
inv=json.loads((ROOT/'data/inventory.json').read_text('utf-8'));lookup={r['id']:r for r in inv};trans,rejected=merge(inv)
assert not rejected and len(trans)==2539
for r in inv:assert source[int(r['offset'],16):int(r['end'],16)].hex()==r['original_hex']
for key,row in trans.items():assert same_controls(lookup[key]['tokens'],row['tokens'])
ids=json.loads((ROOT/'build/font-map.json').read_text('utf-8'));registry=json.loads((ROOT/'data/gba-font-ids.json').read_text('utf-8'));assert registry==ids
codec=CNCodec(ids);counts=collections.Counter()
for r in m['records']:
 actual,end=codec.decode(target,r['offset'],lookup[r['id']]['format']);assert end==r['offset']+r['bytes'] and actual==r['tokens']
 if lookup[r['id']]['format']=='plain':
  compiled,profile=apply_plain_profile(lookup[r['id']],trans[r['id']]['tokens'],codec,source)
  normalized,_=codec.decode(codec.encode(compiled,'plain',compact=True),0,'plain')
  assert actual==normalized,('plain author/compiler/native mismatch',r['id'])
  assert r['layout'].get('fixed_window')==profile
 if lookup[r['id']]['format']=='small':
  compiled,profile=fit_resident_cells(lookup[r['id']],trans[r['id']]['tokens'],codec,source)
  expected,_=codec.decode(codec.encode(compiled,'small'),0,'small')
  assert actual==expected and r['layout'].get('resident_cells')==profile
 counts[(lookup[r['id']]['format'],r['layout'].get('font','original_profile'))]+=1
assert next(r for r in m['records'] if r['id']=='dialogue-7259A3')['layout']['font']=='clear16'
assert all(int(h['id'].split('-')[-1],16)>=0x714091 and int(h['id'].split('-')[-1],16)<0x714144 for h in m['holds'])
allowed=bytearray(len(source))
for row in m['write_regions']:
 a=row['offset'];b=min(a+row['length'],len(source))
 if a<len(source):allowed[a:b]=b'\1'*(b-a)
assert not any(a!=b and not allowed[i] for i,(a,b) in enumerate(zip(source,target)))
# Original small-font bitmaps and every stock main-font bitmap stay untouched.
assert target[0x73cae8:0x740ae8]==source[0x73cae8:0x740ae8]
for n in range(10):
 ptr,first,width,stride=struct.unpack_from('<IHBB',source,0x713eb8+n*8)
 end=(0x13,0x18,0x23,0x3d,0x66,0x97,0xce,0x10c,0x141,0x1b8)[n]
 count=end-first+1;at=ptr-BASE
 assert target[at:at+stride*count]==source[at:at+stride*count]
review=json.loads((ROOT/'data/review-overrides.json').read_text('utf-8'));assert len({r['id'] for r in review})==len(review)
# Review credit is attached to parent-accepted exact tokens, not worker counts.
ledger=json.loads((ROOT/'data/gba-review-ledger.json').read_text('utf-8'))
assert set(ledger['entries'])=={r['id'] for r in review}
for r in review:
 entry=ledger['entries'][r['id']]
 kwargs={'ensure_ascii':False}
 if entry['token_digest_encoding']=='json-utf8-compact':kwargs['separators']=(',',':')
 else:assert entry['token_digest_encoding']=='json-utf8-default-spaces'
 digest=hashlib.sha256(json.dumps(r['tokens'],**kwargs).encode()).hexdigest()
 assert entry['accepted_tokens_sha256']==digest,r['id']
 # Private provenance logs are summarized in the ledger; not a public runtime proof.
 # Original private logs are not distributed; this checks accepted-token digest only.
 if entry['stage'].startswith('v03'):pass
# Names are checked against actual current merged source identities.
name_groups=collections.defaultdict(set)
for key,row in trans.items():
 src=[t[1] for t in lookup[key]['tokens'] if isinstance(t,list) and t[0]=='NAME']
 dst=[t[1] for t in row['tokens'] if isinstance(t,list) and t[0]=='NAME']
 assert len(src)==len(dst)
 for a,b in zip(src,dst):name_groups[a].add(b)
conflicts={a:sorted(b) for a,b in name_groups.items() if len(b)>1};assert not conflicts,conflicts
name_audit={'identity_groups':len(name_groups),'conflict_groups':conflicts,'scope':'exact original NAME identities; not official Chinese-name certification'}
(ROOT/'data/gba-naming-audit.json').write_text(json.dumps(name_audit,ensure_ascii=False,indent=2),'utf8')
meta=m['engine']['speaker_label']
for r in m['records']:
 for t in r['tokens']:
  if isinstance(t,list) and t[0]=='NAME':
   width=sum(meta['advance_cn'] if c in codec.ids else meta['advance_legacy'] for c in codec.units(t[1],True))
   assert width<=meta['max_pixels'],('speaker width',r['id'],t[1],width)
report={'status':'pass','source_sha256':SOURCE_SHA,'target_sha256':m['target_sha256'],'source_inventory_records':len(inv),'draft_denominator':2539,'injected':len(m['records']),'reference_proven_records':m['referenced_records'],'source_controls_validated':len(trans),'final_readback_records':len(m['records']),'reviewed_records':len(review),'reviewed_dialogue':sum(r['id'].startswith('dialogue') for r in review),'reviewed_plain_labels':sum(r['id'].startswith('plain') for r in review),'layout_font_counts':{str(k):v for k,v in counts.items()},'stable_primary_glyphs':len(ids),'unchanged_original_header_and_font_bitmaps':True,'exact_declared_diff_only':True,'name_identity_audit':name_audit,'parent_review_ledger_exact_hashes':len(review),'speaker_label_font':meta,'scope_limit':'Format/readback/consistency checks do not prove complete precision translation or all windows/scenes.'}
(ROOT/'evidence/gba-final-audit.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),'utf-8');print(json.dumps(report,ensure_ascii=False))
