"""Source-bound start/clear OBJ glyph sequences; fixed frame IDs and geometry.
Different scenes instantiate one object per source letter, so Chinese sequences
keep the same four/six cells rather than drawing a static overlay per character.
"""
import struct
from PIL import Image,ImageFilter
from cn_codec import ROOT,BASE,SOURCE_SHA
from cn_engine import bitmap,load_bdf
from graphics_pot import resource
from graphics_sprites import parse_cells
from gba_graphics_engine import literal
from gba_title_graphics_v22 import pack_image
from gba_graphic_labels_v22 import digest
CONFIGS=((0x2C6,0x2C7,'スタート','开始游戏',10,1),(0x2C8,0x2C9,'ゲームクリア','成功通过关卡',1,None),(0x2CE,0x2CF,'ゲームクリア','成功通过关卡',1,None))
def assets(source):
 font=load_bdf(ROOT/'assets/fonts/fusion12/fusion-pixel-12px-monospaced-zh_hans.bdf');result={};profiles=[]
 for tid,mid,ja,cn,ink,border in CONFIGS:
  atlas=resource(source,0x765FA8,tid)[2];cells=resource(source,0x765FA8,mid)[2];rows=parse_cells(cells)
  assert len(rows)==len(cn) and all(len(row)==1 and row[0][2]&1023==k*16 and row[0][0]==0xF0 and row[0][1]==0x81F0 for k,row in enumerate(rows))
  raw=bytearray()
  for ch in cn:
   native=bitmap(ch,font,12);crop=native.crop((0,2,12,14));assert sum(bool(v) for v in crop.get_flattened_data())==sum(bool(v) for v in native.get_flattened_data())
   mask=Image.new('L',(32,32));mask.paste(crop.convert('L').resize((24,24),Image.Resampling.NEAREST),(4,4));out=Image.new('P',(32,32))
   outline=mask.filter(ImageFilter.MaxFilter(3)) if border is not None else mask
   for y in range(32):
    for x in range(32):
     if border is not None and outline.getpixel((x,y)):out.putpixel((x,y),border)
     if mask.getpixel((x,y)):out.putpixel((x,y),ink)
   raw+=pack_image(out)
  assert len(raw)==len(atlas);result[tid]=bytes(raw);profiles.append({'tiles_ID':tid,'templates_ID':mid,'ja':ja,'cn':cn,'frame_count':len(rows),'native_px':12,'integer_scale':2,'templates_byte_identical':True,'source_atlas_sha256':digest(atlas)})
 # SELECT/A button symbols are original art; localize only the adjacent
 # selection/confirmation text in all six prompt frames, keeping animations.
 old=resource(source,0x765FA8,0x2D7)[2];assert len(old)==2048;atlas=bytearray(old)
 from gba_resident_obj_labels import encode_parts
 for cn,parts in [('选择',[(8,0,32),(16,32,8)]),('确认',[(28,0,32),(36,32,8)])]:
  image=Image.new('P',(40,16));x=7
  for ch in cn:
   native=bitmap(ch,font,12)
   for y in range(16):
    for xx in range(12):
     if native.getpixel((xx,y)):image.putpixel((x+xx,y),15)
   x+=12
  atlas=bytearray(encode_parts(atlas,image,parts))
 assert atlas[:8*32]==old[:8*32] and atlas[18*32:28*32]==old[18*32:28*32] and atlas[38*32:]==old[38*32:]
 result[0x2D7]=bytes(atlas);profiles.append({'tiles_ID':0x2D7,'templates_ID':0x2D8,'ja':['せんたく','かくにん'],'cn':['选择','确认'],'frame_count':6,'native_px':12,'integer_scale':1,'button_art_and_templates_preserved':True,'source_atlas_sha256':digest(old)})
 return result,profiles

def extend(source,baseline,append_end):
 if digest(source)!=SOURCE_SHA:raise ValueError('Wrong source')
 # These source routines instantiate all four/six animated letter objects.
 for a,n in [(0xBED40,0x100),(0xBF078,0x100),(0xBF188,0x100),(0xBF51C,0x110),(0xBF6B0,0x100)]:
  if source[a:a+n]!=baseline[a:a+n]:raise ValueError('Start/clear consumer changed')
 assets_cn,profiles=assets(source);rom=bytearray(baseline);cursor=(append_end+3)&~3;start=cursor;writes=[];entries=[]
 for tid,raw in sorted(assets_cn.items()):
  stored=literal(raw);cursor=(cursor+3)&~3;at=cursor
  if at+len(stored)>len(rom) or any(v!=255 for v in rom[at:at+len(stored)]):raise ValueError('Occupied/overflow tail')
  rom[at:at+len(stored)]=stored;cursor+=len(stored);writes.append({'offset':at,'length':len(stored),'purpose':'native-Chinese-start-clear-sequence'})
  entry=0x765FA8+4+tid*8;base=0x765FA8+4+737*8
  if source[entry:entry+8]!=baseline[entry:entry+8]:raise ValueError('Wordmark entry already changed')
  rom[entry:entry+8]=struct.pack('<II',at-base,len(stored));writes.append({'offset':entry,'length':8,'purpose':'source-bound-start-clear-atlas-entry'});entries.append({'archive':0x765FA8,'ID':tid,'offset':at,'stored_bytes':len(stored)})
 assert all(any(w['offset']<=i<w['offset']+w['length'] for w in writes) for i,(a,b) in enumerate(zip(baseline,rom)) if a!=b)
 return bytes(rom),{'schema':'gba-minigame-start-clear-wordmarks-v22','status':'candidate','source_sha256':SOURCE_SHA,'baseline_sha256':digest(baseline),'target_sha256':digest(rom),'append_start':start,'append_end':cursor,'writes':writes,'labels':profiles,'source_qualified_entries':entries,'new_CPU_instructions':False,'source_glyph_timings_countdown_digits_and_templates_preserved':True}
