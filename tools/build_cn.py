"""Deterministic local source-ROM gated build. No upstream English patch is used.
Merges validated translated records, preserves all non-layout controls, appends
fonts and strings in a 16MiB ROM, and audits every touched pointer/code range.
"""
import argparse,json,hashlib,struct,sys,re,collections,os
from pathlib import Path
from cn_codec import ROOT,BASE,SOURCE_SHA,CNCodec,translated_chars,same_controls
from cn_engine import engine
from gba_name_engine import name_engine, name_font_rows
from gba_graphics_engine import graphics_engine
from gba_ui_v03 import tutorial_engine, file_ui_engine
from gba_text_layout import reflow
from gba_file_labels import file_label_engine
from gba_plain_layout import apply_plain_profile
from gba_resident_layout import fit_resident_cells
from slime_gfx import Decompressor

# Never replace player-name grids/validation/lookups using variable-length CN.
UNSAFE_PLAIN=(0x714091,0x714144)
RELOCATABLE={'dialogue-table','credits-table','resident-name-table','item-label-table','window-descriptor','code-literal-candidate'}

def source_entities(source,canonical,protected):
 # One longest-match source pass: スーラン is a town, not the shorter NPC
 # スーラ. Matching only 'ja in source' rewrote the reviewed town back to NPC.
 if set(canonical)&set(protected):raise ValueError('Source entity cannot be both person and protected nonperson')
 keys=sorted(set(canonical)|set(protected),key=lambda k:(-len(k),k))
 if not keys:return set(),set()
 if any(not k for k in keys):raise ValueError('Empty source entity')
 hits={m.group() for m in re.finditer('|'.join(re.escape(k) for k in keys),source)}
 return hits&set(canonical),hits&set(protected)


def normalize_name_mentions(source,text,canonical,variants,body_rules,protected=None):
 protected=protected or {}
 mentioned,nonpersons=source_entities(source,canonical,protected)
 protected_cn={protected[k] for k in nonpersons}

 # Source-guarded full forms resolve ordinal suffixes before ordinary aliases.
 # In particular スラーリン８世 must not become 史拉林八世８世.
 for rule in body_rules:
  if rule['source_contains'] in source and not mentioned&set(rule.get('exclude_person_mentions',[])):
   text=re.sub(rule['candidate_regex'],rule['replacement'],text)
 # One pass, longest-first with lexical ties: never feed a newly inserted
 # canonical name back into a shorter alias. Sequential replacement over sets
 # produced both duplicate 八世 and different ROM bytes by PYTHONHASHSEED.
 aliases={}
 for ja in sorted(canonical,key=lambda k:(-len(k),k)):
  if ja not in mentioned:continue
  for old in sorted(variants.get(ja,set())|{canonical[ja]},key=lambda k:(-len(k),k)):
   if not old:raise ValueError('Empty name alias '+ja)
   if old in protected_cn:continue
   if old in aliases and aliases[old]!=canonical[ja]:raise ValueError('Ambiguous source-guarded alias '+old)
   aliases[old]=canonical[ja]
 if not aliases:return text
 pattern='|'.join(re.escape(k) for k in sorted(aliases,key=lambda k:(-len(k),k)))
 return re.sub(pattern,lambda m:aliases[m.group()],text)



def small_name_identity(text,canonical):
 # Resident strings include fixed stock space suffixes. Match the complete
 # source name only, not an arbitrary substring or source-leading whitespace.
 key=text.rstrip(' \u3000')
 return key if key in canonical else None


def canonical_small_name(source,target,canonical):
 key=small_name_identity(source,canonical)
 if key is None:return None
 # Preserve the authored destination padding; do not guess/resize an 8px
 # caller allocation here. Capacity remains enforced by the real build gate.
 tail=target[len(target.rstrip(' \u3000')):]
 return canonical[key]+tail


