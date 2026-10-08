"""Patch actual pre-rendered name-grid resources (8bpp tiles + byte maps).
The name-entry grid is NOT a standard 4bpp u16 BG map. Source decompression is
checked against its real consumer; new literal-mode streams have equal decoded
capacities. Rebuild tile IDs with deduplication, preserving non-letter pixels.
"""
import json,sys,struct
from PIL import Image
from cn_codec import ROOT,BASE
from cn_engine import load_bdf,bitmap
sys.path.insert(0,str(ROOT/'upstream/Translimeation/tools'))
sys.path.insert(0,str(ROOT/'upstream/Translimeation/agent-tools'))
from slime_gfx import Decompressor


def literal(data):
 logical=(b'\x04'+data)
 logical+=b'\0'*((-len(logical))%4)
 body=b''.join(logical[i:i+4][::-1] for i in range(0,len(logical),4))
 stream=struct.pack('<I',(len(data)<<8)|0x70)+body
 actual,mode,end=Decompressor(stream,0).decompress()
 if actual!=data or mode!=4 or end!=len(stream):raise ValueError('Graphics literal roundtrip failed')
 return stream


def graphics_engine(rom,append):
 writes=[];records=[];cfg=json.loads((ROOT/'data/gba-name-entry.json').read_text('utf-8'))
 profile=json.loads((ROOT/'data/gba-font-profile.json').read_text('utf-8'));font=load_bdf(ROOT/'assets/fonts/fusion12/fusion-pixel-12px-monospaced-zh_hans.bdf')
 def add(data,tag):
  at=append(data);writes.append((at,data,tag));return at
 preview=ROOT/'evidence/gba-name-graphics-v02';preview.mkdir(exist_ok=True)
 palette=bytes(128)+Decompressor(rom,0x755ad8).decompress()[0]
 colors=[((v&31)*255//31,((v>>5)&31)*255//31,((v>>10)&31)*255//31) for v, in struct.iter_unpack('<H',palette)]
 for page in range(2):
  table=0x7656e4+page*8;old_tiles,old_map=struct.unpack_from('<II',rom,table)
  tiles=Decompressor(rom,old_tiles-BASE).decompress()[0]
  mp=bytearray(Decompressor(rom,old_map-BASE).decompress()[0])
  if len(tiles)!=16384 or len(mp)!=1024:raise ValueError('Stale name resource sizes')
  # Preserve the complete 32x32 source map, replacing only its sixty cells.
  indexed=Image.new('L',(256,256))
  for i,t in enumerate(mp):
   tile=Image.frombytes('L',(8,8),tiles[t*64:t*64+64]);indexed.paste(tile,(i%32*8,i//32*8))
  for row,text in enumerate(cfg['cn_rows'][page*6:page*6+6]):
   for col,c in enumerate(text):
    x=col*16+(8 if col>=5 else 0);y=row*16
    indexed.paste(113,(x,y,x+16,y+16)) # Original green background palette index.
    glyph=bitmap(c,font,12)
    for yy in range(16):
     for xx in range(12):
      if glyph.getpixel((xx,yy)):indexed.putpixel((x+2+xx,y+yy),profile.get('name_grid_ink',116)) # Existing source palette, not a palette edit.
  newtiles=bytearray();dedup={}
  for i in range(1024):
   x=i%32*8;y=i//32*8;tile=indexed.crop((x,y,x+8,y+8)).tobytes()
   if tile not in dedup:dedup[tile]=len(dedup);newtiles+=tile
   mp[i]=dedup[tile]
  if len(dedup)>256:raise ValueError('Name grid exceeds original 256-tile VRAM budget')
  newtiles=newtiles.ljust(16384,b'\0')
  ta=add(literal(bytes(newtiles)),f'cn-name-grid-{page}-8bpp');ma=add(literal(bytes(mp)),f'cn-name-grid-{page}-byte-map')
  writes.append((table,struct.pack('<II',BASE+ta,BASE+ma),f'cn-name-grid-{page}-resource-pointers'))
  im=Image.new('RGB',indexed.size);im.putdata([colors[v] for v in indexed.tobytes()]);im.save(preview/f'page-{page}.png')
  records.append({'page':page,'table':table,'source_tiles':old_tiles-BASE,'source_map':old_map-BASE,'tiles':ta,'map':ma,'tile_count':len(dedup),'decoded_tiles':16384,'decoded_map':1024,'cells':60,'font':'native Fusion Pixel 12px, centered in original 16px cells; no scaled strokes','ink_palette_index':profile.get('name_grid_ink',116),'background_palette_index':113,'preserved':'all non-letter pixels, original 256-tile buffer, Latin page'})
 # The right-side name-panel labels are separate 4bpp BG tiles, NOT OBJ.
 # Reuse only truly blank tiles unreferenced by either of the two source maps.
 original_tiles=Decompressor(rom,0x74f90c).decompress()[0]
 panel=bytearray(Decompressor(rom,0x74fe74).decompress()[0])
 background=Decompressor(rom,0x74fe54).decompress()[0]
 if len(original_tiles)!=8192 or len(panel)!=1280:raise ValueError('Stale name panel')
 used={v&1023 for raw in (panel,background) for v, in struct.iter_unpack('<H',raw)}
 free=[i for i in range(256) if i not in used and not any(original_tiles[i*32:i*32+32])]
 newtiles=bytearray(original_tiles);tile_ids={original_tiles[i*32:i*32+32]:i for i in range(256)}
 indexed=Image.new('L',(256,160))
 for i,(e,) in enumerate(struct.iter_unpack('<H',panel)):
  t=e&1023
  for yy in range(8):
   for xx in range(8):
    sx=7-xx if e&1024 else xx;sy=7-yy if e&2048 else yy
    b=original_tiles[t*32+sy*4+sx//2] if t<256 else 0;indexed.putpixel((i%32*8+xx,i//32*8+yy),(b>>((sx&1)*4))&15)
 for label,rect,x,y in [('换字',(194,33,230,55),200,35),('完成',(194,113,230,128),200,112)]:
  indexed.paste(11,rect) # original paper background, not window edges
  for k,c in enumerate(label):
   glyph=bitmap(c,font,12)
   for yy in range(16):
    for xx in range(12):
     if glyph.getpixel((xx,yy)):indexed.putpixel((x+k*12+xx,y+yy),15)
  x0,y0,x1,y1=rect
  for ty in range(y0//8,(y1+7)//8):
   for tx in range(x0//8,(x1+7)//8):
    pixels=indexed.crop((tx*8,ty*8,tx*8+8,ty*8+8)).tobytes()
    tile=bytes(pixels[n]|pixels[n+1]<<4 for n in range(0,64,2))
    if tile not in tile_ids:
     if not free:raise ValueError('Name-panel tile budget exhausted')
     at=free.pop(0);newtiles[at*32:at*32+32]=tile;tile_ids[tile]=at
    pos=(ty*32+tx)*2;e=struct.unpack_from('<H',panel,pos)[0]
    struct.pack_into('<H',panel,pos,(e&0xf000)|tile_ids[tile])
 ta=add(literal(bytes(newtiles)),'cn-name-panel-4bpp');ma=add(literal(bytes(panel)),'cn-name-panel-u16-map')
 old_base=BASE+0x755ad8
 if struct.unpack_from('<I',rom,0xd20bc)[0]!=0xffff9e34:raise ValueError('Name tile loader moved')
 if struct.unpack_from('<I',rom,0xd3594)[0]!=BASE+0x74fe74:raise ValueError('Name panel map loader moved')
 writes.append((0xd20bc,struct.pack('<I',(BASE+ta-old_base)&0xffffffff),'cn-name-panel-tile-load-offset'))
 writes.append((0xd3594,struct.pack('<I',BASE+ma),'cn-name-panel-map-pointer'))
 from graphics_backgrounds import render_map
 render_map(bytes(newtiles).ljust(0x8000,b'\0'),bytes(panel),palette,32).save(preview/'panel.png')
 records.append({'page':'panel','source_tiles':0x74f90c,'source_map':0x74fe74,'tiles':ta,'map':ma,'decoded_tiles':8192,'decoded_map':1280,'labels':['换字','完成'],'tile_format':'4bpp + u16 tilemap, not 8bpp/byte grid','preserved':'original palette/background/edges, native 256-tile budget; free slots must be blank and unreferenced by both maps'})
 return writes,{'status':'two actual CJK grid resources and right-panel switch/finish labels localized','records':records}
