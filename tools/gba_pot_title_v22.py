"""Pot-game Japanese wordmark, all fifteen OBJ cells and both source archives."""
import struct
from PIL import Image,ImageFilter
from graphics_pot import resource
from cn_codec import ROOT,BASE,SOURCE_SHA
from cn_engine import bitmap,load_bdf
from gba_title_graphics_v22 import part,pack_image
from gba_graphic_labels_v22 import digest
from gba_graphics_engine import literal

def assets(source):
 tiles=resource(source,0x1D9FEC,0xBC)[2];cells=resource(source,0x1D9FEC,0xBE)[2];assert len(tiles)==4896 and len(cells)==868
 anim,count=struct.unpack_from('<HH',cells);assert count==15
 rows=[]
 for i in range(count):
  a=4+(struct.unpack_from('<H',cells,4+i*2)[0]&~1);n=struct.unpack_from('<H',cells,a)[0];rows.append([struct.unpack_from('<3H',cells,a+2+j*6) for j in range(n)])
 atlas=bytearray(tiles);atlas[75*32:]=bytes(len(atlas)-75*32);font=load_bdf(ROOT/'assets/fonts/fusion12/fusion-pixel-12px-monospaced-zh_hans.bdf')
 def draw(ch,big=False):
  native=bitmap(ch,font,12);im=Image.new('L',(32 if big else 16,32 if big else 16))
  if big:im.paste(native.crop((0,2,12,14)).convert('L').resize((24,24),Image.Resampling.NEAREST),(4,4))
  else:im.paste(native.convert('L'),(2,0))
  out=Image.new('P',im.size);outline=im.filter(ImageFilter.MaxFilter(3))
  for y in range(im.height):
   for x in range(im.width):
    if outline.getpixel((x,y)):out.putpixel((x,y),7)
    if im.getpixel((x,y)):out.putpixel((x,y),max(2,6-y//7) if big else 2)
  return out
 header=Image.new('P',(32,16));header.paste(draw('心'),(0,0));header.paste(draw('动'),(16,0));atlas[75*32:83*32]=pack_image(header)
 for k,ch in enumerate('砸壶'):atlas[(83+k*16)*32:(99+k*16)*32]=pack_image(draw(ch,True))
 new=[list(row) for row in rows]
 for i in range(3,14):
  new[i]=[part(-16,-24,32,16,75,15)]
  if i>=4:
   y={4:12,5:-4,6:0,7:4}.get(i,4);new[i].append(part(-34,y,32,32,83,15))
  if i>=8:
   y={8:14,9:-4,10:0,11:4,12:4,13:4}[i];new[i].append(part(2,y,32,32,99,15))
  new[i]+=rows[2] # English brand stays byte-identical in every full frame.
 out=bytearray(4+count*2)
 for i,row in enumerate(new):struct.pack_into('<H',out,4+i*2,len(out)-4);out+=struct.pack('<H',len(row))+b''.join(struct.pack('<3H',*q) for q in row)
 struct.pack_into('<HH',out,0,len(out),count);out+=cells[anim:]
 assert atlas[:75*32]==tiles[:75*32] and new[0]==rows[0] and new[1]==rows[1] and new[2]==rows[2] and new[14]==rows[14]
 # The duplicate archive uses OBJ bank4 instead of15, and identical geometry.
 duplicate=bytearray(out)
 for i in range(count):
  a=4+(struct.unpack_from('<H',duplicate,4+i*2)[0]&~1)
  for j in range(struct.unpack_from('<H',duplicate,a)[0]):
   q=a+2+j*6+4;v=struct.unpack_from('<H',duplicate,q)[0];struct.pack_into('<H',duplicate,q,(v&0xfff)|0x4000)
 return bytes(atlas),bytes(out),bytes(duplicate),{'frame_count':15,'Japanese_changed_frames':list(range(3,14)),'animation_program_unchanged':True,'English_and_pot_art_preserved':True,'labels':{'ドキドキ':'心动','つぼくらっしゅ':'砸壶'},'native_px':12,'integer_wordmark_scale':2,'source_cell_sha256':digest(cells)}

def extend(source,baseline,append_end):
 if digest(source)!=SOURCE_SHA:raise ValueError('Wrong source')
 for a,n in [(0xD1B8C,0xB0),(0xC5980,0x20)]:
  if baseline[a:a+n]!=source[a:a+n]:raise ValueError('Pot title consumer changed')
 tiles,cells,dup,meta=assets(source);rom=bytearray(baseline);cursor=(append_end+3)&~3;start=cursor;writes=[]
 def append(data,tag):
  nonlocal cursor
  cursor=(cursor+3)&~3;a=cursor
  if a+len(data)>len(rom) or any(v!=255 for v in rom[a:a+len(data)]):raise ValueError('Occupied/overflow tail')
  rom[a:a+len(data)]=data;cursor+=len(data);writes.append({'offset':a,'length':len(data),'purpose':tag});return a
 ta=append(literal(tiles),'pot-Chinese-wordmark-atlas');ca=append(cells,'pot-Chinese15-cells');da=append(dup,'pot-Chinese15-cells-bank4')
 entries=[]
 for arc,i,at,n in [(0x1D9FEC,0xBC,ta,len(literal(tiles))),(0x1D9FEC,0xBE,ca,len(cells)),(0x765FA8,0x2C2,ta,len(literal(tiles))),(0x765FA8,0x2C3,da,len(dup))]:
  entry=arc+4+i*8;base=arc+4+struct.unpack_from('<I',source,arc)[0]*8
  if baseline[entry:entry+8]!=source[entry:entry+8]:raise ValueError('Pot entry changed')
  rom[entry:entry+8]=struct.pack('<II',(at-base)&0xffffffff,n);writes.append({'offset':entry,'length':8,'purpose':'source-qualified-pot-entry'});entries.append({'archive':arc,'ID':i,'offset':at,'stored_bytes':n})
 assert all(any(w['offset']<=i<w['offset']+w['length'] for w in writes) for i,(a,b) in enumerate(zip(baseline,rom)) if a!=b)
 meta.update(schema='gba-pot-title-all15-OBJ-v22',status='candidate',source_sha256=SOURCE_SHA,baseline_sha256=digest(baseline),target_sha256=digest(rom),append_start=start,append_end=cursor,writes=writes,source_qualified_entries=entries,new_CPU_instructions=False)
 return bytes(rom),meta