def merge(inventory,pilot=False):
 lookup={r['id']:r for r in inventory};translations={};rejected=[]
 files=[ROOT/'data/auxiliary-translations.json']
 if pilot:files=[ROOT/'data/pilot.json']
 if (ROOT/'data/review-overrides.json').exists():files.append(Path(os.environ.get('GENKI_AUTHORING',str(ROOT/'data/review-overrides.json'))))
 for path in files:
  try:rows=json.loads(path.read_text(encoding='utf-8-sig'))
  except Exception as e:rejected.append({'file':str(path),'reason':str(e)});continue
  if not isinstance(rows,list):rejected.append({'file':str(path),'reason':'Expected JSON list'});continue
  for row in rows:
   key=row.get('id');old=lookup.get(key)
   if not old or not same_controls(old['tokens'],row.get('tokens',[])):
    rejected.append({'file':str(path),'id':key,'reason':'Unknown ID / control or structure changed'});continue
   if key in translations and translations[key]['tokens']!=row['tokens'] and path!=files[-1]:
    raise ValueError('Duplicate conflicting translation '+key)
   translations[key]=row
 norm=json.loads((ROOT/'data/term-normalization.json').read_text(encoding='utf-8'))
 for row in translations.values():
  for n,t in enumerate(row['tokens']):
   if isinstance(t,str):
    for old,new in norm.items():t=t.replace(old,new)
    row['tokens'][n]=t
   elif t[0]=='NAME':
    for old,new in norm.items():t[1]=t[1].replace(old,new)
 canonical_path=ROOT/'data/canonical-names.json'
 if canonical_path.exists():
  canonical=json.loads(canonical_path.read_text(encoding='utf-8'))
  rules_path=ROOT/'data/gba-name-body-rules.json'
  body_profile=json.loads(rules_path.read_text('utf8')) if rules_path.exists() else {}
  body_rules=body_profile.get('rules',[]);protected=body_profile.get('protected_non_person_entities',{})
  variants={ja:set() for ja in canonical}
  for key,row in translations.items():
   for src,dst in zip(lookup[key]['tokens'],row['tokens']):
    if isinstance(src,list) and src[0]=='NAME' and src[1] in canonical:variants[src[1]].add(dst[1])
    elif lookup[key]['format']=='small' and isinstance(src,str):
     identity=small_name_identity(src,canonical)
     if identity is not None:variants[identity].add(dst.rstrip(' \u3000'))
  for key,row in translations.items():
   for n,(src,dst) in enumerate(zip(lookup[key]['tokens'],row['tokens'])):
    if isinstance(src,list) and src[0]=='NAME' and src[1] in canonical:row['tokens'][n]=['NAME',canonical[src[1]]]
    elif lookup[key]['format']=='small' and isinstance(src,str) and small_name_identity(src,canonical) is not None:row['tokens'][n]=canonical_small_name(src,dst,canonical)
    elif isinstance(src,str) and isinstance(dst,str):
     row['tokens'][n]=normalize_name_mentions(src,dst,canonical,variants,body_rules,protected)
 return translations,rejected

