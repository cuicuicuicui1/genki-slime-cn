"""Native12 town/resident BG Japanese, exact source atlas lifecycle.
Preserves24KiB town atlas, first256 tiles, all unrelated source maps and palettes.
This is an additive work candidate from the documented v16 SHA, not a freeze.
"""
from pathlib import Path
import hashlib,json,struct
from PIL import Image
from cn_codec import ROOT,BASE,SOURCE_SHA
from cn_engine import asm,veneer,load_bdf,bitmap
from gba_main_menu_graphics import resources,SOURCE_PATH,ARCHIVE
from gba_ui_v03 import indexed4
from gba_graphics_engine import literal
from graphics_backgrounds import render_map

BASELINE_SHA='7df827e991cc2415a3b54e0b4dce6ee90cad363f3b881113f2cafe0c27317568'
TILES_ID=0x1C6
PALETTE_ID=0x1C7
HOOK=0x858
RETURN=None # fallback executes the complete18-byte native leaf, no far jump

MAP_IDS=(0x1CE,0x1D7,0x1E4)
OTHER_MAP_IDS=(*range(0x1C8,0x1EF),0x1F0,0x1F1,0x1F3,0x1F4)
# Actual caller uses the12x3 composites1E7..1EE, NOT the unused12x2
# captions1D8..1DE. The failed initial interpretation is preserved in work.
CAPTIONS={0x1E7:('スーランの町・全体','史兰镇全图'),
          0x1E8:('一丁目','一区'),0x1E9:('二丁目','二区'),0x1EA:('三丁目','三区'),
          0x1EB:('スーランビーチ','史兰海滩'),0x1EC:('空き地','空地'),
          0x1ED:('スーランスタジアム','史兰竞技场'),0x1EE:('グランド','球场')}
GETTER_CALLS={0x1E4:(0xC72EC,0xC77AA,0xC7C12),
              0x1D7:(0xC7830,0xC7C94,0xCB5F2,0xCBE9C,0xCC046,0xCC0DE,0xCFCEC),
              0x1CE:(0xC78BE,0xC7D1E),
              **{i:(0xCAB88,0xCABAA) for i in CAPTIONS}}

LABELS={
 0x1CE:[
  {'key':'main','ja':'メイン','cn':'主菜单','rect':[30,139,76,155],'x':32,'y':139,'bg':7},
  {'key':'return','ja':'もどる','cn':'返回','rect':[121,139,152,155],'x':128,'y':139,'bg':7},
  {'key':'rescued_list','ja':'助けたスライム','cn':'获救名单','rect':[164,139,224,155],'x':168,'y':139,'bg':7}],
 0x1D7:[
  {'key':'transported','ja':'はこんだもの','cn':'搬运记录','rect':[26,139,88,155],'x':32,'y':139,'bg':7},
  {'key':'return','ja':'もどる','cn':'返回','rect':[121,139,152,155],'x':128,'y':139,'bg':7},
  {'key':'main','ja':'メイン','cn':'主菜单','rect':[166,139,208,155],'x':168,'y':139,'bg':7}],
 0x1E4:[
  {'key':'items','ja':'アイテム','cn':'物品','rect':[7,65,40,78],'x':12,'y':63,'bg':10},
  {'key':'unit_population','ja':'ひき','cn':'只','rect':[88,32,104,48],'x':88,'y':31,'bg':10},
  {'key':'rescued_list','ja':'助けたスライム','cn':'获救名单','rect':[24,139,86,155],'x':32,'y':139,'bg':7},
  {'key':'return','ja':'もどる','cn':'返回','rect':[121,139,152,155],'x':128,'y':139,'bg':7},
  {'key':'transported','ja':'はこんだもの','cn':'搬运记录','rect':[158,139,215,155],'x':160,'y':139,'bg':7}],
}


