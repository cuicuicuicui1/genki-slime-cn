"""Local CN extension: 0F A B, A/B in 10..FF, base-240 glyph index.
Never aliases an original glyph. Original dialogue NOP occurrences must be zero.
Original codecs stay unmodified; original player-name encoding remains supported.
"""
import json,struct,sys,re,unicodedata
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'upstream/Translimeation/tools'))
from text_codec import Codec,OPS,BY_NAME
BASE=0x08000000
FIRST=0x200
COMPACT=0x4000
SOURCE_SHA='a4f8d475eb877bc370cead79876caf7418864b1497d237650ff738c3afdf27a2'

class CNCodec:
 def __init__(self,chars):
  self.stock=Codec(ROOT/'upstream/Translimeation')
  profile=ROOT/'data/gba-font-profile.json'
  self.main_px=json.loads(profile.read_text('utf-8'))['main_px'] if profile.exists() else 12
  # Stable glyph IDs matter now that player names are persisted as u16 cells.
  registry_path=ROOT/'data/gba-font-ids.json'
  registry=json.loads(registry_path.read_text(encoding='utf-8')) if registry_path.exists() else {}
  ordered=sorted(registry,key=registry.get)
  if ordered and [registry[c] for c in ordered]!=list(range(FIRST,FIRST+len(ordered))):
   raise ValueError('Stable glyph registry is not contiguous')
  self.chars=ordered+sorted(set(chars)-set(ordered),key=ord)
  if len(self.chars)>0x10000-FIRST:raise ValueError('Too many glyphs')
  self.ids={c:FIRST+i for i,c in enumerate(self.chars)}
  self.by_id={v:k for k,v in self.ids.items()}
  if FIRST+len(self.chars)>COMPACT:raise ValueError('Primary/compact font namespaces overlap')
  self.by_id.update({COMPACT+i:c for i,c in enumerate(self.chars)})
  self.keys=sorted(set(self.stock.inverse)|set(self.ids),key=lambda x:(-len(x),x))
 def units(self,text,small=False):
  table=self.stock.small_inverse if small else self.stock.inverse
  cache='_small_multi' if small else '_big_multi'
  if not hasattr(self,cache):
   d={}
   for key in table:
    if len(key)>1:d.setdefault(key[0],[]).append(key)
   for ks in d.values():ks.sort(key=lambda x:(-len(x),x))
   setattr(self,cache,d)
  multis=getattr(self,cache);pos=0
  while pos<len(text):
   c=text[pos];key=next((x for x in multis.get(c,()) if text.startswith(x,pos)),None)
   if key is None:
    if c in self.ids or c in table:key=c
    else:raise ValueError('Unencodable '+repr(text[pos:]))
   yield key;pos+=len(key)
 def escape(self,code):
  a,b=divmod(code-FIRST,240)
  if not 0<=a<240:raise ValueError('Extension overflow')
  return bytes([15,a+16,b+16])
 def glyph(self,char,small=False,compact=False):
  if char in self.ids:
   return self.escape(self.ids[char]+(COMPACT-FIRST if compact and not small else 0))
  table=self.stock.small_inverse if small else self.stock.inverse
  code=table[char]
  if small and code>=256:raise ValueError('Unsupported stock small code')
  return bytes([code]) if code<256 else bytes([1,code-256])
 def text(self,text,small=False,compact=False):return b''.join(self.glyph(c,small,compact) for c in self.units(text,small))
 def encode(self,tokens,kind='dialogue',compact=False):
  out=bytearray()
  if kind=='small':
   if any(not isinstance(t,str) for t in tokens):raise ValueError('Small controls unsupported')
   return self.text(''.join(tokens),True)+b'\0'
  for t in tokens:
   if isinstance(t,str):out+=self.text(t,compact=compact)
   elif t[0]=='NAME':out+=b'\x05'+self.text(t[1],True)+b'\x05'
   elif t[0]=='GLYPH':
    code=t[1];out+=bytes([code]) if code<256 else bytes([1,code-256])
   elif t==['ALIGN'] and kind=='plain':out.append(2)
   elif t[0] in BY_NAME:
    op,args=BY_NAME[t[0]]
    if op==15:raise ValueError('NOP now reserved for CN glyphs')
    out.append(op)
    if args:out.append(t[1])
   else:raise ValueError('Unsupported token '+str(t))
  return bytes(out)+b'\0'
 def read_glyph(self,rom,pos,small=False):
  c=rom[pos];pos+=1
  if c==15:
   a,b=rom[pos:pos+2]
   if a<16 or b<16:raise ValueError('Invalid extension payload')
   return self.by_id[FIRST+(a-16)*240+b-16],pos+2
  if c==1 and not small:c=256+rom[pos];pos+=1
  return (self.stock.small if small else self.stock.big)[c],pos
 def decode(self,rom,pos,kind='dialogue'):
  result=[]
  def add(s):
   if result and isinstance(result[-1],str):result[-1]+=s
   else:result.append(s)
  while rom[pos]:
   c=rom[pos]
   if kind=='small' or c==15 or c==1 or c>=16:
    s,pos=self.read_glyph(rom,pos,kind=='small');add(s)
   elif c==5 and kind=='dialogue':
    pos+=1;name=''
    while rom[pos]!=5:s,pos=self.read_glyph(rom,pos,True);name+=s
    pos+=1;result.append(['NAME',name])
   elif c==2 and kind=='plain':result.append(['ALIGN']);pos+=1
   elif c in OPS:
    name,args=OPS[c];result.append([name]+([rom[pos+1]] if args else []));pos+=1+args
   else:raise ValueError('Bad stream')
  return result,pos+1
 def width(self,c,small=False,compact=False):
  if small:return 8
  if c in self.ids:return 12 if compact else self.main_px
  code=self.stock.inverse[c]
  return self.stock_width(code)
 def stock_width(self,code):
  for end,w in zip((0x13,0x18,0x23,0x3d,0x66,0x97,0xce,0x10c,0x141,0x1b8),range(4,14)):
   if code<=end:return w
  raise ValueError('Stock glyph out of range')

def translated_chars(rows):
 stock=Codec(ROOT/'upstream/Translimeation');chars=set()
 for row in rows:
  for t in row['tokens']:
   values=[t] if isinstance(t,str) else [t[1]] if t and t[0]=='NAME' else []
   for s in values:
    for c in s:
     if '\u4e00'<=c<='\u9fff' or c not in stock.inverse and c not in '<>':chars.add(c)
 return chars

def same_controls(old,new):
 if len(old)!=len(new):return False
 for a,b in zip(old,new):
  if isinstance(a,str):
   if not isinstance(b,str):return False
  elif a[0]=='NAME':
   if not isinstance(b,list) or len(b)!=2 or b[0]!='NAME' or not isinstance(b[1],str):return False
  elif a!=b:return False
 return True
