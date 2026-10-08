"""Remaining file copy/error/sleep command BGs; chains existing decode gateway."""
import struct
from cn_codec import BASE,SOURCE_SHA
from cn_engine import asm,veneer
from gba_file_labels import FILE_MAPS,BG_MAP,TASK_RAW_SPAN,_stream_spans
from gba_graphic_labels_v22 import translate,digest
from gba_graphics_engine import literal
from slime_gfx import Decompressor
NEW_MAPS=(0x756464,0x75651C,0x756890)
def assets(source,baseline,manifest):
 table=next(w['offset'] for w in manifest['write_regions'] if w['purpose']=='file-ui-decode-pairs')
 pairs=[];a=table
 while True:
  row=struct.unpack_from('<4I',baseline,a);a+=16
  if not row[0]:break
  pairs.append(row)
 assert len(pairs)==7
 direct=next(row for row in pairs if row[0]==BASE+0x751B90);tiles=Decompressor(baseline,direct[1]-BASE).decompress()[0];assert len(tiles)==32768
 # Source-family maps are enumerated; only the current paired-map lifetime
 # supplies allocation input below. Old map lifetimes upload separate atlases.
 maps={a:Decompressor(source,a).decompress()[0] for a in FILE_MAPS};maps[BG_MAP]=Decompressor(source,BG_MAP).decompress()[0]
 # Older warning maps upload their own complete atlases before use, so their
 # private font slot IDs are not live in this atlas. Preserve the source family
 # and all default-card helpers/dynamic banks instead.
 extras=[]
 used=set(range(256))|set(range(0x3B4,0x400));spans=_stream_spans(source,0x755344,0x756464)
 for at in range(0x755344,0x756464-1,2):
  if not any(a<=at<b for a,b in spans):used.add(struct.unpack_from('<H',baseline,at)[0]&1023)
 extras.append(baseline[TASK_RAW_SPAN[0]:TASK_RAW_SPAN[1]])
 common={'px':12,'ink':1,'bg':0,'outline':4,'bank':4}
 labels={0x756464:[{**common,'ja':'すでにきろくがあるので コピーできません！','cn':'这里已有冒险记录，','rect':[56,16,232,48],'xy':[56,13]},
 {'px':12,'ink':1,'bg':0,'outline':4,'bank':4,'clear':False,'ja':'コピーできません！','cn':'无法复制！','rect':[56,16,232,48],'xy':[56,29]}],
 0x75651C:[{**common,'ja':'ぼうけんのしょ1を コピーしますか？','cn':'要复制冒险记录1吗？','rect':[48,16,224,48],'xy':[56,21]}],
 0x756890:[{**common,'ja':'スリープモードの コマンドを オンにしますか？','cn':'启用睡眠模式快捷键吗？','rect':[40,8,224,48],'xy':[48,21]},
 {'px':12,'ink':1,'bg':6,'bank':4,'ja':'コマンド','cn':'快捷键','rect':[56,88,104,104],'xy':[62,86]},
 {'px':12,'ink':1,'bg':6,'bank':4,'ja':'（もどる時も）','cn':'唤醒也用','rect':[40,104,120,120],'xy':[56,102]}]}
 palette=bytes(128)+Decompressor(source,0x751AB0).decompress()[0]
 alltiles={};allmaps={};profiles={};images={}
 for a in NEW_MAPS:
  # Only current message and default BG are live: every file message selector
  # restores its own full atlas. Existing six paired gateways do so already;
  # the remaining empty message is explicitly restored in the outer gateway.
  nt,nm,meta,im=translate(tiles,{a:maps[a],BG_MAP:maps[BG_MAP]}, {a:labels[a]},reserved=used,extra_maps=extras,palette=palette,reclaim_unreferenced_nonempty=True)
  alltiles[a]=nt;allmaps[a]=nm[a];profiles[str(a)]=meta;images[a]=im[a]
 return alltiles,allmaps,{'paired_profiles':profiles,'lifecycle':'Every file message map selects a complete private/default atlas; stock raw helpers and numeric/name scratch preserved'},images