def build(rompath,pilot=False,experimental_menu_fonts=False,experimental_town_menus=False,experimental_resident_objs=False,experimental_resident_cards=False):
 if experimental_resident_cards:experimental_resident_objs=True
 if experimental_resident_objs:experimental_town_menus=True
 if experimental_town_menus:experimental_menu_fonts=True
 source=rompath.read_bytes()
 if len(source)!=0x800000 or hashlib.sha256(source).hexdigest()!=SOURCE_SHA:raise ValueError('Wrong source ROM: exact local SHA256 required')
 if pilot and experimental_menu_fonts:raise ValueError('Experimental complete-menu profiles cannot be combined with pilot')
 inventory=json.loads((ROOT/'data/inventory.json').read_text(encoding='utf-8'))
 for rec in inventory:
  a=int(rec['offset'],16);b=int(rec['end'],16)
  if source[a:b].hex()!=rec['original_hex']:raise ValueError('Stale source inventory '+rec['id'])
 if any(t==['NOP'] for rec in inventory if rec['format']=='dialogue' for t in rec['tokens']):raise ValueError('Original NOP conflicts with CN escape')
 trans,rejected=merge(inventory,pilot)
 credit_rows=json.loads((ROOT/'data/credits-cn.json').read_text(encoding='utf-8')) if (ROOT/'data/credits-cn.json').exists() and not pilot else []
 font_rows=list(trans.values())+name_font_rows()+[{'tokens':line['tokens']} for rec in credit_rows for line in rec['lines']]
 codec=CNCodec(translated_chars(font_rows))
 result=bytearray(source+b'\xff'*0x800000);cursor=0x800000;regions=[]
 def append(data,align=4):
  nonlocal cursor
  cursor=(cursor+align-1)&~(align-1);start=cursor;result[start:start+len(data)]=data;cursor+=len(data)
  if cursor>len(result):raise ValueError('ROM append overflow')
  return start
 writes,eng=engine(source,codec,append)
 name_writes,name_info=name_engine(source,codec,eng,append)
 writes.extend(name_writes);eng['name_entry']=name_info
 gfx_writes,gfx_info=graphics_engine(source,append)
 tutorial_writes,tutorial_info=tutorial_engine(source,append);gfx_writes.extend(tutorial_writes);gfx_info['records'].append(tutorial_info)
 label_writes,label_meta=file_label_engine(source,append,gateway=False)
 label_atlas=Decompressor(result,label_meta['cn_atlas_stream']).decompress()[0]
 ui_writes,ui_records,ui_meta=file_ui_engine(source,append,atlas_override=label_atlas,reserved_tile_ids=label_meta['allocated_slots'],direct_pairs=[label_meta['gateway_pair']])
 gfx_writes.extend(label_writes);gfx_writes.extend(ui_writes);gfx_info['records'].extend(ui_records);gfx_info['file_ui_gateway']=ui_meta;gfx_info['file_labels']=label_meta
 gfx_info['status']='localized CJK name grids/panel, two-consumer operation tutorial and six deletion/sleep instruction maps; adventure-book header and empty-record variantA native16; title logo, command OBJ and other graphics still incomplete'
 writes.extend(gfx_writes);eng['graphics']=gfx_info
 for offset,data,name in writes:result[offset:offset+len(data)]=data;regions.append({'offset':offset,'length':len(data),'purpose':name})
 accepted=[];holds=[];orphans=[];mapped={};pointer_writes=[]
 for rec in inventory:
  key=rec['id']
  if key not in trans:continue
  pos=int(rec['offset'],16);kind=rec['format'];tokens=trans[key]['tokens']
  if kind=='plain' and UNSAFE_PLAIN[0]<=pos<UNSAFE_PLAIN[1]:
   holds.append({'id':key,'reason':'Special name-entry patch handles default/comparison; legacy reserved names, symbols and lookup deliberately preserved'});continue
  if kind not in ('dialogue','plain','small'):holds.append({'id':key,'reason':'Unsupported consumer'});continue
  interactive=any(isinstance(t,list) and t[0] in ('NAME','SHOW-PROMPT','WAIT-INPUT','YES-NO') for t in rec['tokens'])
  try:
   compact=False
   if kind=='dialogue':
    try:tokens,layout=reflow(tokens,codec,interactive=interactive)
    except ValueError as e:
     if str(e)!='Noninteractive line overflow requires window profile':raise
     tokens,layout=reflow(tokens,codec,interactive=interactive,compact=True);compact=True
    layout['font']='compact12' if compact else 'clear16'
   else:
    compact=kind=='plain'
    layout={'font':'compact12' if compact else 'small8'}
    if kind=='plain':
     tokens,profile=apply_plain_profile(rec,tokens,codec,source)
     if profile is not None:layout['fixed_window']=profile
   if kind=='small':
    tokens,resident_profile=fit_resident_cells(rec,tokens,codec,source)
    layout['resident_cells']=resident_profile
   if any(isinstance(t,list) and t[0]=='NAME' and len(list(codec.units(t[1],True)))>9 for t in tokens):raise ValueError('Speaker name longer than 9 tiles')
   data=codec.encode(tokens,kind,compact=compact)
  except ValueError as e:holds.append({'id':key,'reason':str(e)});continue
  target=append(data,1);refs=rec['references'];wrote=0
  for ref in refs:
   if ref['kind'] not in RELOCATABLE:continue
   offset=int(ref['offset'],16)
   if struct.unpack_from('<I',source,offset)[0]!=BASE+pos:raise ValueError('Pointer mismatch '+str(ref))
   value=struct.pack('<I',BASE+target)
   if offset in mapped and mapped[offset]!=value:raise ValueError('Pointer collision')
   mapped[offset]=value;result[offset:offset+4]=value;pointer_writes.append(offset);wrote+=1
  if not wrote:orphans.append(key)
  actual,end=codec.decode(result,target,kind)
  # Compare with encode/decode-normalized authoring (adjacent strings coalesced).
  expected,_=codec.decode(data,0,kind)
  if actual!=expected or end-target!=len(data):raise ValueError('Final-ROM readback mismatch '+key)
  accepted.append({'id':key,'offset':target,'bytes':len(data),'reference_count':wrote,'layout':layout,'tokens':expected})
 credit_records=[];credit_index={r['id']:r for r in inventory if r['format']=='credits'}
 for row in credit_rows:
  old=credit_index[row['id']];lines=row['lines']
  if len(lines)!=len(old['tokens']):raise ValueError('Credit line count changed')
  data=bytearray()
  for n,(a,b) in enumerate(zip(old['tokens'],lines)):
   if any(a[k]!=b[k] for k in ['tile_row','x','separator']):raise ValueError('Credit coordinates changed')
   encoded=codec.encode(b['tokens'],'plain')[:-1]
   b['encoded_bytes']=len(encoded)
   if len(encoded)>31:raise ValueError('Credits stack line exceeds 31 encoded bytes')
   pixels=sum(codec.width(c)+1 for t in b['tokens'] if isinstance(t,str) for c in codec.units(t))-1
   if pixels>240:raise ValueError('Credit line exceeds 240px')
   # Payload bytes >=16 ensure the stock 00/02 copy scanner cannot split a glyph.
   if any(v in (0,2) for v in encoded):raise ValueError('Embedded credit delimiter')
   data+=bytes([b['tile_row'],255 if b['x']=='center' else b['x']])+encoded+bytes([b['separator']])
  target=append(data,1)
  for ref in old['references']:
   if ref['kind'] not in ('credits-table','dialogue-table'):continue
   offset=int(ref['offset'],16)
   if struct.unpack_from('<I',source,offset)[0]!=BASE+int(old['offset'],16):raise ValueError('Credit pointer mismatch')
   result[offset:offset+4]=struct.pack('<I',BASE+target);pointer_writes.append(offset)
  credit_records.append({'id':old['id'],'offset':target,'bytes':len(data),'lines':lines})
 regions.extend({'offset':o,'length':4,'purpose':'text-pointer'} for o in sorted(set(pointer_writes)))
 # Compare exact diff against the declared original-ROM writes, not a loose area.
 allowed=bytearray(len(source))
 for reg in regions:
  a=reg['offset'];b=min(a+reg['length'],len(source))
  if a<len(source):allowed[a:b]=b'\1'*(b-a)
 unexpected=[i for i,(a,b) in enumerate(zip(source,result)) if a!=b and not allowed[i]]
 if unexpected:raise ValueError('Unexpected diff '+str(unexpected[:20]))
 (ROOT/'build/slime-cn.gba').write_bytes(result)
 (ROOT/'build/font-map.json').write_text(json.dumps(codec.ids,ensure_ascii=False,indent=2),encoding='utf-8')
 manifest={'stage':'experimental-text-build-not-release','source_sha256':SOURCE_SHA,'target_sha256':hashlib.sha256(result).hexdigest(),'source_size':len(source),'target_size':len(result),'appended_used':cursor-0x800000,'engine':eng,'translated_submitted':len(trans),'injected_records':len(accepted),'referenced_records':sum(x['reference_count']>0 for x in accepted),'rejected':rejected,'holds':holds,'unreferenced_records':orphans,'write_regions':regions,'records':accepted,'credits':credit_records,'credits_status':'role labels and three verified series creators; other staff kana preserved','scope_remaining':['full-game contextual prose/proper-name/voice cross-check after source-record acceptance','graphics/tilemap Japanese','unknown staff-name spellings in credits','battery-save/legacy saved-name natural-scene compatibility','remaining special-window/dynamic-text and natural8px-list layout verification','full playthrough and hardware']}
 # Public project: asset stages are composed by project.py from this fresh text build.
 (ROOT/'build/manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
 print(json.dumps({k:v for k,v in manifest.items() if k not in ('records','credits','write_regions','holds','rejected','unreferenced_records')},ensure_ascii=False));print('holds',len(holds),'rejected',len(rejected))
 return manifest

if __name__=='__main__':
 a=argparse.ArgumentParser();a.add_argument('--rom',type=Path,required=True);args=a.parse_args();build(args.rom)
