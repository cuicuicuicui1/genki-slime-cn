"""Source-bound v21 fixes for user-reported file-command OBJ and yes/no layout.
Builds a new candidate from exact delivered v20; does not touch user saves,
font IDs, author prose, the activity/frozen build, or original ROM.
"""
from pathlib import Path
import hashlib,json,struct,sys
from PIL import Image,ImageFilter
from cn_codec import ROOT,BASE,SOURCE_SHA,CNCodec
from cn_engine import bitmap,load_bdf
from gba_main_menu_graphics import resources,ARCHIVE
from gba_graphics_engine import literal
from gba_resident_obj_labels import encode_parts,decode_parts
V20_SHA='b658e3bea80ce1deb024298583d5743332bdbb5101109bcdf0d1404501c9bde0'
FILE_ARCHIVE_LITERAL=0xD6104
YESNO_POINTER=0x73840C
APPEND_START=9868012
TILE_ID=0x219
TEMPLATE_ID=0x21B

def digest(b):return hashlib.sha256(b).hexdigest()

def file_assets(source):
 get,_=resources(source);oldtiles=get(TILE_ID)[2];oldtemplates=get(TEMPLATE_ID)[2]
 assert len(oldtiles)==8192 and len(oldtemplates)==2262
 # Preserve all hand/icon art and tail tiles208..255. Private Chinese tiles only
 # use the original command-letter area0..207; no global archive mutation.
 atlas=bytearray(oldtiles);atlas[:208*32]=bytes(208*32)
 template=bytearray(oldtemplates);next_tile=0;memo={};profiles=[]
 font=load_bdf(ROOT/'assets/fonts/fusion12/fusion-pixel-12px-monospaced-zh_hans.bdf')
 def piece(text):
  nonlocal next_tile
  if text in memo:return memo[text]
  w=32 if len(text)==2 else 16
  im=Image.new('P',(w,16),0)
  for i,ch in enumerate(text):
   glyph=bitmap(ch,font,12);mask=Image.new('L',(w,16),0)
   for y in range(16):
    for x in range(12):
     if glyph.getpixel((x,y)):mask.putpixel((i*16+2+x,y),255)
   outer=mask.filter(ImageFilter.MaxFilter(3))
   for y in range(16):
    for x in range(w):
     if outer.getpixel((x,y)):im.putpixel((x,y),9)
     if mask.getpixel((x,y)):im.putpixel((x,y),1)
  count=w//8*2
  if next_tile+count>208:raise ValueError('File command original tile budget exceeded')
  t=next_tile;next_tile+=count
  part=[(t,0,w)];atlas[:]=encode_parts(atlas,im,part)
  assert decode_parts(atlas,part,w).tobytes()==im.tobytes()
  memo[text]=(t,w)
  return t,w
 def label(i):
  if 1<=i<=8:return '是'
  if 9<=i<=16:return '否'
  if 17<=i<=21:return '开始冒险'
  if 22<=i<=26:return '复制'
  if 27<=i<=31:return '睡眠模式\n开'
  if 32<=i<=36:return '睡眠模式\n关'
  if 37<=i<=41:return '通信'
  if 42<=i<=46:return '删除'
  if 47<=i<=51:return '说明'
  return None
 anim,n=struct.unpack_from('<HH',template);assert n==60
 for i in range(1,52):
  off=4+struct.unpack_from('<H',template,4+i*2)[0];oldn=struct.unpack_from('<H',template,off)[0]
  oldparts=[struct.unpack_from('<HHH',oldtemplates,off+2+j*6) for j in range(oldn)]
  text=label(i);parts=[]
  for line_no,line in enumerate(text.split('\n')):
   # Native 12px glyph in16px cell with original white fill/dark outline;
   # preserve template palette variants and two-row sleep layout.
   x=-len(line)*8; y=(-15 if line_no==0 else -1) if '\n' in text else -8
   palette=(oldparts[0][2]>>12)&15
   if 18<=i<=21 or 23<=i<=26 or 38<=i<=41 or 43<=i<=46 or 48<=i<=51:
    # Keep the frame's actual palette selection; fine bobbing is bounded1px.
    y+=max(-1,min(1,(oldparts[0][0]&255)-248 if (oldparts[0][0]&255)>=240 else 0))
   for a in range(0,len(line),2):
    t,w=piece(line[a:a+2]);shape=1 if w==32 else 0;size=2 if w==32 else 1
    attr0=(y&255)|(shape<<14)
    attr1=(x&511)|(size<<14)
    attr2=(palette<<12)|t
    parts.append((attr0,attr1,attr2));x+=w
  assert len(parts)<=oldn,(i,len(parts),oldn)
  struct.pack_into('<H',template,off,len(parts))
  for j,part in enumerate(parts):struct.pack_into('<HHH',template,off+2+j*6,*part)
  profiles.append({'template':i,'text':text,'old_parts':oldn,'new_parts':len(parts),'offset':off})
 # The original pointer directory and animation program are unchanged.
 assert template[:124]==oldtemplates[:124]
 assert template[4+anim:]==oldtemplates[4+anim:]
 assert atlas[208*32:]==oldtiles[208*32:]
 return bytes(atlas),bytes(template),{'templates':profiles,'native_font_px':12,'cell_px':16,'new_tiles_used':next_tile,'capacity_tiles':208,'original_art_tail_preserved':True,'original_animation_program_preserved':True,'original_template_pointer_directory_preserved':True,'outline':'Original palette9 border outside native ink; palette1 fill. No resampling.'}

