"""Rescue result BGs: original loader-specific archive, untouched dynamic counters."""
from gba_main_menu_graphics import resources
from gba_graphic_labels_v22 import translate,private_extend
TILES_ID=0x169
MAP_IDS=(0x16D,0x16E,0x170,0x171)
def assets(source):
 get,_=resources(source);tiles=get(TILES_ID)[2];assert len(tiles)==32768
 maps={i:get(i)[2] for i in (*MAP_IDS,0x172)};labels={}
 for mid,ja,cn in [(0x16D,'たすけた スライム','救出的史莱姆'),(0x170,'はこんだ まもの','搬回的怪物'),(0x171,'はこんだ しざい','搬回的物资')]:
  labels[mid]=[{'ja':ja,'cn':cn,'rect':[32,40,168,64] if mid==0x16D else [32,40,168,56],'xy':[33,45] if mid==0x16D else [33,38],'px':12,'ink':2,'bg':1,'bank':1}]
  # StockAB..KL digit rectangles are left byte-identical; Japanese unit only.
  if mid==0x16D:positions=[(72,64,'只')]
  else:positions=[(x,y,'只' if mid==0x170 else '个') for y in [56,72] for x in [72,136,200]]
  for x,y,cn in positions:
   labels[mid].append({'ja':'ひき' if mid!=0x171 else 'こ','cn':cn,'rect':[x,y,x+16,y+16],'xy':[x+2,y-2],'px':12,'ink':2,'bg':1,'bank':1})
 labels[0x16E]=[{'ja':'ひき','cn':'只','rect':[64,128,88,152],'xy':[66,132],'px':12,'ink':2,'bg':0,'bank':1}, {'ja':'ひき','cn':'只','rect':[208,128,232,152],'xy':[210,132],'px':12,'ink':2,'bg':0,'bank':1}]
 extras=[get(i)[2] for i in range(0x173,0x187)]
 # 16F is raw alternate tileset (not a 64-row BG); never treat it as a map.
 # 3E0..3F7 are stock two-digit dynamic overlays from IDs174..180.
 nt,nm,meta,images=translate(tiles,maps,labels,reserved=range(0x3E0,0x400),extra_maps=extras,palette=b"\0\0"+get(0x16b)[2])
 return nt,nm,meta,images
def extend(source,baseline,append_end):
 tiles,maps,meta,_=assets(source)
 rom,private=private_extend(source,baseline,append_end,{TILES_ID:(tiles,True),**{i:(m,True) for i,m in maps.items() if i in MAP_IDS}},[0xBBA14],[(0xBB95C,0x78)])
 meta.update(private);meta.update(schema='gba-rescue-result-graphics-v22',status='candidate',palette_unchanged=True,dynamic_numeric_overlays_preserved=True)
 return rom,meta
