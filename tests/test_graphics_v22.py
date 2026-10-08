"""ROM-free glyph, palette/layer and source-gate regression checks."""
import unittest,sys,struct
from pathlib import Path
from PIL import Image
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'tools'),str(ROOT/'upstream/Translimeation/tools'),str(ROOT/'upstream/Translimeation/agent-tools')]
from gba_title_graphics_v22 import part,pack_image,glyph
from gba_graphic_labels_v22 import font,translate,draw_label,private_extend
class GraphicContracts(unittest.TestCase):
 def test_title_native_integer_scale(self):
  for ch in '史莱姆':
   im,proof=glyph(ch,font(12),12,'blue')
   self.assertEqual(im.size,(32,32));self.assertEqual(proof['integer_artwork_scale'],2);self.assertGreater(proof['ink_pixels'],100)
 def test_native_units_not_scaled(self):
  for ch in '只个枚胜':
   im,proof=glyph(ch,font(12),12,'green');self.assertEqual(proof['integer_artwork_scale'],1);self.assertEqual(im.size,(16,16))
 def test_pack_roundtrip(self):
  im=Image.new('P',(16,16))
  for y in range(16):
   for x in range(16):im.putpixel((x,y),(x+y)%16)
  raw=pack_image(im);self.assertEqual(len(raw),128)
  for y in range(16):
   for x in range(16):
    t=y//8*2+x//8;v=raw[t*32+y%8*4+x%8//2]>>(x%2*4)&15;self.assertEqual(v,(x+y)%16)
 def test_part_valid_dimensions(self):
  a,b,c=part(-30,-40,32,16,150,2);self.assertEqual(a>>14,1);self.assertEqual(b>>14,2);self.assertEqual(c,0x2096)
 def test_part_invalid_dimensions(self):
  with self.assertRaises(AssertionError):part(0,0,12,16,0,0)
 def test_wrong_source_rejected(self):
  with self.assertRaises(ValueError):private_extend(bytes(16),bytes(16),0,{},[])
 def test_label_bounds_enforced(self):
  with self.assertRaises(ValueError):draw_label(Image.new('L',(64,32)),{'cn':'中文','rect':[0,0,8,16],'xy':[0,0],'px':12,'ink':1})
 def test_palette_native_color_remapping(self):
  # Entire source screen uses native green=1 in bank0, but the new font's
  # bank1 green=3. Half-tile rectangle forces preservation of boundary pixels.
  tiles=bytes(32)+bytes([0x11])*32+bytes(32768-64);mp=struct.pack('<1024H',*([1]*1024));words=[0]*256
  words[1]=0x03e0;words[2]=0x7fff;words[16+3]=0x03e0;words[16+4]=0x7fff
  rawpal=struct.pack('<256H',*words)
  nt,nm,meta,_=translate(tiles,{0:mp},{0:[{'cn':'是','rect':[3,2,28,24],'xy':[6,4],'px':12,'bg':3,'ink':4,'bank':1}]},palette=rawpal)
  self.assertTrue(meta['RGBA_nontext_proof']);self.assertEqual(nt[:32],tiles[:32]);self.assertNotEqual(mp,nm[0])
if __name__=='__main__':unittest.main()
