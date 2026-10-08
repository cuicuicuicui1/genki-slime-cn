"""Main pause-menu BG localization: exact source caller and paired source maps.
Isolated candidate until live natural menu/overlays are validated.
"""
import hashlib,json,struct
from pathlib import Path
from PIL import Image
from cn_codec import ROOT,BASE,SOURCE_SHA
from cn_engine import asm,veneer,load_bdf,bitmap
from gba_ui_v03 import indexed4
from gba_graphics_engine import literal
from slime_gfx import Decompressor
from graphics_backgrounds import render_map

ARCHIVE=0x765FA8
HOOK=0xC70FC
RETURN=0x080C7105
MAP_IDS=(0xD3,0xD4)
TILES_ID=0xDF
CAPTION_HOOK=0xC8214
CAPTION_RETURN=0x080C821D
CAPTIONS={
 0x103:{'ja':'ノッケの森','cn':'诺克森林','source_text_ID':'dialogue-714F69'},
 0x105:{'ja':'ウルオッター川','cn':'乌鲁奥塔河','source_text_ID':'dialogue-71A92C'},
 0x107:{'ja':'ニコミスキー鉱山','cn':'尼科米斯基矿山','source_text_ID':'dialogue-716293'},
 0x109:{'ja':'スライムのしっぽ','cn':'史莱姆的尾巴','source_text_ID':'dialogue-7158C9'},
 0x10A:{'ja':'ミオ・ロシタル','cn':'米欧·罗西塔尔','source_text_ID':'dialogue-71C55F'},
 0x104:{'ja':'ノッケの森のおく','cn':'诺克森林深处','source_text_ID':'dialogue-72BAAE'},
 0x106:{'ja':'カラカラ水源','cn':'卡拉卡拉水源','source_text_ID':'dialogue-71F4AF'},
 0x108:{'ja':'メラゾマ火山','cn':'梅拉佐马火山','source_text_ID':'dialogue-7216EB'},
}
PALETTE_ID=0xE0
from project_paths import SOURCE_PATH
# Final labels are source-image parent judgments, not automated kana density.
LABELS=[
 {'key':'title','ja':'スライムのしっぽ','cn':'史莱姆的尾巴','rect':[40,16,136,32],'x':40,'y':16,'px':16,'background':'green','reason':'Literal source heading retained rather than inventing diary official name.'},
 {'key':'rescued','ja':'たすけたかず','cn':'救出数量','rect':[40,52,112,68],'x':42,'y':51,'px':12,'background':'green'},
 {'key':'town_population','ja':'まちにいるかず','cn':'镇上人数','rect':[40,76,118,92],'x':42,'y':75,'px':12,'background':'green','reason':'Residents in town, not not-yet-rescued or current stock.'},
 {'key':'unit_rescued','ja':'ひき','cn':'只','rect':[176,54,194,68],'x':178,'y':52,'px':12,'background':'green'},
 {'key':'unit_town','ja':'ひき','cn':'只','rect':[176,78,194,92],'x':178,'y':76,'px':12,'background':'green'},
 {'key':'letters','ja':'てがみ','cn':'书信','rect':[33,141,65,154],'x':35,'y':139,'px':12,'background':'button'},
 {'key':'return','ja':'もどる','cn':'返回','rect':[123,141,152,154],'x':124,'y':139,'px':12,'background':'button'},
 {'key':'map','ja':'ちず','cn':'地图','rect':[182,141,211,154],'x':183,'y':139,'px':12,'background':'button'},
]


def resources(rom):
 count=struct.unpack_from('<I',rom,ARCHIVE)[0];base=ARCHIVE+4+count*8
 if count!=0x2E1: raise ValueError('Main-menu archive directory fingerprint changed')
 def get(index):
  entry=ARCHIVE+4+index*8;rel,size=struct.unpack_from('<II',rom,entry);at=base+rel;raw=rom[at:at+size]
  data=Decompressor(raw,0).decompress()[0] if raw[0]==0x70 else raw
  return at,size,data
 return get,base


