"""Source-bound private archive and native BG-label compositor. No ROM files bundled."""
import hashlib,struct
from PIL import Image,ImageFilter
from cn_codec import ROOT,BASE,SOURCE_SHA
from cn_engine import load_bdf,bitmap
from gba_main_menu_graphics import resources,ARCHIVE
from gba_graphics_engine import literal
from gba_ui_v03 import indexed4
from graphics_backgrounds import render_map

def digest(b):return hashlib.sha256(b).hexdigest()
def font(px):
 name={8:'fusion8/fusion-pixel-8px-monospaced-zh_hans.bdf',12:'fusion12/fusion-pixel-12px-monospaced-zh_hans.bdf',16:'unifont16/unifont-16.0.03.bdf'}[px]
 return load_bdf(ROOT/'assets/fonts'/name)

def draw_label(image,label):
 rect=label['rect'];x,y=label['xy'];px=label.get('px',12)
 if label.get('clear',True):image.paste(label.get('bg',0),rect)
 mask=Image.new('L',image.size);bdf=font(px);profiles=[]
 for ch in label['cn']:
  im=bitmap(ch,bdf,px);advance=px//2 if ord(ch)<128 else px
  if ord(ch)<128:im=im.crop((0,0,advance,16))
  if not ch.isspace():
   bb=im.getbbox()
   if bb and not (rect[0]<=x+bb[0]<x+bb[2]<=rect[2] and rect[1]<=y+bb[1]<y+bb[3]<=rect[3]):raise ValueError('Glyph outside label rectangle: '+ch)
  mask.paste(im.convert('L'),(x,y));profiles.append({'char':ch,'advance':advance,'native_px':px,'bitmap_sha256':digest(im.tobytes())});x+=advance
 if not mask.getbbox():raise ValueError('Empty label mask')
 outline=mask.filter(ImageFilter.MaxFilter(3)) if 'outline' in label else mask
 for yy in range(rect[1],rect[3]):
  for xx in range(rect[0],rect[2]):
   if outline.getpixel((xx,yy)):image.putpixel((xx,yy),label.get('outline',label['ink']))
   if mask.getpixel((xx,yy)):image.putpixel((xx,yy),label['ink'])
 return profiles