def translate(source,active_map=0x1E4,active_caption=None):
 get,_=resources(source);tiles=get(TILES_ID)[2];palette=b'\0\0'+get(PALETTE_ID)[2]
 if len(tiles)!=24576 or len(palette)!=512:raise ValueError('Town24KiB atlas capacity changed')
 selected=(*MAP_IDS,active_caption) if active_caption is not None else MAP_IDS
 maps={mid:get(mid)[2] for mid in selected};font=load_bdf(ROOT/'assets/fonts/fusion12/fusion-pixel-12px-monospaced-zh_hans.bdf')
 outside=set(range(256));inside=set();cells={};images={};caption_profiles=[]
 for mid in OTHER_MAP_IDS:
  if mid not in (*MAP_IDS,*CAPTIONS,*range(0x1D8,0x1DF)):outside.update(v&1023 for v, in struct.iter_unpack('<H',get(mid)[2]))
 def draw(im,value,x,y,ink,rect):
  for ch in value:
   glyph=bitmap(ch,font,12)
   for yy in range(16):
    for xx in range(12):
     if glyph.getpixel((xx,yy)):
      px=x+xx;py=y+yy
      if not(rect[0]<=px<rect[2] and rect[1]<=py<rect[3]):raise ValueError('Native12 stroke outside label '+value)
      im.putpixel((px,py),ink)
   x+=12
 for mid,mp in maps.items():
  width=32 if mid in MAP_IDS else 12;im=indexed4(tiles,mp,width);old=im.copy()
  if mid in CAPTIONS:
   ja,cn=CAPTIONS[mid];rect=[0,4,96,22]
   im.paste(7,tuple(rect));draw(im,cn,(96-len(cn)*12)//2,5,4,rect)
   caption_profiles.append({'archive_ID':mid,'ja':ja,'cn':cn,'rect':rect,'native_px':12,'native_width':len(cn)*12,'ink':4,'background':7,'source_JP_not_official_CN':True})
  else:
   for label in LABELS[mid]:im.paste(label['bg'],tuple(label['rect']));draw(im,label['cn'],label['x'],label['y'],15,label['rect'])
  changed=set()
  for n,(v,) in enumerate(struct.iter_unpack('<H',mp)):
   x=n%width*8;y=n//width*8
   if mid in CAPTIONS or old.crop((x,y,x+8,y+8)).tobytes()!=im.crop((x,y,x+8,y+8)).tobytes():changed.add(n);inside.add(v&1023)
   else:outside.add(v&1023)
  images[mid]=im;cells[mid]=changed
  assert changed
 free=[i for i in range(256,768) if i not in outside]
 # The whole native1C8..1F4 map family (except documented non-map
 # palette1EF/fontatlas1F2) is inventoried above. Preserve every ID used
 # outside edited cells AND the entire dynamic/native glyph prefix0..255.
 # Unreferenced nonblank tiles may be reclaimed, not only zero tiles.
 safe_initial=list(free);newtiles=bytearray(tiles);cache={};allocated=[];newmaps={}
 def cache_variants(blob,slot):
  px=bytes(v for b in blob for v in (b&15,b>>4));base=Image.frombytes('L',(8,8),px)
  for mode,flag in [(None,0),(Image.Transpose.FLIP_LEFT_RIGHT,1024),(Image.Transpose.FLIP_TOP_BOTTOM,2048),(Image.Transpose.ROTATE_180,3072)]:
   image=base if mode is None else base.transpose(mode);pixels=image.tobytes();packed=bytes(pixels[n]|pixels[n+1]<<4 for n in range(0,64,2));cache.setdefault(packed,(slot,flag))
 for i in range(768):
  if i not in free:cache_variants(tiles[i*32:i*32+32],i)
 for mid,mp in maps.items():
  new=bytearray(mp);width=32 if mid in MAP_IDS else 12
  for n in sorted(cells[mid]):
   x=n%width*8;y=n//width*8;px=images[mid].crop((x,y,x+8,y+8)).tobytes();tile=bytes(px[i]|px[i+1]<<4 for i in range(0,64,2))
   if tile not in cache:
    if not free:raise ValueError(f'Safe town atlas slots exhausted at map{mid:X}, cell{n}; initial{len(safe_initial)}, allocated{len(allocated)}; do NOT crop/downscale text')
    at=free.pop(0);newtiles[at*32:at*32+32]=tile;cache_variants(tile,at);allocated.append(at)
   oldv=struct.unpack_from('<H',new,n*2)[0];struct.pack_into('<H',new,n*2,(oldv&0xF000)|cache[tile][0]|cache[tile][1])
  newmaps[mid]=bytes(new)
  assert indexed4(bytes(newtiles),bytes(new),width).tobytes()==images[mid].tobytes()
 assert newtiles[:8192]==tiles[:8192]
 assert all(newtiles[i*32:i*32+32]==tiles[i*32:i*32+32] for i in range(768) if i not in allocated)
 meta={'active_map':active_map,'active_caption':active_caption,'native_px':12,'labels':{hex(k):v for k,v in LABELS.items()},'captions':caption_profiles,'capacity_bytes':24576,'capacity_tiles':768,'first256_tiles_unchanged':True,'allocated_tile_ids':allocated,'free_slots_before':len(safe_initial),'free_slots_after':len(free),'untouched_source_map_tile_ids_unchanged':True,'preserved_other_map_IDs':[i for i in OTHER_MAP_IDS if i not in maps],'unchanged_map_cell_counts':{hex(mid):len(mp)//2-len(cells[mid]) for mid,mp in maps.items()},'source_atlas_sha256':hashlib.sha256(tiles).hexdigest(),'atlas_sha256':hashlib.sha256(newtiles).hexdigest()}
 return bytes(newtiles),newmaps,meta,palette


def extend(baseline,prior_end, *, expected_baseline_sha=BASELINE_SHA):
 source=SOURCE_PATH.read_bytes()
 from capstone import Cs,CS_ARCH_ARM,CS_MODE_THUMB
 # NativeD0904..D0D3B has a second district-header map lifecycle,
 # discovered in diagnostic whole-system getter trace (not inherited proof).
 caption_decoder=Cs(CS_ARCH_ARM,CS_MODE_THUMB);caption_decoder.skipdata=True
 caption_callers=tuple(i.address-BASE for i in caption_decoder.disasm(source[0xD0904:0xD0D3C],BASE+0xD0904) if i.mnemonic=='bl' and i.op_str=='#0x8000858')
 if 0xD09B8 not in caption_callers:raise ValueError('Native secondary header getter discovery failed')
 if hashlib.sha256(source).hexdigest()!=SOURCE_SHA:raise ValueError('Wrong source')
 if hashlib.sha256(baseline).hexdigest()!=expected_baseline_sha:raise ValueError('Wrong v16 font baseline')
 prefix=source[HOOK:HOOK+18]
 if baseline[HOOK:HOOK+18]!=source[HOOK:HOOK+18]:raise ValueError('Source getter already changed')
 get,archive_base=resources(source);oldget,_=resources(baseline)
 for mid in (*OTHER_MAP_IDS,TILES_ID,PALETTE_ID):
  if oldget(mid)!=get(mid):raise ValueError('Source town resource changed')
 rom=bytearray(baseline);cursor=(prior_end+3)&~3;start=cursor
 def append(data):
  nonlocal cursor
  cursor=(cursor+3)&~3;at=cursor
  if at+len(data)>len(rom) or any(v!=255 for v in rom[at:at+len(data)]):raise ValueError('Occupied append tail')
  rom[at:at+len(data)]=data;cursor+=len(data);return at
 variants=[];outputs={}
 for active,caption in [(0x1D7,None),(0x1CE,None),(0x1E4,None),*((0x1E4,i) for i in CAPTIONS)]:
  tiles,maps,info,palette=translate(source,active,caption);map_entries=[]
  for mid,mp in maps.items():
   compressed=get(mid)[2]!=source[get(mid)[0]:get(mid)[0]+get(mid)[1]]
   data=literal(mp) if compressed else mp;at=append(data)
   map_entries.append({'ID':mid,'offset':at,'stored_bytes':len(data),'decoded_bytes':len(mp),'compressed_transport':compressed,'pointer':BASE+at})
  info.update(map_entries=map_entries);variants.append(info)
  outputs[(active,caption)]=(tiles,maps,palette)
 # Make caller maps stable across all district variants; do NOT blindly assume.
 town_variants=[v for v in variants if v['active_map']==0x1E4]
 main_map_bytes=[outputs[(v['active_map'],v['active_caption'])][1][0x1E4] for v in town_variants]
 if any(mp!=main_map_bytes[0] for mp in main_map_bytes):raise ValueError('Townmap allocation varied with district; must pair existingBG map before reload')
 # Only apply the union of changed tile positions. Never reload all24KiB:
 # CA680 has already queued native numbers in5800..5FFF by the second
 # caption read, and wholesale atlas reload would erase those live buffers.
 patch_ranges=[]
 for v in variants:
  low=min(v['allocated_tile_ids'])*32;high=(max(v['allocated_tile_ids'])+1)*32
  if low<8192 or high>0x5800:raise ValueError('Patch span intersects native glyph prefix/counter scratch')
  tiles=outputs[(v['active_map'],v['active_caption'])][0]
  at=append(tiles[low:high]);v.update(tile_patch=at,tile_patch_VRAM=0x06000000+low,tile_patch_bytes=high-low)
  patch_ranges.append([0x06000000+low,0x06000000+high])
 # All3 common page maps retain the same translated tile IDs in every atlas,
 # including transition frames where two native BG layers are both visible.
 for mid in MAP_IDS:
  allmapbytes=[outputs[(v['active_map'],v['active_caption'])][1][mid] for v in variants]
  if any(mp!=allmapbytes[0] for mp in allmapbytes):raise ValueError('Common page layout inconsistent across paired atlases')
 table_rows=[]
 for v in variants:
  mid=v['active_caption'] or v['active_map'];entry=next(e for e in v['map_entries'] if e['ID']==mid)
  for call in (*GETTER_CALLS[mid],*(caption_callers if mid in CAPTIONS else ())):
   # Fingerprint source BL target to native getter.
   from capstone import Cs,CS_ARCH_ARM,CS_MODE_THUMB
   ins=list(Cs(CS_ARCH_ARM,CS_MODE_THUMB).disasm(source[call:call+4],BASE+call))
   if len(ins)!=1 or ins[0].mnemonic!='bl' or ins[0].op_str!='#0x8000858':raise ValueError('Source getter caller fingerprint changed')
   table_rows.append({'ID':mid,'caller':call,'LR':BASE+call+5,'tile_pointer':BASE+v['tile_patch'],'tile_destination':v['tile_patch_VRAM'],'tile_word_count':v['tile_patch_bytes']//4,'map_pointer':entry['pointer']})
 table=append(b''.join(struct.pack('<6I',r['ID'],r['LR'],r['tile_pointer'],r['tile_destination'],r['tile_word_count'],r['map_pointer']) for r in table_rows))
 stub=(cursor+3)&~3
 assembly=f"""push {{r0,r1,r2,r4,r5,r6,r7,lr}}
ldr r3, ={BASE+ARCHIVE}
cmp r0,r3
bne fallback
ldr r3, =0x1ce
cmp r1,r3
beq eligible
ldr r3, =0x1d7
cmp r1,r3
beq eligible
ldr r3, =0x1e4
cmp r1,r3
beq eligible
ldr r3, =0x1e7
cmp r1,r3
blo fallback
ldr r3, =0x1ee
cmp r1,r3
bhi fallback
eligible:
mov r7,lr
ldr r4, ={BASE+table}
ldr r5, ={len(table_rows)}
lookup:
ldr r3,[r4]
cmp r3,r1
bne next
ldr r3,[r4,#4]
cmp r3,r7
beq found
next:
adds r4,#24
subs r5,#1
bne lookup
fallback:
pop {{r0,r1,r2,r4,r5,r6,r7}}
pop {{r3}}
mov lr,r3
pop {{r3}}
ldm r0!,{{r2}}
lsls r1,r1,#16
asrs r1,r1,#13
adds r1,r1,r0
ldr r1,[r1]
lsls r2,r2,#3
adds r0,r0,r2
adds r0,r0,r1
bx lr
found:
ldr r0,[r4,#8]
ldr r1,[r4,#12]
ldr r2,[r4,#16]
copy_tiles:
ldr r3,[r0]
str r3,[r1]
adds r0,#4
adds r1,#4
subs r2,#1
bne copy_tiles
ldr r0,[sp]
ldr r1,[sp,#4]
bl native_leaf
str r1,[sp,#4]
str r2,[sp,#8]
ldr r3,[r4,#20]
str r3,[sp]
pop {{r0,r1,r2,r4,r5,r6,r7}}
pop {{r3}}
mov lr,r3
pop {{r3}}
bx lr
native_leaf:
ldm r0!,{{r2}}
lsls r1,r1,#16
asrs r1,r1,#13
adds r1,r1,r0
ldr r1,[r1]
lsls r2,r2,#3
adds r0,r0,r2
adds r0,r0,r1
bx lr"""
 code=asm(assembly,BASE+stub);assert append(code)==stub;rom[HOOK:HOOK+12]=asm('push {r3}\nldr r3,[pc,#4]\nbx r3\nmov r8,r8',BASE+HOOK)+struct.pack('<I',BASE+stub+1)
 ranges=[(HOOK,12),(start,cursor-start)]
 assert all(any(at<=i<at+n for at,n in ranges) for i,(a,b) in enumerate(zip(baseline,rom)) if a!=b)
 meta={'schema':'gba-v17-town-resident-paired-atlas-gateway','status':'experimental-not-frozen','source_sha256':SOURCE_SHA,'baseline_sha256':expected_baseline_sha,'rom_sha256':hashlib.sha256(rom).hexdigest(),'hook':HOOK,'original_hook_bytes':prefix.hex(),'stub':stub,'stub_bytes':len(code),'assembly':assembly,'hook_bytes':12,'full_native_leaf_original_R3_preserved':True,'table':table,'table_rows':table_rows,'variants':variants,'town_map_allocation_identical_across8_caption_variants':True,'archive_directory_and_source_payloads_unchanged':True,'original_atlas_decoded_bytes':24576,'paired_patch_VRAM_by_variant':patch_ranges,'all3translated_page_map_bytes_identical_between_variants':True,'optional_caption_tiles_preserved_when_base_page_reloads':True,'native_counter_scratch5800_5FFF_preserved':True,'appended_start':start,'append_end':cursor,'transport_label_parent_reason':'はこんだもの includes transportedmonsters, explicitly source dialogue72AC61/72E812; use搬运记录 ratherthan narrower搬运物品. No claim of officialChinese.', 'scope':'Archive+ID+callerLR gated paired native12 common3page layouts and currentdistrict caption. Only3648..9312byte safe union slots copied; never overwrite native5800..5FFF counter scratch. All3page tile IDs identical during overlapping transitionBGs; baseview reload leaves optionalcaption tiles intact. Fullnativegetter18byte leaf reproduced for foreigncalls; originalR3 and all R1/R2 resultregisters preserved. Original archive/font IDs/encodedprose unchanged. Actual12x3 caption1E7..1EE; not unused1D8..1DE. Lifecycle/finalSHA tests required.'}
 return bytes(rom),meta,outputs


def main():
 prior=ROOT/'work/gba-v16-menu-graphics-candidate05';end=json.loads((prior/'redraw-experiment.json').read_text('utf8'))['append_end'];rom,meta,outputs=extend((prior/'slime-cn.gba').read_bytes(),end)
 out=ROOT/'work/gba-v17-town-resident-candidate09';out.mkdir(exist_ok=False);(out/'slime-cn.gba').write_bytes(rom);(out/'experiment.json').write_text(json.dumps(meta,ensure_ascii=False,indent=2),'utf8')
 for (active,caption),(tiles,maps,palette) in outputs.items():
  key=f'{active:03X}-'+(f'{caption:03X}' if caption is not None else 'base');(out/f'atlas-{key}.bin').write_bytes(tiles)
  for mid,mp in maps.items():(out/f'map-{key}-{mid:03X}.bin').write_bytes(mp);render_map(tiles,mp,palette,32 if mid in MAP_IDS else 12).save(out/f'map-{key}-{mid:03X}-cn.png')
 print('Native12 shared-page/caption candidate',meta['rom_sha256'],'variants',len(meta['variants']))
if __name__=='__main__':main()

