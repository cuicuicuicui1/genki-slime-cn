"""Clear native16 resident location/status cards, exact three source consumers.
Reuses per-card exclusive slots (never nativeprefix/counters/v17 glyph slots)
through scatter copies at actual card getter sites; no global getter rewrite.
"""
from pathlib import Path
import hashlib,json,struct
from PIL import Image
from cn_codec import ROOT,BASE,SOURCE_SHA
from cn_engine import asm,bitmap,load_bdf
from gba_main_menu_graphics import SOURCE_PATH,resources,ARCHIVE
from gba_town_resident_graphics import OTHER_MAP_IDS,TILES_ID
from gba_ui_v03 import indexed4

BASELINE_SHA='1d24b44a2ab48d64f9ccf12db34aafa3ce1325e6b49fffe0a8f218a7a826b79b'
PROFILES={
 0x1E0:{'ja':'ヒミツじゃ♥','cn':'秘密哟','rect':[24,32,76,48],'x':24,'y':32,'hook':0xCFCBC,'getter_call':0xCFCC4,'resume':0xCFCC8,'emulate_add_r1':False,'semantics':'Hidden location caption is secret, not instruction to reveal or to keep a player secret. Original heart beyond text mask retained.'},
 0x1E1:{'ja':'行ったコトないばしょ','cn':'未到访地点','rect':[8,32,104,48],'x':16,'y':32,'hook':0xCFC54,'getter_call':0xCFC5A,'resume':0xCFC60,'emulate_add_r1':True,'semantics':'A location the player has not visited; not location the resident has never visited and not unrecovered treasure.'},
 0x1E2:{'ja':'はやくたすけてねー！','cn':'快救我吧！','rect':[8,32,104,48],'x':16,'y':32,'hook':0xD00EC,'getter_call':0xD00F4,'resume':0xD00F8,'emulate_add_r1':False,'semantics':'Rescue plea from the still-captured resident; keep urgency and friendly request, not claim rescued.'},
}


