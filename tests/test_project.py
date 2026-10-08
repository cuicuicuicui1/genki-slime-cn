"""ROM-free regression contracts. A commercial ROM is never a CI fixture."""
import hashlib,json,os,random,struct,subprocess,sys,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'tools'),str(ROOT/'upstream/Translimeation/tools'),str(ROOT/'upstream/Translimeation/agent-tools')]
from bps_patch import make,apply,number,read_number,PatchError,crc,apply_file
from cn_codec import CNCodec,same_controls,FIRST,COMPACT,translated_chars
from build_cn import normalize_name_mentions,source_entities
from gba_graphics_engine import literal
from slime_gfx import Decompressor
from cn_engine import load_bdf,bitmap

def data(n):return json.loads((ROOT/'data'/n).read_text('utf-8'))
class PatchContracts(unittest.TestCase):
 def test_varint_boundaries(self):
  for n in [0,1,127,128,129,16383,16384,10**9]:self.assertEqual(read_number(number(n),0,len(number(n))),(n,len(number(n))))
 def test_varint_negative(self):
  with self.assertRaises(PatchError):number(-1)
 def test_varint_truncated(self):
  with self.assertRaises(PatchError):read_number(b'\0',0,1)
 def test_varint_budget(self):
  with self.assertRaises(PatchError):read_number(b'\0'*11,0,11)
 def test_identical(self):self.assertEqual(apply(b'abc',make(b'abc',b'abc')),b'abc')
 def test_mixed_actions(self):self.assertEqual(apply(b'abcdef',make(b'abcdef',b'abXYefhello')),b'abXYefhello')
 def test_metadata(self):self.assertEqual(apply(b'a',make(b'a',b'ab',b'test')),b'ab')
 def test_many_small_inputs(self):
  r=random.Random(42)
  for n in range(20):
   a=r.randbytes(n);b=r.randbytes(n+4);self.assertEqual(apply(a,make(a,b)),b)
 def test_corrupt_patch(self):
  p=bytearray(make(b'abc',b'def'));p[5]^=1
  with self.assertRaises(PatchError):apply(b'abc',p)
 def test_wrong_source(self):
  with self.assertRaises(PatchError):apply(b'axc',make(b'abc',b'def'))
 def test_short_patch(self):
  with self.assertRaises(PatchError):apply(b'',b'BPS1')
 def test_output_budget(self):
  with self.assertRaises(PatchError):apply(b'',make(b'',b'123456'),max_output=4)
 def test_no_overwrite(self):
  with tempfile.TemporaryDirectory() as d:
   d=Path(d);(d/'src').write_bytes(b'abc');(d/'p').write_bytes(make(b'abc',b'abcd'));(d/'out').write_bytes(b'keep')
   with self.assertRaises(PatchError):apply_file(d/'src',d/'p',d/'out')
   self.assertEqual((d/'out').read_bytes(),b'keep')