def repair_file_BG(source,base,rom,writes,manifest):
 from slime_gfx import Decompressor
 from gba_file_labels import consumer_tiles,RECORD_SPANS,RECORD_VARIANT_B
 original=Decompressor(source,0x751B90).decompress()[0]
 label=manifest['engine']['graphics']['file_labels']
 spans=(*RECORD_SPANS,*RECORD_VARIANT_B)
 exclude=[(s['off'],s['off']+s['n']*2) for s in spans]
 used=consumer_tiles(source,exclude=exclude)
 record_ids={v&1023 for s in spans for (v,) in struct.iter_unpack('<H',source[s['off']:s['off']+s['n']*2])}
 safe=sorted(record_ids-used-set(range(256))-set(range(0x3A0,0x400)))
 bad=sorted(set(label['record']['allocated_slots']) & set(range(0x3EC,0x400)))
 assert len(safe)==30 and len(bad)==14
 relocate=dict(zip(bad,safe[:len(bad)]));next_ids=iter(safe[len(bad):]);units={}
 font=load_bdf(ROOT/'assets/fonts/fusion12/fusion-pixel-12px-monospaced-zh_hans.bdf')
 for ch in ['只','胜']:
  image=Image.new('P',(16,16),6);glyph=bitmap(ch,font,12);mask=Image.new('L',(16,16),0)
  for y in range(16):
   for x in range(12):
    if glyph.getpixel((x,y)):mask.putpixel((x+2,y),255)
  border=mask.filter(ImageFilter.MaxFilter(3))
  for y in range(16):
   for x in range(16):
    if border.getpixel((x,y)):image.putpixel((x,y),4)
    if mask.getpixel((x,y)):image.putpixel((x,y),1)
  ids=[next(next_ids) for _ in range(4)];packed={}
  for n,t in enumerate(ids):
   piece=image.crop((n%2*8,n//2*8,n%2*8+8,n//2*8+8)).tobytes()
   packed[t]=bytes(piece[i]|piece[i+1]<<4 for i in range(0,64,2))
  units[ch]={'ids':ids,'packed':packed}
 streams=[label['cn_atlas_stream']]+[x['tiles'] for x in manifest['engine']['graphics']['records'] if x.get('kind')=='file-ui']
 for at in streams:
  data=bytearray(Decompressor(base,at).decompress()[0]);oldlen=len(literal(bytes(data)));assert len(data)==32768
  for old,new in relocate.items():data[new*32:(new+1)*32]=data[old*32:(old+1)*32]
  data[0x3EC*32:0x400*32]=original[0x3EC*32:0x400*32]
  for unit in units.values():
   for t,b in unit['packed'].items():data[t*32:(t+1)*32]=b
  stream=literal(bytes(data));assert len(stream)==oldlen
  rom[at:at+len(stream)]=stream;writes.append({'offset':at,'bytes':len(stream),'tag':'file-BG-restore-dynamic-time-digits-relocate-empty-record'})
 # Both blank variants must move together, since they share source glyphs.
 # Keep each row's padding; replacing the original Japanese text frees only
 # tiles proven exclusive to the two blank variants.
 for a,b in zip(RECORD_SPANS,RECORD_VARIANT_B):
  assert a['n']==b['n']
  old=base[a['off']:a['off']+a['n']*2];new=bytearray(old)
  for i,(e,) in enumerate(struct.iter_unpack('<H',old)):
   t=e&1023
   if t in relocate:struct.pack_into('<H',new,i*2,(e&0xFC00)|relocate[t])
  for span in [a,b]:
   off=span['off'];rom[off:off+len(new)]=new;writes.append({'offset':off,'bytes':len(new),'tag':'localized-empty-record-variant-'+('A' if span is a else 'B')})
 # Actual raw populated-record tables, 28x7; dynamic name/count/time cells are
 # written later by the stock code and remain untouched.
 for off in [0x7553B4,0x75553C]:
  assert base[off:off+392]==source[off:off+392]
  for ch,x,y in [('只',17,2),('胜',25,1)]:
   ids=units[ch]['ids']
   for n,t in enumerate(ids):
    cell=off+((y+n//2)*28+x+n%2)*2
    struct.pack_into('<H',rom,cell,0x4000|t);writes.append({'offset':cell,'bytes':2,'tag':'file-stat-unit-'+ch})
 return {'root_cause':'Old static-only spare census reused numeric atlas tiles3EC..3FF which stockD7930 generates dynamically. Restored all20 time digit tiles in all7paired atlas variants; original bug was reproducible on fresh local file, not user save corruption.', 'restored_dynamic_time_tiles':list(range(0x3EC,0x400)),'relocated_empty_record_tiles':{str(k):v for k,v in relocate.items()},'exclusive_blank_variants_census':safe,'both_blank_variants_localized':True,'stat_units':{ch:{'tiles':v['ids'],'font_px':12} for ch,v in units.items()},'all_paired_atlases_updated':streams,'numeric_name_and_stat_consumers_unchanged':True}


def build(source,base,manifest):
 if digest(source)!=SOURCE_SHA or digest(base)!=V20_SHA:raise ValueError('Wrong source/v20 delivery fingerprint')
 if struct.unpack_from('<I',base,FILE_ARCHIVE_LITERAL)[0]!=BASE+ARCHIVE:raise ValueError('File archive consumer already modified')
 if struct.unpack_from('<I',base,YESNO_POINTER)[0]!=BASE+9403768:raise ValueError('Wrong v20 yes/no pointer')
 assert base[0xD5EBC:FILE_ARCHIVE_LITERAL]==source[0xD5EBC:FILE_ARCHIVE_LITERAL]
 get,oldbase=resources(source);rom=bytearray(base);cursor=APPEND_START;writes=[]
 def append(data,tag):
  nonlocal cursor
  cursor=(cursor+3)&~3;a=cursor
  if any(v!=255 for v in rom[a:a+len(data)]):raise ValueError('Occupied append region')
  rom[a:a+len(data)]=data;cursor+=len(data);writes.append({'offset':a,'bytes':len(data),'tag':tag});return a
 ids=json.loads((ROOT/'data/gba-font-ids.json').read_text('utf-8'));codec=CNCodec(ids)
 # Original consumer draws first24px (3 columns) then32px (4 columns), regardless
 # of translated glyph advances. Padding+ALIGN restores exact56px/14tiles.
 choice=codec.encode(['是 ',['ALIGN'],'否  ',['ALIGN']],'plain',compact=True)
 yes_at=append(choice,'fixed-yesno-24-plus-32-pixel-layout')
 struct.pack_into('<I',rom,YESNO_POINTER,BASE+yes_at)
 tiles,templates,meta=file_assets(source)
 replacements={TILE_ID:append(literal(tiles),'cn-file-command-OBJ-atlas'),TEMPLATE_ID:append(templates,'cn-file-command-OBJ-templates')}
 lengths={TILE_ID:len(literal(tiles)),TEMPLATE_ID:len(templates)}
 count=0x2E1;newarc_at=(cursor+3)&~3;newbase=newarc_at+4+count*8
 directory=bytearray(struct.pack('<I',count));entries=[]
 for i in range(count):
  oldentry=ARCHIVE+4+i*8;rel,sz=struct.unpack_from('<II',source,oldentry);ptr=oldbase+rel
  if i in replacements:ptr=replacements[i];sz=lengths[i]
  directory+=struct.pack('<II',(ptr-newbase)&0xFFFFFFFF,sz)
  entries.append({'ID':i,'offset':ptr,'bytes':sz,'localized':i in replacements})
 assert append(directory,'source-qualified-file-OBJ-private-archive')==newarc_at
 struct.pack_into('<I',rom,FILE_ARCHIVE_LITERAL,BASE+newarc_at)
 writes += [{'offset':YESNO_POINTER,'bytes':4,'tag':'yesno-resource-pointer'},{'offset':FILE_ARCHIVE_LITERAL,'bytes':4,'tag':'file-private-archive-literal'}]
 bgmeta=repair_file_BG(source,base,rom,writes,manifest)
 result=bytes(rom)
 allowed=set()
 for w in writes:allowed.update(range(w['offset'],w['offset']+w['bytes']))
 assert all(i in allowed for i,(a,b) in enumerate(zip(base,result)) if a!=b)
 return result,{'schema':'gba-v21-user-screenshot-ui-fixes','status':'candidate-awaiting-runtime-verification','source_sha256':SOURCE_SHA,'baseline_sha256':V20_SHA,'target_sha256':digest(result),'append_start':APPEND_START,'append_end':cursor,'writes':writes,'choice':{'offset':yes_at,'encoded_hex':choice.hex(),'original_width_px':56,'original_columns_per_row':[3,4],'source_record':'plain-713F08','semantic_tokens_unchanged':['是',['ALIGN'],'否'],'padding_is_compiler_layout_only':True},'file_OBJ':meta,'file_BG':bgmeta,'private_archive':{'offset':newarc_at,'entries':entries,'only_changed_IDs':[TILE_ID,TEMPLATE_ID]},'font_ID_registry_unchanged':True,'all_primary_and_compact_font_bitmap_bytes_unchanged':True,'no_new_CPU_instructions':True,'remaining':'Title and other unrequested graphical Japanese still incomplete; no full playthrough/save compatibility certification.'}

