"""GBA graphic localization primitives. Indexed native pixels, no screenshot paint.
Read actual resources, retain palettes/buffer sizes, deduplicate 4bpp tiles and
repoint only consumer-traced literals/offsets. No presumed generic BG format.
"""
import struct
from PIL import Image
from cn_codec import ROOT,BASE
from cn_engine import bitmap,load_bdf
from gba_graphics_engine import literal
from slime_gfx import Decompressor
from graphics_backgrounds import render_map


def indexed4(tiles,mp,width=32):
 image=Image.new('L',(width*8,(len(mp)//2//width)*8))
 for i,(e,) in enumerate(struct.iter_unpack('<H',mp)):
  t=e&1023
  if t*32+32>len(tiles):raise ValueError('Map references missing source tile')
  for y in range(8):
   for x in range(8):
    sx=7-x if e&1024 else x;sy=7-y if e&2048 else y
    b=tiles[t*32+sy*4+sx//2]
    image.putpixel((i%width*8+x,i//width*8+y),(b>>((sx&1)*4))&15)
 return image


def pack4(image,source_map,capacity,width=32,fixed_tiles=None):
 if image.width!=width*8 or image.height*image.width!=len(source_map)*32:raise ValueError('Map/image dimension mismatch')
 tiles=bytearray();mapping=bytearray(source_map);seen={};variants={}
 # Some atlases are shared with dynamic layers whose maps are not replaced.
 # Keep explicitly traced fixed IDs; otherwise dedup silently changes blank
 # tile zero and a transparent overlay becomes an opaque corrupt screen.
 for tile_id,tile in sorted((fixed_tiles or {}).items()):
  if tile_id!=len(tiles)//32 or len(tile)!=32:raise ValueError('Fixed tile prefix must be contiguous 32-byte tiles')
  tiles+=tile;seen.setdefault(tile,tile_id)
  px=bytes(v for b in tile for v in (b&15,b>>4));base=Image.frombytes('L',(8,8),px)
  for mode,flag in [(None,0),(Image.Transpose.FLIP_LEFT_RIGHT,1024),(Image.Transpose.FLIP_TOP_BOTTOM,2048),(Image.Transpose.ROTATE_180,3072)]:
   v=base if mode is None else base.transpose(mode);buf=v.tobytes();packed=bytes(buf[n]|buf[n+1]<<4 for n in range(0,64,2));variants.setdefault(packed,(tile_id,flag))
 for i in range(len(mapping)//2):
  x=i%width*8;y=i//width*8;px=image.crop((x,y,x+8,y+8)).tobytes()
  tile=bytes(px[n]|px[n+1]<<4 for n in range(0,64,2))
  match=variants.get(tile)
  if match is None:
   tile_id=len(tiles)//32;seen[tile]=tile_id;tiles+=tile;match=(tile_id,0)
   base=Image.frombytes('L',(8,8),px)
   for mode,flag in [(None,0),(Image.Transpose.FLIP_LEFT_RIGHT,1024),(Image.Transpose.FLIP_TOP_BOTTOM,2048),(Image.Transpose.ROTATE_180,3072)]:
    v=base if mode is None else base.transpose(mode);buf=v.tobytes();packed=bytes(buf[n]|buf[n+1]<<4 for n in range(0,64,2));variants.setdefault(packed,(tile_id,flag))
  e=struct.unpack_from('<H',mapping,i*2)[0]
  struct.pack_into('<H',mapping,i*2,(e&0xf000)|match[0]|match[1])
 if len(tiles)//32>capacity:raise ValueError(f'Tile budget exceeded: {len(tiles)//32}>{capacity}')
 return bytes(tiles).ljust(capacity*32,b'\0'),bytes(mapping),len(tiles)//32


def text(image,value,x,y,ink,font=None,shadow=None):
 font=font or load_bdf(ROOT/'assets/fonts/fusion12/fusion-pixel-12px-monospaced-zh_hans.bdf')
 for c in value:
  if c=='\n':raise ValueError('Provide explicit positioned lines')
  (w,h,gx,gy),_=font[ord(c)]
  advance=6 if w<=8 else 12
  glyph=bitmap(c,font,12)
  if shadow is not None:
   for yy in range(16):
    for xx in range(12):
     if glyph.getpixel((xx,yy)) and x+xx+1<image.width and y+yy+1<image.height:image.putpixel((x+xx+1,y+yy+1),shadow)
  for yy in range(16):
   for xx in range(12):
    if glyph.getpixel((xx,yy)):image.putpixel((x+xx,y+yy),ink)
  x+=advance
 return x


def patch_u32(rom,offset,expected,value,tag):
 if struct.unpack_from('<I',rom,offset)[0]!=expected:raise ValueError('Consumer literal moved '+tag)
 return (offset,struct.pack('<I',value&0xffffffff),tag)


def tutorial_engine(rom,append):
 writes=[]
 original_tiles=Decompressor(rom,0x558bcc).decompress()[0]
 original_map=Decompressor(rom,0x5597d4).decompress()[0]
 if len(original_tiles)!=8192 or len(original_map)!=1280:raise ValueError('Tutorial resource capacity mismatch')
 image=indexed4(original_tiles,original_map)
 # Translate only actual Japanese-text regions; gamepad drawings, numbered
 # A/d-pad shapes, arrows, character diagrams and parchment borders survive.
 for rect,bg in [((10,6,65,21),1),((6,40,73,72),2),((128,41,169,72),2),((184,116,240,159),2),((17,126,72,156),0)]:image.paste(bg,rect)
 # Native dark-blue11 increases contrast over static white/parchment.
 # Keep white START text on animated/transparent background: dark ink there
 # would disappear against the black phases. Geometry/palette stay unchanged.
 text(image,'史莱冲击',11,5,11)
 text(image,'按住A',11,40,11);text(image,'按钮',23,56,11)
 text(image,'十字键',129,41,11);text(image,'伸长',133,57,11)
 text(image,'松开A',191,121,11);text(image,'按钮',192,137,11)
 text(image,'按START键',10,124,1);text(image,'开始游戏',13,140,1)
 # BG2 (control 1A48 / map 0600D000) shares char base 06008000
 # with BG3. Its visible transparent map uses tile 0, even though BG3's
 # patched map has its own IDs. Preserve tile 0 in BOTH consumers.
 if original_tiles[:32]!=bytes(32):raise ValueError('Tutorial transparent tile zero changed')
 tiles,mp,count=pack4(image,original_map,256,fixed_tiles={0:original_tiles[:32]})
 # Title/function tutorial has TWO consumers. Each also derives map/palette
 # from a shared base, so patch both relative offsets rather than assuming a
 # direct-pointer table. Palette byte count and VRAM destinations stay stock.
 tiles_stream=literal(tiles);map_stream=literal(mp)
 tile_at=append(tiles_stream);map_at=append(map_stream)
 writes.extend([(tile_at,tiles_stream,'cn-tutorial-4bpp'),(map_at,map_stream,'cn-tutorial-u16-map')])
 for ptr,map_delta,pal_delta in [(0x811dc,0x811e4,0x811ec),(0xc5f40,0xc5f48,0xc5f50)]:
  writes.append(patch_u32(rom,ptr,BASE+0x558bcc,BASE+tile_at,'cn-tutorial-base'))
  writes.append(patch_u32(rom,map_delta,0xc08,map_at-tile_at,'cn-tutorial-map-offset'))
  writes.append(patch_u32(rom,pal_delta,0xe68,0x559a34-tile_at,'cn-tutorial-palette-offset'))
 evidence=ROOT/'evidence/gba-graphics-v03';evidence.mkdir(exist_ok=True)
 # Source palette is decoded by the original palette loader, unlike regular
 # raw BG palettes. For preview reuse the observed live 16-colour consumer data.
 palette_path=ROOT/'work/gba-graphics-v03/tutorial-palette.bin'
 if palette_path.exists():
  palette=palette_path.read_bytes()
  render_map(tiles,mp,palette,32).save(evidence/'tutorial-cn.png')
 # Preview palette is optional observed state; it is not a build input.
 return writes,{'kind':'tutorial','source_tiles':0x558bcc,'source_map':0x5597d4,'tiles':tile_at,'map':map_at,'decoded_tiles':len(tiles),'decoded_map':len(mp),'tile_count':count,'capacity':256,'fixed_tile_ids':[0],'shared_layer_contract':'BG2 screen map at 0600D000 uses transparent tile 0 from this atlas; preserve exact original bytes','labels':['史莱冲击','按住A按钮','十字键伸长','松开A按钮','按START键开始游戏'],'static_label_ink_palette_index':11,'static_label_color_scope':'title + three control labels only; transparent START instruction stays white1','consumers':['0808116C..0808118A','080C5EC8..080C5EE6'],'source_live_matches':'work/gba-graphics-v03/tutorial-live.json and resource-match.json, full decoded tile/map exact match at VRAM 06008000/0600B800','preview_palette':'live original consumer at 05000040; ROM palette untouched','preserved':'original diagrams/arrows, original capacities, palette and VRAM destinations; no interpolation'}


def file_ui_engine(rom,append,atlas_override=None,reserved_tile_ids=(),direct_pairs=()):
 """Six static warning/sleep instruction maps. Caller source bases are unchanged:
 code also computes native overlay-table addresses relative to those bases.
 A guarded native-decompressor gateway selects paired atlases only for these
 exact source requests, preserving all stock tile IDs used by known raw overlays.
 """
 from cn_engine import asm,veneer
 writes=[];records=[]
 tile_source=0x751b90;tiles=Decompressor(rom,tile_source).decompress()[0]
 if atlas_override is not None:
  if len(atlas_override)!=len(tiles):raise ValueError('File atlas override capacity changed')
  tiles=bytes(atlas_override)
 palette=bytes(128)+Decompressor(rom,0x751ab0).decompress()[0]
 if len(tiles)!=32768:raise ValueError('File atlas capacity changed')
 all_maps=[0x756464,0x75651c,0x7565bc,0x756770,0x756890,0x756a58,0x756c58,0x756e70,0x757030,0x757788]
 used={e&1023 for at in all_maps for e, in struct.iter_unpack('<H',Decompressor(rom,at).decompress()[0])}
 # Reserve the helper rectangles the original callers copy via 08000D1C,
 # plus a conservative prefix that contains borders and runtime number glyphs.
 used|={e&1023 for e, in struct.iter_unpack('<H',rom[0x757174:0x757788])}
 used|=set(range(256))
 used|=set(reserved_tile_ids)
 free_template=[i for i in range(1024) if i not in used]
 configs=[
  (0x7565bc,(16,24,224,72),[(16,24,'即将删除冒险之书！'),(16,40,'删除后将无法恢复。'),(16,56,'请谨慎确认！')]),
  (0x756770,(16,24,224,72),[(16,32,'确定仍要删除吗？')]),
  (0x756a58,(16,56,224,128),[(16,56,'睡眠模式会暂停游戏，'),(16,74,'以降低电量消耗。'),(16,92,'需要暂时休息时，'),(16,110,'可以使用此功能。')]),
  (0x756c58,(16,56,224,128),[(16,56,'开启此设置后，'),(16,74,'随时都能进入睡眠模式。'),(16,92,'睡眠期间，屏幕会关闭，'),(16,110,'这不是机器故障。')]),
  (0x756e70,(16,56,224,128),[(16,56,'睡眠模式的按键组合为：'),(16,74,'SELECT + L + R。'),(16,92,'进入和退出睡眠模式时，'),(16,110,'操作方式相同。')]),
  (0x757030,(16,56,224,128),[(16,56,'睡眠模式不等于存档！'),(16,74,'若在睡眠中关闭电源，'),(16,92,'会回到上次存档的进度。'),(16,110,'请务必注意。')])]
 # The six paired maps always install their complete private atlas first.
 # Reclaim ONLY glyph IDs referenced solely inside the replaced rectangles of
 # these six maps. All unedited map cells, every raw helper, dynamic prefix and
 # localized label IDs are reserved. No claim about undeclared game resources.
 from gba_file_labels import FILE_MAPS,BG_MAP,TASK_RAW_SPAN,_stream_spans
 rectangles={at:rect for at,rect,_ in configs}
 reserved=set(range(256))|set(reserved_tile_ids)
 for at in list(FILE_MAPS)+[BG_MAP]:
  mp=Decompressor(rom,at).decompress()[0];rect=rectangles.get(at)
  for n,(entry,) in enumerate(struct.iter_unpack('<H',mp)):
   tx=n%32*8;ty=n//32*8
   if rect and rect[0]<=tx and tx+8<=rect[2] and rect[1]<=ty and ty+8<=rect[3]:continue
   reserved.add(entry&1023)
 start,end=0x755344,0x756464;compressed=_stream_spans(rom,start,end)
 for off in range(start,end-1,2):
  if not any(a<=off<b for a,b in compressed):reserved.add(struct.unpack_from('<H',rom,off)[0]&1023)
 for off in range(TASK_RAW_SPAN[0],TASK_RAW_SPAN[1]-1,2):reserved.add(struct.unpack_from('<H',rom,off)[0]&1023)
 free_template=sorted(set(range(1024))-reserved)
 pairs=[];evidence=ROOT/'evidence/gba-graphics-v03';evidence.mkdir(exist_ok=True)
 for source,rect,lines in configs:
  oldmap=Decompressor(rom,source).decompress()[0];mp=bytearray(oldmap);image=indexed4(tiles,oldmap)
  image.paste(8,rect)
  for x,y,value in lines:
   if text(image,value,x,y,9,shadow=None)>rect[2]:raise ValueError('File UI text exceeds explicit rectangle')
  newtiles=bytearray(tiles);free=list(free_template);variants={}
  for tile_id in range(1024):
   packed=tiles[tile_id*32:tile_id*32+32];px=bytes(v for b in packed for v in (b&15,b>>4));base=Image.frombytes('L',(8,8),px)
   for mode,flag in [(None,0),(Image.Transpose.FLIP_LEFT_RIGHT,1024),(Image.Transpose.FLIP_TOP_BOTTOM,2048),(Image.Transpose.ROTATE_180,3072)]:
    v=base if mode is None else base.transpose(mode);buf=v.tobytes();key=bytes(buf[n]|buf[n+1]<<4 for n in range(0,64,2));variants.setdefault(key,(tile_id,flag))
  allocated=[];x0,y0,x1,y1=rect
  for ty in range(y0//8,(y1+7)//8):
   for tx in range(x0//8,x1//8):
    px=image.crop((tx*8,ty*8,tx*8+8,ty*8+8)).tobytes();packed=bytes(px[n]|px[n+1]<<4 for n in range(0,64,2));match=variants.get(packed)
    if match is None:
     if not free:raise ValueError('File UI allocation exceeds safe unreferenced tile set '+hex(source))
     tid=free.pop(0);allocated.append(tid);newtiles[tid*32:tid*32+32]=packed;match=(tid,0);variants[packed]=match
    struct.pack_into('<H',mp,(ty*32+tx)*2,0xb000|match[0]|match[1])
  # Everything outside the edited rectangle and allocated safe IDs remains
  # byte-identical, including the original Japanese atlas for other screens.
  for i in range(1024):
   if i not in allocated:assert newtiles[i*32:i*32+32]==tiles[i*32:i*32+32]
  tiledata=literal(bytes(newtiles));mapdata=literal(bytes(mp));ta=append(tiledata);ma=append(mapdata)
  writes.extend([(ta,tiledata,'cn-file-ui-atlas-'+hex(source)),(ma,mapdata,'cn-file-ui-map-'+hex(source))]);pairs.append((BASE+source,BASE+ma,BASE+ta,0x06000000))
  render_map(bytes(newtiles),bytes(mp),palette,32).save(evidence/f'file-{source:06x}-cn.png')
  records.append({'kind':'file-ui','source_tiles':tile_source,'source_map':source,'request_map':source,'tiles':ta,'map':ma,'decoded_tiles':32768,'decoded_map':len(mp),'allocated_tiles':allocated,'safe_spare_tile_count':len(free_template),'lines':[v for _,_,v in lines],'edit_rectangle':list(rect),'consumer':'source requests pass through 08098AC8; original caller base/relative overlay tables unchanged','original_tile_ids_preserved_except_safe_allocations':True,'scope':'warning/sleep instructions only, not selection OBJ or all file menu states','font':'native Fusion12 no shadow','allocation_scope':'paired map rectangles only; unedited maps/raw/dynamicprefix/labels reserved','reserved_tiles':sorted(reserved)})
 pairs.extend((request,replacement,0,0) for request,replacement in direct_pairs)
 tabledata=b''.join(struct.pack('<4I',*row) for row in pairs)+b'\0'*16;table=append(tabledata);writes.append((table,tabledata,'file-ui-decode-pairs'))
 stub_at=append(b'\0'*512)
 assembly=f'''push {{r0,r1,r2,r3,r4,r5,lr}}
ldr r4, ={BASE+table}
search:
ldr r5,[r4]
cmp r5,#0
beq stock
cmp r5,r0
beq paired
adds r4,#16
b search
paired:
ldr r0,[r4,#8]
cmp r0,#0
beq direct
ldr r1,[r4,#12]
bl original
ldr r0,[r4,#4]
ldr r1,[sp,#4]
bl original
b done
direct:
ldr r0,[r4,#4]
ldr r1,[sp,#4]
bl original
b done
stock:
ldr r0,[sp]
ldr r1,[sp,#4]
bl original
done:
add sp,#16
pop {{r4,r5}}
pop {{r3}}
bx r3
original:
push {{r4,r5,r6,r7,lr}}
mov r4,r8
mov r5,r9
mov r6,r10
ldr r3, =0x08098AD1
bx r3'''
 code=asm(assembly,BASE+stub_at)
 if len(code)>512:raise ValueError('File UI decode gateway exceeds allocation')
 if rom[0x98ac8:0x98ad0]!=bytes.fromhex('f0b544464d465646'):raise ValueError('Native decoder prologue moved')
 writes.extend([(stub_at,code,'file-ui-decode-gateway'),(0x98ac8,veneer(BASE+stub_at,3),'file-ui-native-decode-hook')]);(ROOT/'build/file-ui-gateway.s').write_text(assembly,'utf-8')
 return writes,records,{'gateway':stub_at,'pairs_table':table,'pair_count':len(pairs),'direct_pair_count':len(direct_pairs),'hook':0x98ac8,'design':'original source arguments remain in calling code; matched map calls upload matching original-ID atlas then decode CN map. Stock requests transparently follow original ARMv4T native consumer.'}