def translate(source,v17_meta):
 get,_=resources(source);font=load_bdf(ROOT/'assets/fonts/unifont16/unifont-16.0.03.bdf');original=get(TILES_ID)[2]
 outside=set(range(256));images={};changed={};source_cells={}
 for id in OTHER_MAP_IDS:
  mp=get(id)[2]
  if id not in PROFILES:outside.update(v&1023 for v, in struct.iter_unpack('<H',mp));continue
  im=indexed4(original,mp,14);old=im.copy();row=PROFILES[id];im.paste(5,tuple(row['rect']));x=row['x']
  for ch in row['cn']:
   glyph=bitmap(ch,font,16)
   for y in range(16):
    for xx in range(16):
     if glyph.getpixel((xx,y)):
      px=x+xx;py=row['y']+y
      if not(row['rect'][0]<=px<row['rect'][2] and row['rect'][1]<=py<row['rect'][3]):raise ValueError('Native16 glyph exceeds card rectangle')
      im.putpixel((px,py),9)
   x+=16
  cells=set()
  for n,(entry,) in enumerate(struct.iter_unpack('<H',mp)):
   x=n%14*8;y=n//14*8
   if im.crop((x,y,x+8,y+8)).tobytes()!=old.crop((x,y,x+8,y+8)).tobytes():cells.add(n)
   else:outside.add(entry&1023)
  images[id]=im;changed[id]=cells;source_cells[id]=[entry&1023 for entry, in struct.iter_unpack('<H',mp)]
 v17_union={t for v in v17_meta['variants'] for t in v['allocated_tile_ids']}
 safe=[t for t in range(256,0x5800//32) if t not in outside and t not in v17_union]
 outputs={};profiles=[]
 for id,row in PROFILES.items():
  free=list(safe);mp=bytearray(get(id)[2]);im=images[id];newtiles={};cache={original[i*32:i*32+32]:i for i in range(0x5800//32) if i not in safe and i not in v17_union};alloc=[]
  for n in sorted(changed[id]):
   x=n%14*8;y=n//14*8;px=im.crop((x,y,x+8,y+8)).tobytes();tile=bytes(px[i]|px[i+1]<<4 for i in range(0,64,2))
   if tile not in cache:
    if not free:raise ValueError('Per-card native16 safe tile capacity exhausted; do not shrink fonts')
    slot=free.pop(0);cache[tile]=slot;newtiles[slot]=tile;alloc.append(slot)
   entry=struct.unpack_from('<H',mp,n*2)[0];struct.pack_into('<H',mp,n*2,(entry&0xF000)|cache[tile])
  # Independent tiles are valid under original and all v17 atlas states:
  # reserved v17 glyph slots never read/reused by translated cards.
  tiles=bytearray(original)
  for slot,tile in newtiles.items():tiles[slot*32:(slot+1)*32]=tile
  assert indexed4(tiles,bytes(mp),14).tobytes()==im.tobytes()
  samples=[]
  for ch in row['cn']:
   glyph=bitmap(ch,font,16);samples.append({'char':ch,'native_ink_pixels':sum(bool(glyph.getpixel((x,y))) for y in range(16) for x in range(16)),'bitmap_SHA256':hashlib.sha256(glyph.tobytes()).hexdigest()})
  profiles.append({**row,'ID':id,'native_font_px':16,'advance_px':16,'ink':9,'background_index':5,'width_tiles':14,'height_tiles':9,'decoded_map_bytes':252,'safe_exclusive_slots':safe,'allocated_tile_IDs':alloc,'changed_map_cells':sorted(changed[id]),'native_strokes':samples,'source_map_SHA256':hashlib.sha256(get(id)[2]).hexdigest(),'target_map_SHA256':hashlib.sha256(mp).hexdigest(),'all_outside_text_pixels_unchanged':True,'all_map_entries_outside_edited_cells_unchanged':True,'v17_slot_overlap':False})
  outputs[id]={'map':bytes(mp),'tiles':bytes(tiles),'scatter':newtiles,'image':im}
 return outputs,profiles


def extend(baseline,append_end,v17_meta, *, expected_baseline_sha=BASELINE_SHA):
 source=SOURCE_PATH.read_bytes()
 if hashlib.sha256(source).hexdigest()!=SOURCE_SHA or hashlib.sha256(baseline).hexdigest()!=expected_baseline_sha:raise ValueError('Wrong original/v18 baseline')
 outputs,profiles=translate(source,v17_meta);rom=bytearray(baseline);start=cursor=(append_end+3)&~3
 def append(data):
  nonlocal cursor
  cursor=(cursor+3)&~3;at=cursor
  if at+len(data)>len(rom) or any(v!=255 for v in rom[at:at+len(data)]):raise ValueError('Occupied/overflow append span')
  rom[at:at+len(data)]=data;cursor+=len(data);return at
 for row in profiles:
  id=row['ID'];hook=row['hook'];call=row['getter_call'];resume=row['resume'];original=source[hook:hook+12]
  if hook%4 or baseline[hook:hook+12]!=original:raise ValueError('Original resident card source-hook fingerprint changed')
  from capstone import Cs,CS_ARCH_ARM,CS_MODE_THUMB
  md=Cs(CS_ARCH_ARM,CS_MODE_THUMB);ins=list(md.disasm(source[call:call+4],BASE+call))
  if len(ins)!=1 or ins[0].mnemonic!='bl' or ins[0].op_str!='#0x8000858':raise ValueError('Source card getter caller changed')
  map_at=append(outputs[id]['map']);scatter=[]
  for slot,tile in sorted(outputs[id]['scatter'].items()):
   at=append(tile);scatter.append({'tile_ID':slot,'pointer':BASE+at,'destination':0x06000000+slot*32,'bytes':32})
  table=append(b''.join(struct.pack('<II',s['pointer'],s['destination']) for s in scatter));stub=(cursor+3)&~3
  # Entry has one saved originalr3. Restore full live native registers and
  # emit originalcallLR, not wrapperLR. Original getter R1/R2 results replayed.
  assembly=f'''push {{r0,r1,r2,r4,r5,r6,r7,lr}}
ldr r4, ={BASE+table}
movs r5, #{len(scatter)}
next_tile:
ldr r0,[r4]
ldr r1,[r4,#4]
movs r6,#8
copy_words:
ldr r2,[r0]
str r2,[r1]
adds r0,#4
adds r1,#4
subs r6,#1
bne copy_words
adds r4,#8
subs r5,#1
bne next_tile
ldr r0, ={BASE+ARCHIVE}
ldr r1, ={id}
bl stock_getter
str r1,[sp,#4]
str r2,[sp,#8]
ldr r0, ={BASE+map_at}
str r0,[sp]
ldr r1, =0x0600C220
str r1,[sp,#12]
ldr r3,[sp,#32]
str r3,[sp,#28]
ldr r3, ={BASE+resume+1}
str r3,[sp,#32]
ldr r3, ={BASE+call+5}
mov lr,r3
'''
  if row['emulate_add_r1']:assembly+='adds r1,r0,#0\nstr r1,[sp,#4]\n'
  else:assembly+='adds r0,r0,#0\n'
  assembly+='pop {r0,r1,r2,r4,r5,r6,r7}\npop {r3,pc}\nstock_getter:\nldr r3, =0x08000859\nbx r3'
  # localBL trampoline may clobberr3 internally; originalr3 restored above.
  code=asm(assembly,BASE+stub)
  decoded=list(md.disasm(code,BASE+stub))
  # Code before literalpool has only16-bit nativeops or32-bit Thumb1BL.
  code_end=next(i.address+2-BASE-stub for i in decoded if i.mnemonic=='bx' and i.op_str=='r3')
  code_ins=list(md.disasm(code[:code_end],BASE+stub))
  if any(i.size==4 and i.mnemonic!='bl' for i in code_ins):raise ValueError('Thumb2 instruction in ARMv4T card stub')
  assert append(code)==stub
  rom[hook:hook+12]=asm('push {r3}\nldr r3,[pc,#4]\nbx r3\nmov r8,r8',BASE+hook)+struct.pack('<I',BASE+stub+1)
  row.update(original_hook_bytes=original.hex(),hook_bytes=12,map_pointer=BASE+map_at,scatter=scatter,scatter_table=table,stub=stub,stub_bytes=len(code),native_code_bytes=code_end,assembly=assembly,stub_SHA256=hashlib.sha256(code).hexdigest())
 allowed=[(row['hook'],12) for row in profiles]+[(start,cursor-start)]
 assert all(any(lo<=i<lo+n for lo,n in allowed) for i,(a,b) in enumerate(zip(baseline,rom)) if a!=b)
 assert rom[0x858:0x86A]==baseline[0x858:0x86A]
 meta={'schema':'gba-v19-resident-card-per-state-native16','status':'experimental-not-frozen','source_sha256':SOURCE_SHA,'baseline_sha256':expected_baseline_sha,'rom_sha256':hashlib.sha256(rom).hexdigest(),'append_start':start,'append_end':cursor,'card_profiles':profiles,'source_archive_directory_unchanged_relative_v18':True,'v17_getter_gateway_unchanged':True,'no_global_getter_rewrite':True,'all_card_tiles_below_native_counter_scratch':True,'scope':'3exact cardgetter consumers. Per-state scatter8wordtile copies into sourceexclusive/v17unused slots, paired3raw14x9maps. All3cards single active native112x72panel; joint fullatlas capacityfails preserved, not smallerfont. Sourcefirst256/counter5800+ andregion6000+ never overwritten. Naturalunlock/context/fullgame not yet proven.'}
 return bytes(rom),meta,outputs

if __name__=='__main__':
 v18=json.loads((ROOT/'work/gba-v18-resident-obj-candidate03/experiment.json').read_text('utf8'));v17=json.loads((ROOT/'work/gba-v17-town-resident-candidate09/experiment.json').read_text('utf8'))
 rom,meta,outputs=extend((ROOT/'build/resident-font-experimental-v18/slime-cn.gba').read_bytes(),v18['append_end'],v17)
 out=ROOT/'work/gba-v19-resident-card-candidate01';out.mkdir(exist_ok=False);(out/'slime-cn.gba').write_bytes(rom);(out/'experiment.json').write_text(json.dumps(meta,ensure_ascii=False,indent=2)+'\n','utf8')
 from graphics_backgrounds import render_map
 get,_=resources(SOURCE_PATH.read_bytes());pal=b'\0\0'+get(0x1c7)[2]
 for id,v in outputs.items():
  (out/f'atlas-{id:03X}.bin').write_bytes(v['tiles']);(out/f'map-{id:03X}.bin').write_bytes(v['map']);render_map(v['tiles'],v['map'],pal,14).resize((448,288),Image.Resampling.NEAREST).save(out/f'card-{id:03X}-4x.png')
 print(meta['rom_sha256'],[(hex(r['ID']),len(r['allocated_tile_IDs'])) for r in meta['card_profiles']])
