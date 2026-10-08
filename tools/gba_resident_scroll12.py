"""Extend isolated resident12 to the three source-bound redraw call sites.
The generic8px renderer/saved names remain unchanged for every other call.
A LR+string-pointer gate protects the native small reader at its prologue.
"""
import hashlib,json,struct
from cn_codec import ROOT,BASE
from cn_engine import asm,veneer

HOOK=0x96FE8
NATIVE_CONTINUE=0x08096FF1
CALLERS=(0xCB9FC,0xCBB2A,0xCBF7C)
PREP_STARTS=(0xCB9EC,0xCBB1A,0xCBF6C)
PROLOGUE=bytes.fromhex('f0b557464e464546')


def extend(rom_bytes,resident_meta,menu_meta,source):
    if hashlib.sha256(rom_bytes).hexdigest()!=menu_meta['rom_sha256']:
        raise ValueError('Wrong prior isolated menu candidate')
    if rom_bytes[HOOK:HOOK+8]!=PROLOGUE or source[HOOK:HOOK+8]!=PROLOGUE:
        raise ValueError('Native small prologue fingerprint changed')
    for start,caller in zip(PREP_STARTS,CALLERS):
        if rom_bytes[start:caller+4]!=source[start:caller+4]:
            raise ValueError('Resident redraw caller changed')
    cursor=(menu_meta['append_end']+3)&~3;start=cursor
    rom=bytearray(rom_bytes)
    def append(data):
        nonlocal cursor
        cursor=(cursor+3)&~3;at=cursor
        if at+len(data)>len(rom) or any(v!=255 for v in rom[at:at+len(data)]):
            raise ValueError('Occupied or overflowing candidate tail')
        rom[at:at+len(data)]=data;cursor+=len(data);return at
    # Original prologue must run once, with its original SP and registers,
    # before the untouched native reader/Chinese small-hook continues.
    fallback=(cursor+3)&~3
    assert append(PROLOGUE+asm(f'ldr r3, ={NATIVE_CONTINUE}\nbx r3',BASE+fallback+8))==fallback
    stub=(cursor+3)&~3
    returns=[BASE+call+5 for call in CALLERS]
    assembly=f'''push {{r0,r1,r2,r4,r5,r6,r7,lr}}
mov r4,lr
ldr r3, ={returns[0]}
cmp r4,r3
beq qualified
ldr r3, ={returns[1]}
cmp r4,r3
beq qualified
ldr r3, ={returns[2]}
cmp r4,r3
bne fallback
qualified:
cmp r2,#0
bne fallback
ldr r5, ={BASE+resident_meta['table']}
movs r6,#100
lookup:
ldr r3,[r5]
cmp r3,r1
beq found
adds r5,#8
subs r6,#1
bne lookup
fallback:
pop {{r0,r1,r2,r4,r5,r6,r7}}
pop {{r3}}
mov lr,r3
ldr r3, ={BASE+fallback+1}
bx r3
found:
ldr r1,[r5,#4]
movs r2,#128
copy:
ldr r3,[r1]
str r3,[r0]
adds r1,#4
adds r0,#4
subs r2,#1
bne copy
pop {{r0,r1,r2,r4,r5,r6,r7}}
pop {{r3}}
mov lr,r3
movs r0,#16
bx r3'''
    code=asm(assembly,BASE+stub);assert append(code)==stub
    rom[HOOK:HOOK+8]=veneer(BASE+stub,reg=3)
    changed=[i for i,(a,b) in enumerate(zip(rom_bytes,rom)) if a!=b]
    assert all(HOOK<=i<HOOK+8 or start<=i<cursor for i in changed)
    meta={'schema':'gba-v16-resident12-redraw-gate','status':'experimental-not-frozen',
        'prior_sha256':menu_meta['rom_sha256'],'rom_sha256':hashlib.sha256(rom).hexdigest(),
        'hook':HOOK,'original_prologue':PROLOGUE.hex(),'stub':stub,'stub_bytes':len(code),
        'assembly':assembly,'fallback_prologue':fallback,'stock_continue':NATIVE_CONTINUE,
        'allowed_source_callers':list(CALLERS),'allowed_LR':returns,
        'caller_fingerprints':[{'offset':s,'bytes':source[s:c+4].hex(),'sha256':hashlib.sha256(source[s:c+4]).hexdigest()} for s,c in zip(PREP_STARTS,CALLERS)],
        'resident_table':resident_meta['table'],'resident_pointer_count':100,
        'returned_tiles':16,'destination_bytes':512,'appended_start':start,'append_end':cursor,
        'changed_bytes':len(changed),'scope':'Exact three native list redraw return addresses AND 100 known resident pointers AND style0 only. Every other small/saved-name use replays original prologue then follows unchanged native+Chinese8 reader. Not naturally rescued/unlocked/all-game evidence.'}
    return bytes(rom),meta


def main():
    from gba_main_menu_graphics import SOURCE_PATH
    previous=ROOT/'work/gba-v16-menu-graphics-candidate03'
    resident=json.loads((ROOT/'work/gba-v16-resident12-candidate/experiment.json').read_text('utf8'))
    menu=json.loads((previous/'experiment.json').read_text('utf8'))
    rom,meta=extend((previous/'slime-cn.gba').read_bytes(),resident,menu,SOURCE_PATH.read_bytes())
    out=ROOT/'work/gba-v16-menu-graphics-candidate05';out.mkdir(exist_ok=False)
    (out/'slime-cn.gba').write_bytes(rom)
    (out/'redraw-experiment.json').write_text(json.dumps(meta,ensure_ascii=False,indent=2),'utf8')
    print('Native12 resident redraw candidate:',meta['rom_sha256'])
if __name__=='__main__':main()