def translate_images(source):
 get,_=resources(source)
 tiles=get(TILES_ID)[2];palette=b'\0\0'+get(PALETTE_ID)[2];maps={i:get(i)[2] for i in MAP_IDS}
 maps.update({i:get(i)[2] for i in CAPTIONS})
 widths={i:(32 if i in MAP_IDS else 12) for i in maps}
 if len(tiles)!=30720 or any(len(m)!=(2048 if i in MAP_IDS else 48) for i,m in maps.items()) or len(palette)!=512:raise ValueError('Source main-menu decoded capacity changed')
 if tuple(struct.unpack_from('<8h',source,0x764E68))!=tuple(CAPTIONS):raise ValueError('Source eight area-caption table changed')
 fonts={12:load_bdf(ROOT/'assets/fonts/fusion12/fusion-pixel-12px-monospaced-zh_hans.bdf'),16:load_bdf(ROOT/'assets/fonts/unifont16/unifont-16.0.03.bdf')}
 images={};modified_cells={};outside_ids=set(range(256));inside_ids=set()
 # Keep every raw native trophy/heart/helper overlay used after C7D70.
 for i in range(0xE8,0xF3):
  outside_ids.update(v&1023 for v, in struct.iter_unpack('<H',get(i)[2]))
 caption_profiles=[]
 for mid,mp in maps.items():
  image_width=widths[mid]
  im=indexed4(tiles.ljust(32768,b'\0'),mp,image_width);old=im.copy()
  if mid in CAPTIONS:
   caption=CAPTIONS[mid]
   size=16 if len(caption['cn'])*16<=96 else 12
   advances=[(6 if size==12 and fonts[size][ord(ch)][0][0]<=8 else size) for ch in caption['cn']]
   rendered_width=sum(advances);cursor=(96-rendered_width)//2
   if rendered_width>96:raise ValueError('Full area caption exceeds source96px field')
   if {v>>12 for v, in struct.iter_unpack('<H',mp)}!={7}:raise ValueError('Area caption source palette changed')
   im.paste(10,(0,0,96,16))
   for ch,advance in zip(caption['cn'],advances):
    glyph=bitmap(ch,fonts[size],size)
    for yy in range(16):
     for xx in range(size):
      if glyph.getpixel((xx,yy)):
       if not 0<=cursor+xx<96:raise ValueError('Caption native stroke clipped')
       im.putpixel((cursor+xx,yy),15)
    cursor+=advance
   caption_profiles.append({'archive_ID':mid,**caption,'native_font_px':size,'rendered_pixels':rendered_width,'full_name_preserved':True,'source_map_offset':get(mid)[0],'map_bytes':48,'source_RGBA_palette_bank':7,'localized_ink_index':15})
  for label in (LABELS if mid in MAP_IDS else []):
   rect=label['rect'];x0,y0,x1,y1=rect
   for y in range(y0,y1):
    for x in range(x0,x1):
     bank=struct.unpack_from('<H',mp,(y//8*32+x//8)*2)[0]>>12
     if label['background']=='green':
      if bank not in (7,8):raise ValueError('Main green text crosses art palette: '+label['key'])
      im.putpixel((x,y),11 if bank==8 else 10)
     else:
      if bank!=9:raise ValueError('Main button text crosses icon palette')
      # Preserve highlights/outline: only erase source black lettering inside
      # the source-text rectangle; edge gradients are untouched.
      if old.getpixel((x,y))==15:im.putpixel((x,y),7)
   cursor=label['x'];glyphs=[]
   for ch in label['cn']:
    glyph=bitmap(ch,fonts[label['px']],label['px']);glyphs.append(glyph)
    for yy in range(16):
     for xx in range(label['px']):
      if glyph.getpixel((xx,yy)):
       x=cursor+xx;y=label['y']+yy
       if not (x0<=x<x1 and y0<=y<y1):raise ValueError('Native stroke outside authorized label rectangle: '+label['key'])
       im.putpixel((x,y),15)
    cursor+=label['px']
  changed_cells=set()
  for n,(entry,) in enumerate(struct.iter_unpack('<H',mp)):
   x=n%image_width*8;y=n//image_width*8
   changed=im.crop((x,y,x+8,y+8)).tobytes()!=old.crop((x,y,x+8,y+8)).tobytes()
   if changed:inside_ids.add(entry&1023);changed_cells.add(n)
   else:outside_ids.add(entry&1023)
  images[mid]=im;modified_cells[mid]=changed_cells
  changed_pixels=[(x,y) for y in range(im.height) for x in range(im.width) if old.getpixel((x,y))!=im.getpixel((x,y))]
  if not changed_pixels:raise ValueError('Empty menu translation')
  if mid in MAP_IDS:assert all(any(r['rect'][0]<=x<r['rect'][2] and r['rect'][1]<=y<r['rect'][3] for r in LABELS) for x,y in changed_pixels)
 # Only reclaim a source tile if no untouched cell uses it in either map,
 # and it belongs to edited text or is blank. All other native content stays.
 free=[i for i in range(960) if i not in outside_ids and (i in inside_ids or not any(tiles[i*32:i*32+32]))]
 newtiles=bytearray(tiles);tile_ids={tiles[i*32:i*32+32]:i for i in range(960) if i not in free};allocations=[];newmaps={}
 for mid,mp in maps.items():
  out=bytearray(mp);image=images[mid];image_width=widths[mid]
  for n in sorted(modified_cells[mid]):
   x=n%image_width*8;y=n//image_width*8;pixels=image.crop((x,y,x+8,y+8)).tobytes();tile=bytes(pixels[i]|pixels[i+1]<<4 for i in range(0,64,2))
   if tile not in tile_ids:
    if not free:raise ValueError('Main private atlas safe tile capacity exhausted')
    slot=free.pop(0);newtiles[slot*32:slot*32+32]=tile;tile_ids[tile]=slot;allocations.append(slot)
   entry=struct.unpack_from('<H',out,n*2)[0];struct.pack_into('<H',out,n*2,(entry&0xF000)|tile_ids[tile])
  newmaps[mid]=bytes(out)
  assert indexed4(bytes(newtiles).ljust(32768,b'\0'),bytes(out),image_width).tobytes()==images[mid].tobytes()
 # Identity/stability of reused data is proven against full source byte masks.
 assert len(newtiles)==30720 and newtiles[:8192]==tiles[:8192]
 assert all(newtiles[i*32:i*32+32]==tiles[i*32:i*32+32] for i in range(960) if i not in allocations)
 return bytes(newtiles),newmaps,{'labels':LABELS,'area_captions':caption_profiles,'all_source_trophy_heart_helper_tiles_preserved':True,'capacity_tiles':960,'unchanged_original_prefix_tiles':256,'allocated_tile_ids':allocations,'new_tile_count':len(allocations),'safe_unused_tile_slots_remaining':len(free),'source_tiles_sha256':hashlib.sha256(tiles).hexdigest(),'new_tiles_sha256':hashlib.sha256(newtiles).hexdigest(),'all_pixels_outside_label_rectangles_unchanged':True,'all_unchanged_map_cells_byte_identical':True,'dynamic_counter_slots_3C0_3D7_and_3E0_3F7_not_in_atlas':True,'original_palette_bytes_unchanged':True,'source_maps':{hex(mid):{'offset':get(mid)[0],'stored_bytes':get(mid)[1],'decoded_bytes':len(mp),'source_sha256':hashlib.sha256(mp).hexdigest(),'modified_cells':len(modified_cells[mid])} for mid,mp in maps.items()}},palette


def build_candidate(base_rom,prior_metadata=None):
 source=SOURCE_PATH.read_bytes()
 if hashlib.sha256(source).hexdigest()!=SOURCE_SHA:raise ValueError('Wrong original ROM')
 if HOOK%4:raise ValueError('Main-menu Thumb veneer must be word-aligned')
 if CAPTION_HOOK%4 or base_rom[CAPTION_HOOK:CAPTION_HOOK+12]!=source[CAPTION_HOOK:CAPTION_HOOK+12]:raise ValueError('Area-caption source hook/resume sequence changed')
 if base_rom[HOOK:HOOK+16]!=source[HOOK:HOOK+16]:raise ValueError('Main-menu caller or resumed native decoder sequence already changed')
 # Direct-source main-menu hook only; DF archive remains original for all other
 # archive consumers. D3/D4 maps belong to this exact traced caller.
 get,archive_base=resources(source);base_get,_=resources(base_rom)
 for index in [TILES_ID,PALETTE_ID,*MAP_IDS,*CAPTIONS]:
  if base_get(index)!=get(index):raise ValueError('Main-menu source resource not unchanged')
 tiles,maps,meta,palette=translate_images(source)
 rom=bytearray(base_rom)
 if prior_metadata is None:raise ValueError('Pass metadata returned by resident12 candidate; no historical directory dependency')
 prior=prior_metadata
 if hashlib.sha256(base_rom).hexdigest()!=prior['rom_sha256']:raise ValueError('Wrong isolated resident candidate')
 start=max(r['offset']+r['bytes'] for r in prior['writes']);cursor=start
 def append(data):
  nonlocal cursor
  cursor=(cursor+3)&~3;offset=cursor
  if not all(v==255 for v in rom[cursor:cursor+len(data)]):raise ValueError('Occupied append tail')
  if cursor+len(data)>len(rom):raise ValueError('ROM append overflow')
  rom[cursor:cursor+len(data)]=data;cursor+=len(data);return offset
 tile_at=append(literal(tiles));map_entries=[]
 for mid,newmap in maps.items():
  if mid not in MAP_IDS:continue
  raw=literal(newmap);at=append(raw);entry=ARCHIVE+4+mid*8
  rom[entry:entry+8]=struct.pack('<II',at-archive_base,len(raw));map_entries.append({'archive_index':mid,'entry':entry,'offset':at,'stored_bytes':len(raw),'decoded_bytes':2048})
 stub=(cursor+3)&~3
 assembly=f'''ldr r0, ={BASE+tile_at}
ldr r3, ={RETURN}
bx r3'''
 code=asm(assembly,BASE+stub);assert append(code)==stub
 rom[HOOK:HOOK+8]=veneer(BASE+stub)
 caption_entries=[]
 for mid in CAPTIONS:
  at=append(maps[mid]);caption_entries.append({'archive_ID':mid,'pointer':BASE+at,'offset':at,'bytes':48})
 caption_table=append(b''.join(struct.pack('<II',r['archive_ID'],r['pointer']) for r in caption_entries))
 caption_stub=(cursor+3)&~3
 caption_assembly=f'''push {{r4,r5,r6,lr}}
mov r5,r0
mov r6,r1
ldr r4, ={BASE+caption_table}
movs r2,#8
find:
ldr r3,[r4]
cmp r3,r6
beq match
adds r4,#8
subs r2,#1
bne find
mov r0,r5
mov r1,r6
bl stock_getter
b finish
match:
ldr r0,[r4,#4]
finish:
mov r1,r0
pop {{r4,r5,r6}}
pop {{r3}}
mov r0,r4
ldr r3, ={CAPTION_RETURN}
bx r3
stock_getter:
ldr r3, =0x08000859
bx r3'''
 caption_code=asm(caption_assembly,BASE+caption_stub)
 assert append(caption_code)==caption_stub
 # This entry needs original r0 archive for foreign-ID fallback. Use r3
 # scratch for the veneer, not r0 (the earlier fallback test caught it).
 rom[CAPTION_HOOK:CAPTION_HOOK+8]=veneer(BASE+caption_stub,reg=3)
 patches=[(HOOK,8),(CAPTION_HOOK,8),*((r['entry'],8) for r in map_entries),(start,cursor-start)]
 changed=[i for i,(a,b) in enumerate(zip(base_rom,rom)) if a!=b]
 assert all(any(at<=i<at+n for at,n in patches) for i in changed)
 meta.update(caption_hook=CAPTION_HOOK,caption_hook_source_bytes=source[CAPTION_HOOK:CAPTION_HOOK+8].hex(),caption_entries=caption_entries,caption_table=caption_table,caption_stub=caption_stub,caption_stub_bytes=len(caption_code),caption_assembly=caption_assembly,caption_original_archive_entries_unchanged=True,schema='gba-main-menu-graphics-experiment',status='candidate-not-frozen',source_sha256=SOURCE_SHA,baseline_resident_candidate_sha256=prior['rom_sha256'],rom_sha256=hashlib.sha256(rom).hexdigest(),hook=HOOK,source_hook_bytes=source[HOOK:HOOK+8].hex(),stub=stub,stub_assembly=assembly,stub_bytes=len(code),tile_stream=tile_at,tile_stream_bytes=len(literal(tiles)),map_entries=map_entries,archive_DF_and_palette_and_all_other_entries_unchanged=True,append_start=start,append_end=cursor,changed_bytes=len(changed),scope='Main pause stats/units/footer in D3&D4, staticdefault+8runtime area captions via localC8214 raw-map gateway. Exact local caller loads paired private30720-byte atlas, original DF archive untouched. No natural menu/all runtime overlays validated yet; no global palette or original fonts/IDs change.')
 return bytes(rom),meta,tiles,maps,palette


def main():
 base=ROOT/'work/gba-v16-resident12-candidate/slime-cn.gba';rom,meta,tiles,maps,palette=build_candidate(base.read_bytes());out=ROOT/'work/gba-v16-menu-graphics-candidate03';out.mkdir(exist_ok=False)
 (out/'slime-cn.gba').write_bytes(rom);(out/'experiment.json').write_text(json.dumps(meta,ensure_ascii=False,indent=2),'utf8')
 preview_tiles=bytearray(tiles.ljust(32768,b'\0'))
 # Reproduce traced native C7D80 counter initialization for static previews,
 # not an ROM atlas expansion. Main DF still decodes only30720 bytes.
 for start in (0x3C0,0x3E0):
  for n in range(24):preview_tiles[(start+n)*32:(start+n+1)*32]=tiles[0x7E0:0x800]
 for mid,mp in maps.items():render_map(bytes(preview_tiles),mp,palette,32 if mid in MAP_IDS else 12).save(out/f'main-menu-{mid:03X}-cn.png')
 (out/'main-tiles.bin').write_bytes(tiles)
 for mid,mp in maps.items():(out/f'main-map-{mid:03X}.bin').write_bytes(mp)
 print('Main menu native12/16 source-judged graphics candidate:',meta['rom_sha256'],'allocated',meta['new_tile_count'],'free',meta['safe_unused_tile_slots_remaining'])

if __name__=='__main__':main()