def translate(tiles,maps,labels,widths=None,reserved=(),extra_maps=(),palette=None,reclaim_unreferenced_nonempty=False):
 """Edit label rectangles; reclaim only exclusive old-text or blank unreferenced tiles.
 extra_maps covers small stock counter/digit overlays sharing the atlas. tile0 and
 caller-proven dynamic banks must be reserved. Palette is owned by the caller.
 """
 if len(tiles)%32 or len(tiles)>32768:raise ValueError('4bpp capacity')
 widths=widths or {};images={};before_images={};changes={};bank_override={};profiles=[];inside=set();outside=set(reserved)|{0}
 for raw in extra_maps:
  outside.update(e&1023 for e, in struct.iter_unpack('<H',raw))
 for mid,raw in maps.items():
  w=widths.get(mid,32);before=indexed4(tiles.ljust(32768,b'\0'),raw,w);after=before.copy();before_images[mid]=before;rows=labels.get(mid,[])
  for label in rows:profiles.append({'map_ID':mid,**label,'glyphs':draw_label(after,label)})
  cells=set()
  for n,(entry,) in enumerate(struct.iter_unpack('<H',raw)):
   x=n%w*8;y=n//w*8
   if before.crop((x,y,x+8,y+8)).tobytes()!=after.crop((x,y,x+8,y+8)).tobytes():
    cells.add(n);inside.add(entry&1023)
    for label in rows:
     a,b,c,d=label['rect']
     if 'bank' in label and a<x+8 and x<c and b<y+8 and y<d:bank_override[mid,n]=label['bank']
   else:outside.add(entry&1023)
  for y in range(after.height):
   for x in range(after.width):
    if after.getpixel((x,y))!=before.getpixel((x,y)) and not any(a<=x<c and b<=y<d for a,b,c,d in (l['rect'] for l in rows)):raise AssertionError('Pixel outside text bounds')
  images[mid]=after;changes[mid]=cells
 free=[t for t in range(len(tiles)//32) if t not in outside and (t in inside or not any(tiles[t*32:(t+1)*32]) or reclaim_unreferenced_nonempty)]
 atlas=bytearray(tiles);cache={tiles[t*32:(t+1)*32]:t for t in range(len(tiles)//32) if t not in free};allocated=[];newmaps={}
 for mid,raw in maps.items():
  rawnew=bytearray(raw);im=images[mid];w=widths.get(mid,32)
  for n in sorted(changes[mid]):
   x=n%w*8;y=n//w*8
   entry=struct.unpack_from('<H',raw,n*2)[0];bank=bank_override.get((mid,n),entry>>12)
   if (mid,n) in bank_override:
    if palette is None:raise ValueError('Palette required for cross-bank label proof')
    words=struct.unpack('<256H',palette);wanted=[];rawbefore=before_images[mid]
    for yy in range(y,y+8):
     for xx in range(x,x+8):
      hit=[l for l in labels.get(mid,[]) if l['rect'][0]<=xx<l['rect'][2] and l['rect'][1]<=yy<l['rect'][3]]
      if hit:
       v=im.getpixel((xx,yy));refbank=hit[-1].get('bank',entry>>12)
      else:v=rawbefore.getpixel((xx,yy));refbank=entry>>12
      wanted.append(None if not v else words[refbank*16+v])
    need={c for c in wanted if c is not None}
    options=list(dict.fromkeys([entry>>12,bank,*range(16)]))
    choices=[b for b in options if need<=set(words[b*16+1:b*16+16])]
    if not choices:raise ValueError('No native bank represents text plus boundary art: '+str((mid,n,need)))
    bank=choices[0];colors={c:j for j,c in reversed(list(enumerate(words[bank*16:bank*16+16]))) if j}
    for j,color in enumerate(wanted):im.putpixel((x+j%8,y+j//8),0 if color is None else colors[color])
   pix=im.crop((x,y,x+8,y+8)).tobytes();tile=bytes(pix[j]|pix[j+1]<<4 for j in range(0,64,2))
   if tile not in cache:
    if not free:raise ValueError('Source-proven private atlas capacity exhausted')
    t=free.pop(0);atlas[t*32:(t+1)*32]=tile;cache[tile]=t;allocated.append(t)
   struct.pack_into('<H',rawnew,n*2,bank<<12|cache[tile])
  newmaps[mid]=bytes(rawnew)
  assert indexed4(bytes(atlas).ljust(32768,b'\0'),newmaps[mid],w).tobytes()==im.tobytes()
  if palette is not None:
   oldrgb=render_map(tiles,raw,palette,w);newrgb=render_map(bytes(atlas),newmaps[mid],palette,w)
   for yy in range(im.height):
    for xx in range(im.width):
     if oldrgb.getpixel((xx,yy))!=newrgb.getpixel((xx,yy)) and not any(a<=xx<c and b<=yy<d for a,b,c,d in (l['rect'] for l in labels.get(mid,[]))):raise AssertionError('RGBA changed outside translated rectangle')
  assert all(raw[n*2:n*2+2]==rawnew[n*2:n*2+2] for n in set(range(len(raw)//2))-changes[mid])
 assert all(atlas[t*32:(t+1)*32]==tiles[t*32:(t+1)*32] for t in set(range(len(tiles)//32))-set(allocated))
 return bytes(atlas),newmaps,{'labels':profiles,'allocated_tiles':allocated,'safe_remaining_tiles':len(free),'reserved_tiles':sorted(set(reserved)|{0}),'changed_map_cells':{str(i):len(c) for i,c in changes.items()},'non_text_pixels_and_untouched_map_cells_preserved':True,'RGBA_nontext_proof':palette is not None},images

def private_extend(source,baseline,append_end,replacements,literals,caller_spans=()):
 if digest(source)!=SOURCE_SHA or len(source)!=0x800000:raise ValueError('Wrong original')
 if len(baseline)!=0x1000000:raise ValueError('Wrong target size')
 for a,n in caller_spans:
  if baseline[a:a+n]!=source[a:a+n]:raise ValueError('Qualified graphic consumer changed: '+hex(a))
 for a in literals:
  if source[a:a+4]!=struct.pack('<I',BASE+ARCHIVE) or baseline[a:a+4]!=source[a:a+4]:raise ValueError('Archive literal changed: '+hex(a))
 rom=bytearray(baseline);cursor=(append_end+3)&~3;start=cursor;writes=[];newptrs={}
 def append(data,tag):
  nonlocal cursor
  cursor=(cursor+3)&~3;a=cursor
  if a<0x800000 or a+len(data)>len(rom) or any(b!=255 for b in rom[a:a+len(data)]):raise ValueError('Occupied/overflow append tail')
  rom[a:a+len(data)]=data;cursor+=len(data);writes.append({'offset':a,'length':len(data),'purpose':tag});return a
 for i,(raw,compressed) in sorted(replacements.items()):
  stored=literal(raw) if compressed else raw;newptrs[i]=(append(stored,'graphic-resource-'+hex(i)),len(stored))
 count=struct.unpack_from('<I',source,ARCHIVE)[0];assert count==737;oldbase=ARCHIVE+4+count*8;arc_at=(cursor+3)&~3;newbase=arc_at+4+count*8;directory=bytearray(struct.pack('<I',count))
 for i in range(count):
  rel,n=struct.unpack_from('<II',source,ARCHIVE+4+i*8);at=oldbase+rel
  assert 0<=at<=at+n<=len(source)
  if i in newptrs:at,n=newptrs[i]
  directory+=struct.pack('<II',(at-newbase)&0xffffffff,n)
 assert append(directory,'private-737entry-archive')==arc_at
 for a in literals:rom[a:a+4]=struct.pack('<I',BASE+arc_at);writes.append({'offset':a,'length':4,'purpose':'qualified-archive-literal'})
 changed=[i for i,(a,b) in enumerate(zip(baseline,rom)) if a!=b]
 for i in changed:
  if not any(w['offset']<=i<w['offset']+w['length'] for w in writes):raise AssertionError('Unexpected write')
 return bytes(rom),{'source_sha256':SOURCE_SHA,'baseline_sha256':digest(baseline),'target_sha256':digest(rom),'append_start':start,'append_end':cursor,'writes':writes,'private_archive':arc_at,'localized_resource_IDs':sorted(newptrs),'archive_literals':list(literals),'caller_spans':[{ 'offset':a,'bytes':n,'sha256':digest(source[a:a+n])} for a,n in caller_spans],'new_CPU_instructions':False,'unchanged_outside_writes':True}
