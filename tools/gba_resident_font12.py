"""Experimental resident-only 12px raster cache, preserving each 64x16 allocation.
Not enabled in build_cn; v15 remains the frozen authority until scene validation.
No saved-name ID or generic small-font reader change.
"""
import hashlib
import json
import struct
from pathlib import Path
from PIL import Image
from cn_codec import BASE, FIRST, CNCodec, ROOT
from cn_engine import asm, veneer
from gba_resident_layout import CONSUMER_START, CONSUMER_END, CONSUMER_SHA

HOOK = 0xCB678  # Word-aligned; original eight bytes are inside gated consumer.
RETURN = 0x080CB68B
STOCK_RENDER = 0x08096FE9
BASELINE_SHA = 'e182fbbf564eec2de72293080c00ca741c7b7fbf6d7b2cc2c7f1f8843c59d355'
BASELINE_MANIFEST_CANONICAL_SHA = 'f328570dff63dba3dcd413544d680c6fc643ba67c12794202bc328e01718d129'
BASELINE_REGISTRY_CANONICAL_SHA = '57e277a626d67a03f29d9f2ceffe4acf9b468e90d50553865abc4d7664dd080b'


def decode_glyph_4bpp(data, width):
    """Independent native small/speaker bank decode: 8x16 blocks, row-major."""
    out = Image.new('P', (width, 16))
    for x in range(width):
        for y in range(16):
            pos = (x // 8) * 64 + y * 4 + (x % 8) // 2
            out.putpixel((x, y), (data[pos] >> (4 * (x & 1))) & 15)
    return out


def pack_tiles(image):
    """The native small renderer uses eight pairs of vertically stacked tiles."""
    out = bytearray()
    for block in range(8):
        for y in range(16):
            for x in range(0, 8, 2):
                out.append(image.getpixel((block*8+x,y)) | image.getpixel((block*8+x+1,y)) << 4)
    assert len(out) == 512
    return bytes(out)


def candidate(baseline_rom, manifest, ids, *, input_contract=None):
    expected=input_contract or {'rom':BASELINE_SHA,'manifest':BASELINE_MANIFEST_CANONICAL_SHA,'registry':BASELINE_REGISTRY_CANONICAL_SHA}
    if hashlib.sha256(baseline_rom).hexdigest()!=expected['rom']:raise ValueError('Input ROM contract mismatch')
    canonical_hash = lambda value: hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode('utf-8')).hexdigest()
    if canonical_hash(manifest) != expected['manifest']: raise ValueError('Stale or altered v15 manifest')
    if canonical_hash(ids) != expected['registry']: raise ValueError('Stale or altered stable v15 glyph IDs')
    assert hashlib.sha256(baseline_rom[CONSUMER_START:CONSUMER_END]).hexdigest() == CONSUMER_SHA
    assert HOOK % 4 == 0
    assert struct.unpack_from('<II', baseline_rom, 0xCB6D0) == (0x06008000, 0x087654E4)
    codec = CNCodec(ids)
    rom = bytearray(baseline_rom)
    cursor = 0x800000 + manifest['appended_used']
    start_cursor = cursor
    writes = []
    def append(data):
        nonlocal cursor
        cursor = (cursor + 3) & ~3
        offset = cursor
        assert cursor + len(data) <= len(rom)
        assert all(v == 255 for v in rom[cursor:cursor+len(data)]), 'Occupied append tail'
        rom[cursor:cursor+len(data)] = data
        cursor += len(data)
        return offset
    # Blank is intentionally stock/translucent, not an assumed opaque rectangle.
    blank_code = codec.stock.small_inverse['　']
    blank = decode_glyph_4bpp(baseline_rom[0x73CAE8+blank_code*64:0x73CAE8+(blank_code+1)*64], 8)
    rows = []
    untouched = []
    for record in manifest['records']:
        if not record['id'].startswith('small-'):
            continue
        text = record['tokens'][0].rstrip('　 ')
        units = list(codec.units(text, True))
        if not any(ch in ids for ch in units):
            untouched.append(record['id'])
            continue
        width = sum(12 if ch in ids else 8 for ch in units)
        if width > 64:
            raise ValueError('Resident name wider than preserved allocation: '+record['id'])
        image = Image.new('P', (64,16))
        for x in range(0,64,8): image.paste(blank, (x,0))
        x = 0
        for ch in units:
            if ch in ids:
                at = manifest['engine']['speaker_label']['bitmap'] + (ids[ch]-FIRST)*128
                glyph = decode_glyph_4bpp(baseline_rom[at:at+128],16).crop((0,0,12,16))
            else:
                code = codec.stock.small_inverse[ch]
                glyph = decode_glyph_4bpp(baseline_rom[0x73CAE8+code*64:0x73CAE8+(code+1)*64],8)
            image.paste(glyph,(x,0));x+=glyph.width
        raster=pack_tiles(image);at=append(raster)
        rows.append({'id':record['id'],'name':text,'string_pointer':BASE+record['offset'],'bitmap_pointer':BASE+at,'bitmap_offset':at,'bitmap_bytes':512,'native_width_pixels':width,'native_height_pixels':16,'semantic_text_not_truncated':True,'padding_matches_original_stock_blank':True,'bitmap_sha256':hashlib.sha256(raster).hexdigest()})
    assert len(rows)==100 and len(untouched)==2
    table=append(b''.join(struct.pack('<II',r['string_pointer'],r['bitmap_pointer']) for r in rows))
    stub=(cursor+3)&~3
    assembly=f'''push {{r4,r5,r6,lr}}
adds r0,r5,#1
lsls r0,r0,#5
ldr r1, =0x06008000
adds r0,r0,r1
ldr r1, =0x087654E4
adds r1,r2,r1
ldr r1,[r1]
movs r2,#0
mov r4,r0
mov r5,r1
ldr r6, ={BASE+table}
movs r3,#{len(rows)}
lookup:
ldr r2,[r6]
cmp r2,r5
beq found
adds r6,#8
subs r3,#1
bne lookup
mov r0,r4
mov r1,r5
movs r2,#0
bl call_stock
b finished
found:
ldr r1,[r6,#4]
mov r0,r4
movs r2,#128
copy:
ldr r3,[r1]
str r3,[r0]
adds r1,#4
adds r0,#4
subs r2,#1
bne copy
movs r0,#16
finished:
pop {{r4,r5,r6}}
pop {{r3}}
ldr r3, ={RETURN}
mov lr,r3
bx r3
call_stock:
ldr r3, ={STOCK_RENDER}
bx r3'''
    code=asm(assembly,BASE+stub);assert len(code)<256
    actual_stub=append(code);assert actual_stub==stub
    hook=veneer(BASE+stub);assert len(hook)==8
    rom[HOOK:HOOK+8]=hook
    writes.extend([{'offset':HOOK,'bytes':8,'purpose':'source-gated resident caller word-aligned veneer'},{'offset':start_cursor,'bytes':cursor-start_cursor,'purpose':'resident100 native12 raster cache, pointer table and ARMv4T stub'}])
    # Preserve every existing string, font bank, saved-name code and other hook.
    changed=[i for i,(a,b) in enumerate(zip(baseline_rom,rom)) if a!=b]
    assert all(HOOK<=i<HOOK+8 or start_cursor<=i<cursor for i in changed)
    metadata={'schema':'gba-v16-resident12-experiment','status':'candidate-not-frozen','baseline_sha256':expected['rom'],'rom_sha256':hashlib.sha256(rom).hexdigest(),'source_consumer_sha256':CONSUMER_SHA,'hook_offset':HOOK,'original_hook_bytes':baseline_rom[HOOK:HOOK+8].hex(),'hook_bytes':hook.hex(),'stub':stub,'stub_bytes':len(code),'stub_assembly':assembly,'return_address':RETURN,'table':table,'table_entries':len(rows),'resident12_resources':rows,'unchanged_stock_placeholder_resources':untouched,'maximum_name_width':max(r['native_width_pixels'] for r in rows),'original_destination_bytes_per_name':512,'native_returned_tiles':16,'font_registry_unchanged':True,'all_existing_8px_readers_and_saved_name_IDs_unchanged':True,'generic_small_renderer_096FE8_unchanged':True,'all_v15_encoded_text_resources_and_fontbank_bytes_unchanged':True,'writes':writes,'changed_bytes':len(changed),'natural_resident_scene_validation':'not_run','scope':'Experimental static native12 cache only for100 Chinese resident-list resource pointers at one exact source caller. Existing source unknown/blank rows fall back. Not naturally reached list, battery compatibility, allsmallfont enlargement or fullgame proof.'}
    return bytes(rom),metadata


def main():
    base=ROOT/'build/clear-font-preview-v15'
    rom,meta=candidate((base/'slime-cn.gba').read_bytes(),json.loads((base/'manifest.json').read_text('utf8')),json.loads((base/'font-map.json').read_text('utf8')))
    out=ROOT/'work/gba-v16-resident12-candidate';out.mkdir(exist_ok=False)
    (out/'slime-cn.gba').write_bytes(rom);(out/'experiment.json').write_text(json.dumps(meta,ensure_ascii=False,indent=2),'utf8');(out/'resident12.s').write_text(meta['stub_assembly'],'utf8')
    print('resident12 candidate100 names max60px, one consumer only, not frozen:',meta['rom_sha256'])

if __name__=='__main__':main()
