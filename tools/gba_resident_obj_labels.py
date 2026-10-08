"""v18 native resident OBJ labels (final16px, early12px probes) via a source-qualified private archive literal.
No new CPU instructions or global getter hooks. Keeps A/icon/OAM/palettes and
all foreign original archive consumers. 32-bit relative offsets deliberately
wrap to original ROM resources just as the ARMv4T stock getter adds them.
"""
from pathlib import Path
import hashlib,json,struct
from PIL import Image
from cn_codec import ROOT,BASE,SOURCE_SHA
from cn_engine import bitmap,load_bdf
from gba_main_menu_graphics import SOURCE_PATH,ARCHIVE,resources
from gba_graphics_engine import literal

BASELINE_SHA='042ba869beb56bc96b10350164e24e8e7f681444176af4c9583a190a696fdc07'
HOOK_LITERAL=0xB72CC
CONSUMER_START=0xB7298
CONSUMER_END=0xB72E8
LABELS=(
 {'ID':0x2D9,'ja':'でよむ','cn':'阅读','parts':[(4,0,32)],'width':32,'x':2,'ink':6,'palette':14,'preserve':'Original A-button icon tiles0..3 and unused tiles12..31 unchanged'},
 {'ID':0x2DB,'ja':'まだ話していない','cn':'尚未交谈','parts':[(0,0,32),(8,32,32),(16,64,8)],'width':72,'x':12,'ink':6,'palette':14,'preserve':'Status multipart OAM32x16+32x16+8x16 unchanged; tailtiles18..31 unchanged'},
)

