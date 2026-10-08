#!/usr/bin/env python3
"""Strict local-source BPS application, independent of Flips' implementation.
This package supports only the exact user-provided A9KJ source fingerprint.
No source ROM is included. Refuses aliasing source/output and existing outputs.
"""
import argparse,hashlib,json,struct,zlib
from pathlib import Path
SOURCE_SHA='a4f8d475eb877bc370cead79876caf7418864b1497d237650ff738c3afdf27a2'
TARGET_SHA='fbf65f940f8800264cc5f9a15b3dd45980b11b4da389fa6acb44205e2f93a3ae'
PATCH_SHA='4c1174fcb35a396838302cacd66c9704f6af6d098a885c1c243d4200987de8db'

def apply(source,patch):
 if hashlib.sha256(patch).hexdigest()!=PATCH_SHA:raise ValueError('Wrong v22 patch SHA256')
 if hashlib.sha256(source).hexdigest()!=SOURCE_SHA:raise ValueError('Wrong source ROM SHA-256; use the specified unmodified A9KJ Japanese ROM')
 if len(patch)<19 or patch[:4]!=b'BPS1':raise ValueError('Invalid/truncated BPS')
 sc,tc,pc=struct.unpack_from('<III',patch,len(patch)-12)
 if zlib.crc32(patch[:-4])!=pc:raise ValueError('Patch CRC32 mismatch')
 if zlib.crc32(source)!=sc:raise ValueError('Source CRC32 mismatch')
 pos=4;limit=len(patch)-12
 def number():
  nonlocal pos
  data=0;shift=1
  for _ in range(10):
   if pos>=limit:raise ValueError('Truncated integer')
   x=patch[pos];pos+=1;data+=(x&127)*shift
   if x&128:return data
   shift<<=7;data+=shift
  raise ValueError('Oversized BPS integer')
 source_size=number();target_size=number();meta=number()
 if source_size!=len(source) or target_size!=16777216:raise ValueError('Unexpected BPS source/target sizes')
 if pos+meta>limit:raise ValueError('Truncated metadata')
 pos+=meta;out=bytearray();sr=0;tr=0
 while pos<limit:
  instruction=number();mode=instruction&3;length=(instruction>>2)+1
  if len(out)+length>target_size:raise ValueError('Target size overflow')
  if mode==0:
   a=len(out)
   if a+length>len(source):raise ValueError('SourceRead out of bounds')
   out+=source[a:a+length]
  elif mode==1:
   if pos+length>limit:raise ValueError('Truncated TargetRead')
   out+=patch[pos:pos+length];pos+=length
  else:
   delta=number();step=-(delta>>1) if delta&1 else delta>>1
   if mode==2:
    sr+=step
    if sr<0 or sr+length>len(source):raise ValueError('SourceCopy out of bounds')
    out+=source[sr:sr+length];sr+=length
   else:
    tr+=step
    if tr<0 or tr>=len(out):raise ValueError('TargetCopy out of bounds')
    for _ in range(length):
     if tr>=len(out):raise ValueError('Invalid overlapping TargetCopy')
     out.append(out[tr]);tr+=1
 if len(out)!=target_size:raise ValueError('Incomplete target')
 if zlib.crc32(out)!=tc:raise ValueError('Target CRC32 mismatch')
 if hashlib.sha256(out).hexdigest()!=TARGET_SHA:raise ValueError('Target SHA256 mismatch')
 return bytes(out)

def main():
 a=argparse.ArgumentParser(description=__doc__);a.add_argument('source',type=Path);a.add_argument('patch',type=Path);a.add_argument('output',type=Path);args=a.parse_args()
 if args.source.resolve()==args.output.resolve() or args.patch.resolve()==args.output.resolve():a.error('Output must not alias source or patch')
 if args.output.exists():a.error('Output already exists; choose a new path')
 target=apply(args.source.read_bytes(),args.patch.read_bytes())
 with args.output.open('xb') as f:f.write(target)
 print('Applied and verified:',args.output.resolve());print('SHA256:',hashlib.sha256(target).hexdigest())
if __name__=='__main__':main()