def extend(source,baseline,append_end,manifest):
 if digest(source)!=SOURCE_SHA:raise ValueError('Wrong source')
 for a,n in [(0xD6648,0x30),(0xD66AC,0x30),(0xD7590,0x28)]:
  if baseline[a:a+n]!=source[a:a+n]:raise ValueError('Extra file-message caller changed: '+hex(a))
 old=baseline[0x98AC8:0x98AD0]
 if old[:4]!=veneer(0,3)[:4]:raise ValueError('Existing file decoder gateway absent')
 oldptr=struct.unpack_from('<I',old,4)[0];oldstub=next(w for w in manifest['write_regions'] if w['purpose']=='file-ui-decode-gateway')
 if oldptr!=BASE+oldstub['offset']+1:raise ValueError('Existing gateway changed')
 tiles,maps,meta,_=assets(source,baseline,manifest);rom=bytearray(baseline);cursor=(append_end+3)&~3;start=cursor;writes=[]
 def append(data,tag):
  nonlocal cursor
  cursor=(cursor+3)&~3;a=cursor
  if a+len(data)>len(rom) or any(v!=255 for v in rom[a:a+len(data)]):raise ValueError('Occupied/overflow append')
  rom[a:a+len(data)]=data;cursor+=len(data);writes.append({'offset':a,'length':len(data),'purpose':tag});return a
 newpairs=[]
 for request,raw in maps.items():
  ta=append(literal(tiles[request]),'extra-file-private-atlas-'+hex(request));ma=append(literal(raw),'extra-file-map-'+hex(request));newpairs.append((BASE+request,BASE+ma,BASE+ta))
 # The stock empty green rectangle has no old paired atlas. Restore the default
 # record atlas before it, preventing previous message glyph slots from leaking.
 oldtable=next(w['offset'] for w in manifest['write_regions'] if w['purpose']=='file-ui-decode-pairs')
 direct=None
 for a in range(oldtable,oldtable+128,16):
  row=struct.unpack_from('<4I',baseline,a)
  if row[0]==BASE+0x751B90:direct=row[1]
 assert direct is not None
 newpairs.append((BASE+0x757788,BASE+0x757788,direct))
 table=append(b''.join(struct.pack('<3I',*row) for row in newpairs)+bytes(12),'extra-file-three-pairs-and-empty-restore');stub=(cursor+3)&~3
 code=asm(f"""push {{r0,r1,r2,r3,r4,r5,lr}}
ldr r4, ={BASE+table}
search:
ldr r5,[r4]
cmp r5,#0
beq stock
cmp r5,r0
beq paired
adds r4,#12
b search
paired:
ldr r0,[r4,#8]
ldr r1, =0x06000000
bl previous
ldr r0,[r4,#4]
ldr r1,[sp,#4]
bl previous
b done
stock:
ldr r0,[sp]
ldr r1,[sp,#4]
bl previous
done:
add sp,#16
pop {{r4,r5}}
pop {{r3}}
bx r3
previous:
ldr r3, ={oldptr}
bx r3
""",BASE+stub)
 assert append(code,'extra-file-local-BL-BX-chained-gateway')==stub
 rom[0x98AC8:0x98AD0]=veneer(BASE+stub,3);writes.append({'offset':0x98AC8,'length':8,'purpose':'chained-existing-file-decoder'})
 assert all(any(w['offset']<=i<w['offset']+w['length'] for w in writes) for i,(a,b) in enumerate(zip(baseline,rom)) if a!=b)
 meta.update(schema='gba-file-remaining-three-BGs-v22',status='candidate',source_sha256=SOURCE_SHA,baseline_sha256=digest(baseline),target_sha256=digest(rom),append_start=start,append_end=cursor,writes=writes,pairs=newpairs,old_gateway=oldptr,new_gateway=stub,old_gateway_not_overwritten=True,source_maps=list(NEW_MAPS))
 return bytes(rom),meta