class TextContracts(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.codec=CNCodec(data('gba-font-ids.json'))
 def test_registry_contiguous(self):self.assertEqual(sorted(data('gba-font-ids.json').values()),list(range(FIRST,FIRST+1878)))
 def test_new_ids_append(self):
  old=data('gba-font-ids.json');c=CNCodec(set(old)|{'龘'});self.assertTrue(all(c.ids[ch]==v for ch,v in old.items()));self.assertEqual(c.ids['龘'],FIRST+len(old))
 def test_roundtrip_dialogue(self):
  t=['中文',['NEWLINE'],['NAME','史拉林'],['COLOR',1],['PLAYER-NAME'],['COLOR',0]];b=self.codec.encode(t,'dialogue');self.assertEqual(self.codec.decode(b,0,'dialogue'),(t,len(b)))
 def test_roundtrip_compact_plain(self):
  t=['是',['ALIGN'],'否'];b=self.codec.encode(t,'plain',compact=True);self.assertEqual(self.codec.decode(b,0,'plain'),(t,len(b)))
 def test_roundtrip_small(self):
  t=['史拉林'];b=self.codec.encode(t,'small');self.assertEqual(self.codec.decode(b,0,'small'),(t,len(b)))
 def test_primary_compact_distinct(self):self.assertLess(max(self.codec.ids.values()),COMPACT)
 def test_controls_parameters(self):self.assertFalse(same_controls(['a',['COLOR',1]],['中',['COLOR',2]]))
 def test_controls_order(self):self.assertFalse(same_controls(['a',['NEWLINE'],['SHOW-PROMPT']],['中',['SHOW-PROMPT'],['NEWLINE']]))
 def test_name_translatable(self):self.assertTrue(same_controls([['NAME','スラーリン'],'abc'],[['NAME','史拉林'],'中文']))
 def test_registry_authoring_counts(self):
  a=data('review-overrides.json');b=data('auxiliary-translations.json');self.assertEqual((len(a),len(b)),(2426,113));self.assertEqual(len({x['id'] for x in a+b}),2539)
 def test_ordinal_source_guards(self):
  c=data('canonical-names.json');rules=data('gba-name-body-rules.json')['rules'];v={'スラーリン':{'史拉林','史拉林八世','史拉林八世八世'}}
  for t in ['史拉林８世','史拉林八世８世','史拉林八世八世８世','史拉林八世']:
   self.assertEqual(normalize_name_mentions('スラーリン８世',t,c,v,rules),'史拉林八世')
  self.assertEqual(normalize_name_mentions('名前なし','史拉林８世',c,v,rules),'史拉林８世')
 def test_nonrecursive_name(self):self.assertEqual(normalize_name_mentions('名前','短名',{'名前':'新長名'},{'名前':{'短名','新','新長名'}},[]),'新長名')
 def test_longest_source_entity(self):self.assertEqual(source_entities('スーラン',{'スーラ':'甲'},{'スーラン':'镇'}),(set(),{'スーラン'}))
 def test_authored_merge_order_stable(self):
  from build_cn import merge
  inventory=[{'id':r['id'],'tokens':r['tokens'],'format':'small' if r['id'].startswith('small-') else 'dialogue' if r['id'].startswith('dialogue-') else 'plain'} for r in data('review-overrides.json')+data('auxiliary-translations.json')]
  a,rejected=merge(inventory);b,rejected2=merge(list(reversed(inventory)));self.assertFalse(rejected);self.assertFalse(rejected2);self.assertEqual(a,b)
class GraphicsContracts(unittest.TestCase):
 def test_literal_decode_roundtrip(self):
  for n in [1,4,31,32,48,512]:
   b=bytes((i*7)%256 for i in range(n));s=literal(b);d,mode,end=Decompressor(s,0).decompress();self.assertEqual((d,mode,end),(b,4,len(s)))
 def test_native_font_sizes(self):
  for size,family,file in [(12,'fusion12','fusion-pixel-12px-monospaced-zh_hans.bdf'),(8,'fusion8','fusion-pixel-8px-monospaced-zh_hans.bdf'),(16,'unifont16','unifont-16.0.03.bdf')]:
   b=load_bdf(ROOT/'assets/fonts'/family/file);im=bitmap('史',b,size);self.assertEqual(im.size,(size,16));self.assertTrue(any(im.get_flattened_data()))
 def test_title_census(self):
  p=ROOT/'research/title-parent-source-census.json';self.assertTrue(p.exists());self.assertGreater(p.stat().st_size,100)
class InputContracts(unittest.TestCase):
 def test_wrong_source_rejected_without_upstream_or_output(self):
  with tempfile.TemporaryDirectory() as d:
   d=Path(d);(d/'bad.gba').write_bytes(b'not a ROM');p=subprocess.run([sys.executable,'-X','utf8',str(ROOT/'tools/project.py'),'build','--rom',str(d/'bad.gba'),'--out',str(d/'out')],capture_output=True,text=True)
   self.assertNotEqual(p.returncode,0);self.assertIn('Wrong ROM',p.stderr);self.assertFalse((d/'out').exists())
if __name__=='__main__':unittest.main()
