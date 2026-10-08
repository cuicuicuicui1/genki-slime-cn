"""All Japanese title groups and animation frames, private title archive only.
No game text/IDs/palette/English artwork changes. Native pixel art; no smoothing.
"""
from pathlib import Path
import hashlib,struct
from PIL import Image,ImageFilter
from cn_codec import ROOT,BASE,SOURCE_SHA
from cn_engine import bitmap,load_bdf
from gba_graphics_engine import literal
from gba_main_menu_graphics import resources,ARCHIVE
TILE_ID=0x2BD
TEMPLATE_ID=0x2BE
LITERALS=(0xD3910,0xD3BEC,0xD3E70,0xD4720,0xD5384)
JP_FRAMES=(2,4,5,6,*range(20,31))
DIMS=(((8,8),(16,16),(32,32),(64,64)),((16,8),(32,8),(32,16),(64,32)),((8,16),(8,32),(16,32),(32,64)))
SHA_TEMPLATE='c7a87e790e2448632292396ffdd9030b6e068bdad1c5533608341194f66b102f'
def sha(b):return hashlib.sha256(b).hexdigest()
def frames(data):
 anim,count=struct.unpack_from('<HH',data);assert count==31
 rows=[]
 for i in range(count):
  a=4+(struct.unpack_from('<H',data,4+2*i)[0]&~1);n=struct.unpack_from('<H',data,a)[0];end=a+2+6*n
  assert end==(4+(struct.unpack_from('<H',data,6+2*i)[0]&~1) if i+1<count else anim)
  rows.append([struct.unpack_from('<3H',data,a+2+6*k) for k in range(n)])
 return anim,rows

def part(x,y,w,h,tile,bank):
 choices=[(shape,size) for shape,row in enumerate(DIMS) for size,dim in enumerate(row) if dim==(w,h)]
 assert len(choices)==1;shape,size=choices[0]
 return (shape<<14|(y&255),size<<14|(x&511),bank<<12|tile)