def decode_parts(data,parts,width):
 image=Image.new('P',(width,16))
 for tile,x0,w in parts:
  for y in range(16):
   for x in range(w):
    n=tile+(y//8)*(w//8)+x//8
    byte=data[n*32+(y%8)*4+(x%8)//2]
    image.putpixel((x0+x,y),(byte>>((x&1)*4))&15)
 return image

def encode_parts(data,image,parts):
 result=bytearray(data)
 for tile,x0,w in parts:
  for y in range(16):
   for x in range(0,w,2):
    n=tile+(y//8)*(w//8)+x//8
    result[n*32+(y%8)*4+(x%8)//2]=image.getpixel((x0+x,y))|image.getpixel((x0+x+1,y))<<4
 return bytes(result)

def translate(source,background=0,font_px=12):
 if font_px not in (12,16):raise ValueError('Unsupported native font size')
 if background not in (0,1):raise ValueError('Only native transparent or original white palette index is allowed')
 get,_=resources(source);font=load_bdf(ROOT/('assets/fonts/unifont16/unifont-16.0.03.bdf' if font_px==16 else 'assets/fonts/fusion12/fusion-pixel-12px-monospaced-zh_hans.bdf'));results={};profiles=[]
 for row in LABELS:
  _,_,old=get(row['ID'])
  if len(old)!=1024:raise ValueError('Resident OBJ source1024byte allocation changed')
  image=Image.new('P',(row['width'],16),background);x=(row['width']-len(row['cn'])*font_px)//2 if font_px==16 else row['x'];origin=x;samples=[]
  for ch in row['cn']:
   glyph=bitmap(ch,font,font_px)
   if x<0 or x+font_px>image.width:raise ValueError('Resident OBJ text exceeds native sprite capacity')
   for y in range(16):
    for xx in range(font_px):
     if glyph.getpixel((xx,y)):image.putpixel((x+xx,y),row['ink'])
   samples.append({'char':ch,'native_ink_pixels':sum(bool(glyph.getpixel((xx,yy))) for yy in range(16) for xx in range(font_px)),'bitmap_SHA256':hashlib.sha256(glyph.tobytes()).hexdigest()});x+=font_px
  new=encode_parts(old,image,row['parts']);used=set()
  for tile,_,w in row['parts']:used.update(range(tile,tile+w//8*2))
  for tile in range(32):
   if tile not in used and new[tile*32:(tile+1)*32]!=old[tile*32:(tile+1)*32]:raise ValueError('Nontext OBJ tile changed')
  assert decode_parts(new,row['parts'],row['width']).tobytes()==image.tobytes()
  results[row['ID']]=new;profiles.append({**row,'x':origin,'native_font_px':font_px,'advance_px':font_px,'native_strokes':samples,'modified_tile_IDs':sorted(used),'decoded_bytes':1024,'source_SHA256':hashlib.sha256(old).hexdigest(),'target_SHA256':hashlib.sha256(new).hexdigest(),'no_shadow_or_smoothing':True,'background_index':background,'background_reason':'Original white palette1 flat backplate prevents tiny original letter art confusing native strokes' if background else 'Original transparency retained'})
 return results,profiles

def extend(baseline,append_end,backplate=False,font_px=12, *, expected_baseline_sha=BASELINE_SHA):
 source=SOURCE_PATH.read_bytes()
 if hashlib.sha256(source).hexdigest()!=SOURCE_SHA or hashlib.sha256(baseline).hexdigest()!=expected_baseline_sha:raise ValueError('Wrong original/v17 baseline')
 if baseline[CONSUMER_START:CONSUMER_END]!=source[CONSUMER_START:CONSUMER_END]:raise ValueError('Source resident OBJ consumer changed')
 if struct.unpack_from('<I',baseline,HOOK_LITERAL)[0]!=BASE+ARCHIVE:raise ValueError('Wrong original resident OBJ archive literal')
 from capstone import Cs,CS_ARCH_ARM,CS_MODE_THUMB
 md=Cs(CS_ARCH_ARM,CS_MODE_THUMB)
 references=[]
 for ins in md.disasm(source[0xB71EC:0xB7330],BASE+0xB71EC):
  if ins.mnemonic=='ldr' and '[pc' in ins.op_str:
   at=((ins.address+4)&~3)+int(ins.op_str.split('#')[-1].rstrip(']'),0)
   if at==BASE+HOOK_LITERAL:references.append(ins.address)
 if references!=[BASE+0xB729A]:raise ValueError('Archive literal reference set changed')
 results,profiles=translate(source,1 if backplate else 0,font_px);rom=bytearray(baseline);cursor=(append_end+3)&~3;start=cursor
 def append(data):
  nonlocal cursor
  cursor=(cursor+3)&~3;at=cursor
  if at+len(data)>len(rom) or any(v!=255 for v in rom[at:at+len(data)]):raise ValueError('Occupied/overflow append span')
  rom[at:at+len(data)]=data;cursor+=len(data);return at
 pointers={id:BASE+append(literal(data)) for id,data in sorted(results.items())}
 count=struct.unpack_from('<I',baseline,ARCHIVE)[0]
 if count!=0x2E1:raise ValueError('Original archive count changed')
 original_base=BASE+ARCHIVE+4+count*8
 archive=(cursor+3)&~3;private_base=BASE+archive+4+count*8
 directory=bytearray(struct.pack('<I',count));entries=[]
 for id in range(count):
  relative,size=struct.unpack_from('<II',baseline,ARCHIVE+4+id*8)
  pointer=(original_base+relative)&0xffffffff
  if id in pointers:pointer=pointers[id];size=len(literal(results[id]))
  directory.extend(struct.pack('<II',(pointer-private_base)&0xffffffff,size))
  entries.append({'ID':id,'target_pointer':pointer,'stored_bytes':size,'localized':id in pointers})
 assert append(bytes(directory))==archive
 struct.pack_into('<I',rom,HOOK_LITERAL,BASE+archive)
 allowed=[(HOOK_LITERAL,4),(start,cursor-start)]
 assert all(any(lo<=i<lo+n for lo,n in allowed) for i,(a,b) in enumerate(zip(baseline,rom)) if a!=b)
 assert rom[ARCHIVE:ARCHIVE+4+count*8]==baseline[ARCHIVE:ARCHIVE+4+count*8]
 meta={'schema':'gba-v18-resident-native-OBJ-private-archive','status':'experimental-not-frozen','source_sha256':SOURCE_SHA,'baseline_sha256':expected_baseline_sha,'rom_sha256':hashlib.sha256(rom).hexdigest(),'hook_literal':HOOK_LITERAL,'original_literal':BASE+ARCHIVE,'new_archive':archive,'private_resource_base':private_base,'archive_count':count,'private_entries':entries,'label_profiles':profiles,'original_consumer_byte_fingerprint':hashlib.sha256(source[CONSUMER_START:CONSUMER_END]).hexdigest(),'shared_literal_caller':BASE+0xB729A,'append_start':start,'append_end':cursor,'no_new_CPU_instructions':True,'source_archive_directory_unchanged':True,'scope':'Only original B7298 resident3OBJ resource loader archive literal. Two textresources2D9/2DB native pixels, third2DD is icon art and stays original. All737 private getter targets except2text point to baseline ROM by stock32bit wrapping offsets. No palette/OAM/nameIDs/prose changes. Controlled/native/finalSHA tests required; not natural resident unlock or full campaign.'}
 return bytes(rom),meta,results

if __name__=='__main__':
 base=ROOT/'build/town-menu-experimental-v17/slime-cn.gba';prior=json.loads((ROOT/'work/gba-v17-town-resident-candidate09/experiment.json').read_text('utf8'))
 rom,meta,images=extend(base.read_bytes(),prior['append_end'],backplate=True,font_px=16);out=ROOT/'work/gba-v18-resident-obj-candidate03';out.mkdir(exist_ok=False)
 (out/'slime-cn.gba').write_bytes(rom);(out/'experiment.json').write_text(json.dumps(meta,ensure_ascii=False,indent=2)+'\n','utf8')
 for id,data in images.items():(out/f'atlas-{id:03X}.bin').write_bytes(data)
 print(meta['rom_sha256'])
