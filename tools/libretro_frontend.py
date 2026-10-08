"""Minimal libretro frontend for mGBA natural-route and controlled-fixture tests.
Core HLE BIOS is used; no Nintendo BIOS or user's global emulator state is read.
"""
import ctypes as C,sys,hashlib,json,time,argparse
from pathlib import Path
import numpy as np
from PIL import Image
ROOT=Path(__file__).resolve().parents[1]
ENV=C.CFUNCTYPE(C.c_bool,C.c_uint,C.c_void_p)
VIDEO=C.CFUNCTYPE(None,C.c_void_p,C.c_uint,C.c_uint,C.c_size_t)
AUDIO=C.CFUNCTYPE(None,C.c_int16,C.c_int16)
BATCH=C.CFUNCTYPE(C.c_size_t,C.POINTER(C.c_int16),C.c_size_t)
POLL=C.CFUNCTYPE(None)
STATE=C.CFUNCTYPE(C.c_int16,C.c_uint,C.c_uint,C.c_uint,C.c_uint)
class Var(C.Structure):_fields_=[('key',C.c_char_p),('value',C.c_char_p)]
class Info(C.Structure):_fields_=[('name',C.c_char_p),('version',C.c_char_p),('extensions',C.c_char_p),('fullpath',C.c_bool),('block',C.c_bool)]
class Game(C.Structure):_fields_=[('path',C.c_char_p),('data',C.c_void_p),('size',C.c_size_t),('meta',C.c_char_p)]
class MemDesc(C.Structure):_fields_=[('flags',C.c_uint64),('ptr',C.c_void_p),('offset',C.c_size_t),('start',C.c_size_t),('select',C.c_size_t),('disconnect',C.c_size_t),('length',C.c_size_t),('addrspace',C.c_char_p)]
class MemMap(C.Structure):_fields_=[('descriptors',C.POINTER(MemDesc)),('count',C.c_uint)]
BUTTONS={'b':0,'select':2,'start':3,'up':4,'down':5,'left':6,'right':7,'a':8,'l':10,'r':11}
class Core:
 def __init__(self,rom,core_path,system_dir):
  self.path=Path(rom);self.data=self.path.read_bytes();self.buffer=C.create_string_buffer(self.data);self.format=2;self.frame=None;self.inputs=set();self.maps=[]
  self.core_path=Path(core_path);self.system=str(Path(system_dir).resolve()).encode('utf-8');Path(self.system.decode()).mkdir(parents=True,exist_ok=True)
  self.option_values={'mgba_use_bios':b'OFF','mgba_skip_bios':b'ON','mgba_frameskip':b'0','mgba_idle_optimization':b'Remove Known','mgba_allow_opposing_directions':b'no','mgba_force_gbp':b'OFF','mgba_color_correction':b'OFF','mgba_interframe_blending':b'OFF'}
  self.lib=C.CDLL(str(self.core_path))
  self.env=ENV(self.environment);self.video=VIDEO(self.on_video);self.audio=AUDIO(lambda *a:None);self.batch=BATCH(lambda d,n:n);self.poll=POLL(lambda:None);self.input=STATE(lambda p,d,i,k:1 if k in self.inputs else 0)
  for name,fn in [('environment',self.env),('video_refresh',self.video),('audio_sample',self.audio),('audio_sample_batch',self.batch),('input_poll',self.poll),('input_state',self.input)]:
   f=getattr(self.lib,'retro_set_'+name);f.argtypes=[type(fn)];f(fn)
  self.lib.retro_init();self.lib.retro_get_system_info.argtypes=[C.POINTER(Info)];info=Info();self.lib.retro_get_system_info(C.byref(info));self.info={'name':info.name.decode(),'version':info.version.decode(),'core_sha256':hashlib.sha256(self.core_path.read_bytes()).hexdigest()}
  self.lib.retro_load_game.argtypes=[C.POINTER(Game)];self.lib.retro_load_game.restype=C.c_bool
  self.game=Game(str(self.path).encode(),C.cast(self.buffer,C.c_void_p),len(self.data),None)
  if not self.lib.retro_load_game(C.byref(self.game)):raise RuntimeError('mGBA ROM load failed')
  self.lib.retro_get_memory_data.argtypes=[C.c_uint];self.lib.retro_get_memory_data.restype=C.c_void_p
  self.lib.retro_get_memory_size.argtypes=[C.c_uint];self.lib.retro_get_memory_size.restype=C.c_size_t
  self.lib.retro_serialize_size.restype=C.c_size_t;self.lib.retro_serialize.argtypes=[C.c_void_p,C.c_size_t];self.lib.retro_serialize.restype=C.c_bool
  self.lib.retro_unserialize.argtypes=[C.c_void_p,C.c_size_t];self.lib.retro_unserialize.restype=C.c_bool
 def environment(self,cmd,data):
  cmd=cmd&0xffff
  if cmd in (9,31):C.cast(data,C.POINTER(C.c_char_p))[0]=self.system;return True
  if cmd==10:self.format=C.cast(data,C.POINTER(C.c_int))[0];return self.format in (0,1,2)
  if cmd==15:
   v=C.cast(data,C.POINTER(Var)).contents;key=v.key.decode();value=self.option_values.get(key)
   if value:v.value=value;return True
   return False
  if cmd==17:C.cast(data,C.POINTER(C.c_bool))[0]=False;return True
  if cmd==36:
   m=C.cast(data,C.POINTER(MemMap)).contents
   self.maps=[(x.start,x.length,x.ptr,x.offset) for x in m.descriptors[:m.count] if x.ptr];return True
  if cmd==47:C.cast(data,C.POINTER(C.c_uint))[0]=3;return True
  if cmd==52:C.cast(data,C.POINTER(C.c_uint))[0]=0;return True
  if cmd in (6,8,11,16,18,34,35,37,44,53,54,55,58,67,68,69):return True
  return False
 def on_video(self,data,w,h,pitch):
  if not data or data==C.c_void_p(-1).value:return
  raw=C.string_at(data,pitch*h)
  if self.format==1:
   a=np.frombuffer(raw,np.uint8).reshape(h,pitch)[:,:w*4].reshape(h,w,4);rgb=a[:,:,[2,1,0]]
  else:
   a=np.frombuffer(raw,np.uint16).reshape(h,pitch//2)[:,:w]
   if self.format==2:r=((a>>11)&31)*255//31;g=((a>>5)&63)*255//63;b=(a&31)*255//31
   else:r=((a>>10)&31)*255//31;g=((a>>5)&31)*255//31;b=(a&31)*255//31
   rgb=np.stack((r,g,b),2).astype(np.uint8)
  self.frame=Image.fromarray(rgb)
 def run(self,keys=()):self.inputs={BUTTONS[k] for k in keys};self.lib.retro_run()
 def read(self,address,size=1):
  for start,length,ptr,offset in self.maps:
   if start<=address and address+size<=start+length:return C.string_at(ptr+offset+address-start,size)
  if 0x02000000<=address and address+size<=0x02040000:
   return C.string_at(self.lib.retro_get_memory_data(2)+address-0x02000000,size)
  raise ValueError('Unmapped address '+hex(address))
 def write(self,address,data):
  for start,length,ptr,offset in self.maps:
   if start<=address and address+len(data)<=start+length:C.memmove(ptr+offset+address-start,data,len(data));return
  if 0x02000000<=address and address+len(data)<=0x02040000:C.memmove(self.lib.retro_get_memory_data(2)+address-0x02000000,data,len(data));return
  raise ValueError('Unmapped address '+hex(address))
 def save(self):
  size=self.lib.retro_serialize_size();b=C.create_string_buffer(size)
  if not self.lib.retro_serialize(b,size):raise RuntimeError('serialize failed')
  return b.raw
 def load(self,data):
  b=C.create_string_buffer(data)
  if not self.lib.retro_unserialize(b,len(data)):raise RuntimeError('unserialize failed')
 def close(self):self.lib.retro_unload_game();self.lib.retro_deinit()