def pack_image(image):
 w,h=image.size;assert w%8==h%8==0;out=bytearray()
 for ty in range(h//8):
  for tx in range(w//8):
   for y in range(8):
    for x in range(0,8,2):out.append(image.getpixel((tx*8+x,ty*8+y))|image.getpixel((tx*8+x+1,ty*8+y))<<4)
 return bytes(out)

def glyph(ch,font,size,kind):
 native=bitmap(ch,font,size)
 if kind=='blue':
  # Title artwork uses integer2x of the original12px pixel strokes, not a fuzzy resample.
  crop=native.crop((0,2,12,14));assert sum(bool(v) for v in native.get_flattened_data())==sum(bool(v) for v in crop.get_flattened_data())
  mask=Image.new('L',(32,32));crop=crop.convert('L').resize((24,24),Image.Resampling.NEAREST);mask.paste(crop,(4,4))
 else:
  mask=Image.new('L',(16,16));mask.paste(native.convert('L'),((16-size)//2,0))
 image=Image.new('P',mask.size,0);outline=mask.filter(ImageFilter.MaxFilter(3));ink_count=0
 for y in range(mask.height):
  for x in range(mask.width):
   if outline.getpixel((x,y)):image.putpixel((x,y),8 if kind=='pink' else 1)
   if mask.getpixel((x,y)):
    ink_count+=1
    color=(7+max(0,6-(y-4)//4) if kind=='blue' else 9 if kind=='pink' else max(3,7-y//3) if kind=='orange' else max(4,7-y//4))
    image.putpixel((x,y),color)
 assert ink_count>0
 return image,{'character':ch,'native_font_px':size,'integer_artwork_scale':2 if kind=='blue' else 1,'ink_pixels':ink_count,'bitmap_sha256':sha(native.tobytes())}

def assets(source):
 get,_=resources(source);oldtiles=get(TILE_ID)[2];old=get(TEMPLATE_ID)[2]
 assert len(oldtiles)==14336 and len(old)==2036 and sha(old)==SHA_TEMPLATE
 anim,oldframes=frames(old)
 japanese={t for i in JP_FRAMES if i!=6 for a0,a1,a2 in oldframes[i] for t in range(a2&1023,(a2&1023)+(DIMS[a0>>14][a1>>14][0]//8)*(DIMS[a0>>14][a1>>14][1]//8))}
 assert len(japanese)==186 and japanese==set(range(121,135))|set(range(150,218))|set(range(321,425))
 atlas=bytearray(oldtiles)
 for tile in japanese:atlas[tile*32:(tile+1)*32]=bytes(32)
 used=set();profiles=[];previews={}
 def put(at,image):
  data=pack_image(image);tiles=set(range(at,at+len(data)//32));assert tiles<=japanese and not tiles&used
  used.update(tiles);atlas[at*32:at*32+len(data)]=data
 font12=load_bdf(ROOT/'assets/fonts/fusion12/fusion-pixel-12px-monospaced-zh_hans.bdf')
 font16=load_bdf(ROOT/'assets/fonts/unifont16/unifont-16.0.03.bdf')
 header=Image.new('P',(64,16));x=2
 for ch in '勇者斗恶龙':
  im,proof=glyph(ch,font12,12,'pink');header.paste(im,(x-2,0),Image.frombytes('L',im.size,bytes(255 if v else 0 for v in im.tobytes())));profiles.append(proof);x+=12
 put(150,header.crop((0,0,32,16)));put(158,header.crop((32,0,64,16)))
 blues=[]
 for k,ch in enumerate('史莱姆'):
  im,proof=glyph(ch,font12,12,'blue');put(166+16*k,im);blues.append(166+16*k);profiles.append(proof)
 oranges=[]
 for k,ch in enumerate('元气'):
  im,proof=glyph(ch,font16,16,'orange');put(121+4*k,im);oranges.append(121+4*k);profiles.append(proof)
 greens=[]
 for k,ch in enumerate('冲击的尾巴团'):
  im,proof=glyph(ch,font12,12,'green');put(321+4*k,im);greens.append(321+4*k);profiles.append(proof)
 newframes=[list(f) for f in oldframes]
 newframes[2]=[part(-30,18,32,16,150,2),part(2,18,32,16,158,2)]
 for f in [5,*range(20,25)]:
  pos=[[-51,-40],[-24,-40],[3,-38]]
  if f==20:pos[0][0]-=2;pos[0][1]+=4
  if f==21:pos[0][1]-=4;pos[1][1]+=4
  if f==22:pos[1][1]-=4;pos[2][1]+=4
  if f==23:pos[2][1]-=4
  if f==24:pos[2][0]+=2;pos[2][1]-=2
  newframes[f]=[part(x,y,32,32,t,3) for (x,y),t in zip(pos,blues)]
 for f in [4,*range(25,30)]:
  pos=[[38,-37],[54,-37]]
  if f==25:pos[0][0]-=1;pos[0][1]+=1
  if f==26:pos[0][0]+=1;pos[0][1]-=9
  if f==28:pos[1][0]-=1;pos[1][1]+=1
  if f==29:pos[1][0]+=1;pos[1][1]-=9
  newframes[f]=[part(x,y,16,16,t,2) for (x,y),t in zip(pos,oranges)]
 newframes[30]=[part(-36+12*k,y,16,16,t,1) for k,(y,t) in enumerate(zip([30,31,32,32,31,30],greens))]
 assert oldframes[6]==oldframes[5]+oldframes[2]+oldframes[1]+oldframes[3]+oldframes[4]+oldframes[30]
 # Frame6 is a complete assembled logo, not just English/art. Replace all JP groups here too.
 newframes[6]=newframes[5]+newframes[2]+oldframes[1]+oldframes[3]+newframes[4]+newframes[30]
 out=bytearray(4+31*2)
 for i,row in enumerate(newframes):
  struct.pack_into('<H',out,4+i*2,len(out)-4);out+=struct.pack('<H',len(row))+b''.join(struct.pack('<3H',*p) for p in row)
 newanim=len(out);struct.pack_into('<HH',out,0,newanim,31);out+=old[anim:]
 actual_anim,actual=frames(out);assert actual==newframes and bytes(out[newanim:])==old[anim:]
 for i in set(range(31))-set(JP_FRAMES):assert newframes[i]==oldframes[i]
 assert all(bytes(atlas[i*32:(i+1)*32])==oldtiles[i*32:(i+1)*32] for i in set(range(448))-japanese)
 assert sum(len(newframes[i]) for i in [1,2,3,4,5,30])<=sum(len(oldframes[i]) for i in [1,2,3,4,5,30])
 return bytes(atlas),bytes(out),{'source_template_sha256':SHA_TEMPLATE,'source_template_bytes':2036,'new_template_bytes':len(out),'frame_count':31,'changed_frames':list(JP_FRAMES),'original_animation_program_preserved':True,'original_Japanese_tile_count':186,'allocated_new_tiles':sorted(used),'non_Japanese_art_tiles_and_frames_unchanged':True,'original_palette_unchanged':True,'labels':{'ドラゴンクエスト':'勇者斗恶龙','スライム':'史莱姆','もりもり':'元气','衝撃のしっぽ団':'冲击的尾巴团'},'glyph_profiles':profiles,'title_animation_motion':'Same31-frame indices/program/durations; Chinese glyph group coordinates follow bounce variants; no Japanese intermediate frames','new_animation_anchor':newanim}

def extend(source,baseline,append_end):
 from gba_graphic_labels_v22 import translate,private_extend
 if len(source)!=0x800000 or sha(source)!=SOURCE_SHA:raise ValueError('Wrong source ROM')
 tiles,templates,meta=assets(source);get,_=resources(source)
 bgtiles,bgmaps,prompt,_=translate(get(0x19F)[2],{0x1A1:get(0x1A1)[2]},
  {0x1A1:[{'ja':'PUSH START BUTTON','cn':'按START键开始','rect':[56,128,192,160],'xy':[80,142],'px':12,'bg':0,'ink':1,'outline':7,'bank':3}]},reserved=range(256,1024),palette=get(0x1A0)[2].ljust(512,b"\0"))
 rom,private=private_extend(source,baseline,append_end,
  {0x2BD:(tiles,True),0x2BE:(templates,False),0x19F:(bgtiles,True),0x1A1:(bgmaps[0x1A1],True)},LITERALS,
  [(0xD3B6A,0x68),(0xD4472,0x30),(0xD3E74,0x20),(0xD44AC,0x10)])
 meta.update(private);meta.update(schema='gba-title-Chinese-all31-v22',status='candidate-awaiting-runtime-verification',start_prompt=prompt,original_BG_art_and_palette_preserved=True)
 return rom,meta
