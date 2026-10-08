"""Minimal BPS1, SourceRead/TargetRead only, strict CRC/source/output gates.
No overwrite. Deliberately refuses unsupported SourceCopy/TargetCopy opcodes.
"""
from pathlib import Path
import struct,zlib,hashlib
class PatchError(ValueError):pass

def number(n):
 if type(n)is not int or n<0:raise PatchError('Invalid BPS integer')
 out=bytearray()
 while True:
  v=n&127;n>>=7
  if n==0:out.append(v|128);return bytes(out)
  out.append(v);n-=1

def read_number(data,pos,end):
 value=0;shift=1
 for _ in range(10):
  if pos>=end:raise PatchError('Truncated BPS integer')
  b=data[pos];pos+=1;value+=(b&127)*shift
  if b&128:return value,pos
  shift<<=7;value+=shift
 raise PatchError('Oversized BPS integer')

def crc(data):return zlib.crc32(data)&0xffffffff

def make(source,target,metadata=b''):
 body=bytearray(b'BPS1'+number(len(source))+number(len(target))+number(len(metadata))+metadata);pos=0
 while pos<len(target):
  start=pos;same=pos<len(source) and source[pos]==target[pos]
  while pos<len(target) and (pos<len(source) and source[pos]==target[pos])==same:pos+=1
  body+=number(((pos-start-1)<<2)|(0 if same else 1))
  if not same:body+=target[start:pos]
 body+=struct.pack('<II',crc(source),crc(target));body+=struct.pack('<I',crc(body))
 return bytes(body)

def apply(source,patch,max_output=128*1024*1024):
 if len(patch)<19 or patch[:4]!=b'BPS1':raise PatchError('Invalid BPS1 header')
 if crc(patch[:-4])!=struct.unpack_from('<I',patch,len(patch)-4)[0]:raise PatchError('Patch CRC mismatch')
 end=len(patch)-12;pos=4;size,pos=read_number(patch,pos,end);target_size,pos=read_number(patch,pos,end);meta,pos=read_number(patch,pos,end)
 if size!=len(source) or crc(source)!=struct.unpack_from('<I',patch,end)[0]:raise PatchError('Wrong source ROM')
 if target_size>max_output or pos+meta>end:raise PatchError('Invalid BPS budget')
 pos+=meta;out=bytearray()
 while len(out)<target_size:
  action,pos=read_number(patch,pos,end);length=(action>>2)+1;kind=action&3;at=len(out)
  if at+length>target_size:raise PatchError('Action exceeds target')
  if kind==0:
   if at+length>len(source):raise PatchError('SourceRead out of bounds')
   out+=source[at:at+length]
  elif kind==1:
   if pos+length>end:raise PatchError('Truncated TargetRead')
   out+=patch[pos:pos+length];pos+=length
  else:raise PatchError('Unsupported copy opcode')
 if pos!=end or crc(out)!=struct.unpack_from('<I',patch,end+4)[0]:raise PatchError('Target length/CRC mismatch')
 return bytes(out)

def apply_file(source_path,patch_path,out_path):
 source_path=Path(source_path).resolve();patch_path=Path(patch_path).resolve();out_path=Path(out_path).resolve()
 if out_path.exists() or out_path in [source_path,patch_path]:raise PatchError('Refuse overwrite or alias')
 source=source_path.read_bytes();patch=patch_path.read_bytes();target=apply(source,patch)
 out_path.parent.mkdir(exist_ok=True,parents=True);out_path.write_bytes(target);return hashlib.sha256(target).hexdigest()
if __name__=='__main__':
 import argparse
 ap=argparse.ArgumentParser();ap.add_argument('source',type=Path);ap.add_argument('patch',type=Path);ap.add_argument('out',type=Path);a=ap.parse_args();print(apply_file(a.source,a.patch,a.out))