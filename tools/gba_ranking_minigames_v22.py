"""All three ranking cards and score unit overlays, exact shared source atlas."""
from gba_main_menu_graphics import resources
from gba_graphic_labels_v22 import translate,private_extend
TILES_ID=0x132
MAP_IDS=tuple(range(0x134,0x13B))
def assets(source):
 get,_=resources(source);tiles=get(TILES_ID)[2];assert len(tiles)==32768
 maps={i:get(i)[2] for i in MAP_IDS};labels={}
 # Same graphic style on A/C; on wooden B, retain the carved brown palette.
 for mid,bg in [(0x136,15),(0x13A,14)]:
  labels[mid]=[{'ja':'ランキング','cn':'排行榜','rect':[24,8,104,32],'xy':[37,9],'px':16,'bg':bg,'ink':10,'outline':1,'bank':4}]
  labels[mid].append({'ja':'とじる','cn':'关闭','rect':[184,136,224,152],'xy':[190,134],'px':12,'bg':4,'ink':1,'bank':11})
 labels[0x136].append({'ja':'なみのりホビートル','cn':'冲浪捞金币','rect':[110,16,226,33],'xy':[131,16],'px':12,'bg':15,'ink':12,'outline':4,'bank':4})
 labels[0x138]=[{'ja':'ランキング','cn':'排行榜','rect':[23,16,94,41],'xy':[34,19],'px':16,'bg':6,'ink':5,'outline':11,'bank':10},
  {'ja':'ドキドキつぼくらっしゅ','cn':'心动砸壶','rect':[112,21,226,37],'xy':[141,20],'px':12,'bg':7,'ink':9,'bank':7},
  {'ja':'とじる','cn':'关闭','rect':[192,136,224,152],'xy':[196,138],'px':12,'bg':6,'ink':5,'outline':11,'bank':10}]
 # Scrollable 64-row score columns: each of ten ranks has a Japanese unit.
 for mid,cn,ja in [(0x134,'枚','まい'),(0x137,'秒','びょう')]:
  labels[mid]=[]
  for y in range(112,272,16):
   labels[mid].append({'ja':ja,'cn':cn,'rect':[192 if mid==0x134 else 184,y,216,y+16],'xy':[196 if mid==0x134 else 190,y-2],'px':12,'bg':15,'ink':4,'bank':4})
 labels[0x135]=[{'ja':'しょきゅう','cn':'初级','rect':[40,48,80,64],'xy':[48,46],'px':12,'bg':0,'ink':1,'outline':2,'bank':4}]
 extras=[get(i)[2] for i in range(0x13B,0x169)]
 # Source miniature overlays include 3E0..3FF numeric scratch, no allocation there.
 nt,nm,meta,images=translate(tiles,maps,labels,reserved=range(0x3E0,0x400),extra_maps=extras,palette=b"\0\0"+get(0x133)[2])
 return nt,nm,meta,images
def extend(source,baseline,append_end):
 tiles,maps,meta,_=assets(source)
 rom,private=private_extend(source,baseline,append_end,{TILES_ID:(tiles,True),**{i:(m,True) for i,m in maps.items()}},[0xC2520],[(0xC2392,0x62),(0xC2560,0x28)])
 meta.update(private);meta.update(schema='gba-three-minigame-ranking-graphics-v22',status='candidate',palette_unchanged=True,dynamic_name_score_and_rank_digits_preserved=True)
 return rom,meta
