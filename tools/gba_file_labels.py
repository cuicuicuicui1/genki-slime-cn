"""GBA《元气史莱姆1》冒险之书菜单图片字补丁模块(v04)。

范围: 冒险之书(セーブ選択)菜单的
  (1) 顶部标题「ぼうけんのしょ」→「冒险之书」
  (2) 空存档记录提示「ぼうけんのきろくが　ありません。」→「暂无冒险记录。」

两项都在同一份共享 4bpp atlas(ROM 0x751B90, 解压 32768 字节 = 1024 图块)里,
由 file-menu 家族共用; 本模块只允许覆写经消费者枚举证明仅被目标本身引用的
图块, 其余图块(含其它屏幕依赖的 glyph/empty ID)一律保持原字节。

接口:
    file_label_engine(rom, append) -> (writes, metadata)
    writes: [(file_offset, bytes, tag), ...] 由父 build 写回目标 ROM。
    append(data, align=4) -> file_offset 由父提供(与 v03 一致)。

所有地址/容量/消费者都从真实源 ROM 现场验证, 不硬认提示里的地址。
ARMv4T: 只使用 Thumb 2 字节指令 + 局部 BL 跳板, 不使用 Thumb-2。
"""
from __future__ import annotations
import json
import struct
import sys
from pathlib import Path

from cn_codec import ROOT
sys.path.insert(0,str(ROOT/'upstream/Translimeation/tools'))

from slime_gfx import Decompressor  # noqa: E402
from cn_engine import load_bdf, bitmap, asm  # noqa: E402
from gba_graphics_engine import literal  # noqa: E402

BASE = 0x08000000
SOURCE_SHA = 'a4f8d475eb877bc370cead79876caf7418864b1497d237650ff738c3afdf27a2'

# 冒险之书菜单家族共享资源
ATLAS = 0x751B90          # 4bpp atlas 源(压缩流, 解压 32768)
PALETTE = 0x751AB0        # 该家族 palette 源(解压 384)
BG_MAP = 0x74FE54         # 棋盘背景 map 源(解压 2048)
TITLE_OVERLAY = 0x755344  # 顶部标题的 raw overlay(u16 表, 14x4)
TITLE_ENTRIES = 56        # 14 * 4
FILE_MAPS = (0x756464, 0x75651C, 0x7565BC, 0x756770, 0x756890,
             0x756A58, 0x756C58, 0x756E70, 0x757030, 0x757788)
# 任务点名的 raw table 范围(会动态覆盖菜单)
TASK_RAW_SPAN = (0x757174, 0x757788)
# 标题 overlay 载入代码(file-select 家族唯一引用 base 0x751AB0 的站点)
LOADER_BASE_SITE = 0x80D5EBC        # ldr r4,[pc] -> 0x751AB0
LOADER_TILES_ADD0 = 0x80D5EC6       # adds r0,r4,#0   (2 字节)
LOADER_TILES_ADD1 = 0x80D5EC8       # adds r0,#0xe0   (2 字节)
LOADER_TILES_DEST = 0x80D5ECA       # movs r1,#0xc0 / lsls r1,#0x13
LOADER_TILES_BL = 0x80D5ECE         # bl 0x8098ac8
EXPECT_LOADER_ADD = bytes.fromhex('201ce030')     # adds r0,r4,#0 ; adds r0,#0xe0
EXPECT_LOADER_DEST = bytes.fromhex('c021c904')    # movs r1,#0xc0 ; lsls r1,r1,#0x13
EXPECT_LOADER_BL = bytes.fromhex('c2f7fbfd')      # bl 0x8098ac8 (tiles upload)
TILES_SOURCE = 0x751B90             # loader 传给 native 解压器的 tiles 源(address)
TILES_DEST = 0x06000000             # 原 tiles 上传目标, 保持不变
NATIVE_DECODER = 0x98AC8            # 原 native 解压器入口(唯一 decode gateway)
NATIVE_DECODER_RESUME = 0x98AD0     # 重新实现被 veneer 覆盖的序言后回到这里
EXPECT_NATIVE_PROLOGUE = bytes.fromhex('f0b544464d465646')  # push{r4-r7,lr}; mov r4,r8; mov r5,sb; mov r6,sl

# 标题 glyph 调色(bank 8): 白字 + 深蓝投影
TITLE_BANK = 8
TITLE_INK = 12  # v05 native16 monochrome dark blue
TITLE_SHADOW = 12
# 原 kana 墨水/描边用的 shade(本区实测): 9/10/11/12; 招牌本体 = 0(透明)/1/2/13/14/15
TEXT_SHADES = (9, 10, 11, 12)


def _require(rom: bytes) -> None:
    import hashlib
    if len(rom) != 0x800000 or hashlib.sha256(rom).hexdigest() != SOURCE_SHA:
        raise ValueError('Wrong source ROM: exact local SHA256 required')


def _deep(models: dict, base: int) -> bytes:
    return Decompressor(models, base).decompress()[0]


def _stream_spans(rom: bytes, start: int, end: int) -> list:
    """本地解压扫描在该区间的真实压缩流跨度; 用于把 raw table 和压缩数据分开,
    避免把压缩字节误当 tile ID(假阳性)。"""
    spans = []
    off = start
    while off < end:
        header = struct.unpack_from('<I', rom, off)[0]
        if (header & 0xFF) == 0x70:
            try:
                out, mode, consumed = Decompressor(rom, off).decompress()
            except Exception:
                out = None
            if out is not None and consumed > off and consumed <= end and len(out) >= 64:
                spans.append((off, consumed))
                off = consumed
                continue
        off += 4
    return spans


def consumer_tiles(rom: bytes, exclude=()) -> set:
    """返回被 file-menu 家族已枚举消费者引用的 atlas 图块 ID 集合。

    消费者 = 10 张已解压 map + 背景 map + 0x755344..0x756464 内非压缩的 raw table
             + 任务点名 raw 范围 0x757174..0x757788。
    exclude: [(start,end)] 字节区间, 用于把"目标自身的表"排除, 使目标独占 ID 显现。
    """
    used = set()
    for base in FILE_MAPS:
        used |= {v & 1023 for (v,) in struct.iter_unpack('<H', _deep(rom, base))}
    used |= {v & 1023 for (v,) in struct.iter_unpack('<H', _deep(rom, BG_MAP))}

    def excluded(off):
        return any(a <= off < b for a, b in exclude)

    blob_start, blob_end = 0x755344, 0x756464
    streams = _stream_spans(rom, blob_start, blob_end)
    spans = []
    cur = blob_start
    for a, b in streams:
        if a > cur:
            spans.append((cur, a))
        cur = max(cur, b)
    if cur < blob_end:
        spans.append((cur, blob_end))
    spans.append(TASK_RAW_SPAN)
    for a, b in spans:
        for off in range(a, b - 1, 2):
            if excluded(off):
                continue
            used.add(struct.unpack_from('<H', rom, off)[0] & 1023)
    return used


def original_title(rom: bytes) -> list:
    return [v for (v,) in struct.iter_unpack('<H', rom[TITLE_OVERLAY:TITLE_OVERLAY + TITLE_ENTRIES * 2])]


def _title_grid(rom: bytes, atlas: bytes, entries: list):
    grid = [[0] * 112 for _ in range(32)]
    for k, entry in enumerate(entries):
        t = entry & 1023
        d = atlas[t * 32:t * 32 + 32]
        g = [[(d[y * 4 + x // 2] >> ((x & 1) * 4)) & 15 for x in range(8)] for y in range(8)]
        if entry & 1024:
            g = [r[::-1] for r in g]
        if entry & 2048:
            g = g[::-1]
        for y in range(8):
            for x in range(8):
                grid[(k // 14) * 8 + y][(k % 14) * 8 + x] = g[y][x]
    return grid


def build_cn_title(rom: bytes, atlas: bytes, font, label='冒险之书', advance=16, top=0, glyph_px=16):
    """生成 112x32 的 CN 标题索引图(shade 0-15, 调色 bank 8), 保留招牌剪影。

    做法: 用招牌本体(row2)的木质纹理重建被 kana 覆盖的上半部, 保留原始透明
    剪影(0), 然后写原生16px深蓝单色字。无投影、不缩放、不插值、不额外加粗。
    """
    entries = original_title(rom)
    orig = _title_grid(rom, atlas, entries)
    canvas = [row[:] for row in orig]
    for y in range(16):
        for x in range(112):
            if orig[y][x] != 0:                      # 保留透明剪影
                canvas[y][x] = orig[16 + (y % 8)][x]  # 招牌本体纹理

    width = advance * (len(label) - 1) + glyph_px
    x0 = (112 - width) // 2

    def put(x, y, v):
        if 0 <= x < 112 and 0 <= y < 32:
            canvas[y][x] = v

    for k, ch in enumerate(label):
        im = bitmap(ch, font, glyph_px)
        gx = x0 + k * advance
        for yy in range(16):
            for xx in range(glyph_px):
                if im.getpixel((xx, yy)):
                    put(gx + xx, top + yy, TITLE_INK)
    return orig, canvas


# 空存档记录提示: 地图 row3/row4 文本区的 raw u16 表(变体 A, 现网文件选择画面实测使用)
RECORD_BANK = 5
RECORD_INK = 15                # bank5 原色15 = 深褐(57,41,41); 亮绿底高对比，无调色板修改
RECORD_FILL_SHADE = 1          # bank5 索引1 = 亮绿(实心填充, 对应图块 24)
RECORD_WIDTH = 21              # row4 文本跨度 = 21 格(cols 5..25); row3 = 20 格
RECORD_SPANS = (
    {'off': 0x7561F0, 'n': 20, 'row': 3, 'fill': 0x5018},   # 变体 A(现网)
    {'off': 0x756228, 'n': 21, 'row': 4, 'fill': 0x5018},
)
# 同文本的第二份表(填充 0x502A, 与本画面不同), 只记录不在此模块改写
RECORD_VARIANT_B = (
    {'off': 0x756378, 'n': 20, 'row': 3, 'fill': 0x502A},
    {'off': 0x7563B0, 'n': 21, 'row': 4, 'fill': 0x502A},
)


def _record_cells(rom: bytes):
    """从真实源表读出空记录提示引用的全部图块 ID(含填充), 用于证明独占性。"""
    tiles = set()
    for span in RECORD_SPANS + RECORD_VARIANT_B:
        for i in range(span['n']):
            tiles.add(struct.unpack_from('<H', rom, span['off'] + i * 2)[0] & 1023)
    return tiles


def build_record_canvas(font, label='暂无记录', advance=16, top=0, glyph_px=16):
    """空记录提示文本带(21 格 x 2 格 = 168x16 索引图, bank5)。"""
    w = RECORD_WIDTH * 8
    canvas = [[RECORD_FILL_SHADE] * w for _ in range(16)]
    width = advance * (len(label) - 1) + glyph_px
    x0 = ((w - width) // 2 + 4) // 8 * 8
    for k, ch in enumerate(label):
        im = bitmap(ch, font, glyph_px)
        gx = x0 + k * advance
        for yy in range(16):
            for xx in range(glyph_px):
                if im.getpixel((xx, yy)) and 0 <= top + yy < 16 and 0 <= gx + xx < w:
                    canvas[top + yy][gx + xx] = RECORD_INK
    return canvas


def _pack_cell(canvas, y0, x0) -> bytes:
    px = [canvas[y0 + y][x0 + x] for y in range(8) for x in range(8)]
    return bytes(px[n] | px[n + 1] << 4 for n in range(0, 64, 2))


def assign_cells(cells, atlas, free, by_content, allocated):
    """把 [(packed, bank)] 单元映射到图块 ID; 只允许覆写 free 池中的槽位。"""
    entries = []
    for packed, bank in cells:
        slot = by_content.get(packed)
        if slot is None:
            if not free:
                raise ValueError('Tile budget exhausted (proven-exclusive slots insufficient)')
            slot = free.pop(0)
            atlas[slot * 32:slot * 32 + 32] = packed
            by_content[packed] = slot
            allocated.add(slot)
        entries.append(slot | (bank << 12))
    return entries


def assign_tiles(canvas, atlas, safe_ids, fixed_by_content):
    """标题 4x14 单元 -> 图块 ID。返回 (entries, new_atlas, allocated:set)。"""
    new_atlas = bytearray(atlas)
    free = sorted(safe_ids)
    by_content = dict(fixed_by_content)
    allocated = set()
    cells = [(_pack_cell(canvas, r * 8, c * 8), TITLE_BANK) for r in range(4) for c in range(14)]
    entries = assign_cells(cells, new_atlas, free, by_content, allocated)
    return entries, bytes(new_atlas), allocated


def _guarded_write(rom, offset, expected, data, tag):
    if rom[offset:offset + len(expected)] != expected:
        raise ValueError('Unexpected source bytes at ' + tag)
    return (offset, data, tag)


def _veneer(rom, offset, expected, target, tag):
    if rom[offset:offset + len(expected)] != expected:
        raise ValueError('Unexpected code at ' + tag)
    from cn_engine import veneer
    return (offset, veneer(target, 3), tag)


def thumb16_only(code: bytes, address: int) -> None:
    """ARMv4T 守卫: 拒绝任何 32 位 Thumb-2 编码(Keystone 可能为高寄存器/远跳生成)。"""
    import capstone
    md = capstone.Cs(capstone.CS_ARCH_ARM,
                     capstone.CS_MODE_THUMB | capstone.CS_MODE_LITTLE_ENDIAN)
    seen = 0
    for ins in md.disasm(code, address):
        if len(ins.bytes) != 2:
            raise ValueError('Thumb-2 instruction emitted: %s %s' % (ins.mnemonic, ins.op_str))
        seen += len(ins.bytes)
    if seen != len(code):
        raise ValueError('Stub did not disassemble as pure 16-bit Thumb')


def install_decode_gateway(rom: bytes, append, pairs, meta_out):
    """在 native 解压器入口安装 gateway(与 v03 file_ui gateway 同机制)。

    pairs: [(request_source_address, replacement_source_address), ...]
    对命中 request 的调用, 用 replacement 源替代; 其余请求原样走 stock 解压器。
    veneer 使用 ldr+bx(绝对跳转), 不受 Thumb 相对分支 ±4MB 限制。
    只使用 r0-r3 低寄存器 -> 全部 16 位 Thumb, 兼容 ARM7TDMI。
    """
    if rom[NATIVE_DECODER:NATIVE_DECODER + len(EXPECT_NATIVE_PROLOGUE)] != EXPECT_NATIVE_PROLOGUE:
        raise ValueError('Native decoder prologue moved')
    table = b''.join(struct.pack('<II', a, b) for a, b in pairs) + b'\0' * 8
    table_at = append(table)
    stub_at = append(b'\0' * 128)
    # r2/r3 是调用者不保留的 scratch; 解码器自己在 0x98AE2 重设 r2/r3。
    lines = [
        'ldr r2, =%d' % (BASE + table_at),
        'search:',
        'ldr r3, [r2]',
        'cmp r3, #0',
        'beq stock',
        'cmp r3, r0',
        'beq paired',
        'adds r2, #8',
        'b search',
        'paired:',
        'ldr r0, [r2, #4]',
        'stock:',
        'push {r4, r5, r6, r7, lr}',
        'mov r4, r8',
        'mov r5, sb',
        'mov r6, sl',
        'ldr r3, =%d' % (BASE + NATIVE_DECODER_RESUME + 1),   # +1: bx 需要 Thumb 位
        'bx r3',
    ]
    code = asm('\n'.join(lines), BASE + stub_at)
    thumb16_only(code, BASE + stub_at)
    if len(code) > 128:
        raise ValueError('Decode gateway stub too large')
    writes = [(stub_at, code, 'file-label-decode-gateway'), (table_at, table, 'file-label-decode-pairs')]
    writes.append(_veneer(rom, NATIVE_DECODER, EXPECT_NATIVE_PROLOGUE, BASE + stub_at, 'native-decoder-entry'))
    meta_out['gateway'] = {'hook': NATIVE_DECODER, 'stub': stub_at, 'pairs_table': table_at,
                           'pairs': [{'request': hex(a), 'replacement': hex(b)} for a, b in pairs],
                           'design': 'source-matched swap inside the existing native decoder; '
                                     'caller base and all non-tiles derivations untouched'}
    return writes


def file_label_engine(rom: bytes, append, title_label: str = '冒险之书',
                      record_label: str = '暂无记录',
                      title: bool = True, record: bool = True, gateway: bool = True):
    """冒险之书菜单图片字补丁(顶部标题 + 空存档记录提示)。返回 (writes, metadata)。

    两项共用同一份 atlas, 因此只 append 一份改后 atlas, 只登记一个 gateway 请求。
    gateway=True 时安装独立 decode gateway(用于独立验证); 父 build 合并时可用
    meta['gateway_pair'] 把该请求并入既有 file_ui gateway, 避免重复 hook 0x98AC8。
    """
    _require(rom)
    atlas = _deep(rom, ATLAS)
    if len(atlas) != 32768:
        raise ValueError('File atlas capacity changed')

    font = load_bdf(ROOT / 'assets/fonts/unifont16/unifont-16.0.03.bdf')
    new_atlas = bytearray(atlas)
    writes = []
    meta = {'kind': 'file-label', 'source_atlas': ATLAS, 'decoded_tiles': len(atlas),
            'tile_count_total': 1024, 'palette_source': PALETTE, 'bg_map_source': BG_MAP}
    allocated_all = set()

    # 1) 先各自证明"独占槽位"集合。两个集合互不相交:
    #    被任一方独占的图块都会被另一方的消费者枚举看见。
    title_safe = record_safe = []
    if title:
        used = consumer_tiles(rom, exclude=[(TITLE_OVERLAY, TITLE_OVERLAY + TITLE_ENTRIES * 2)])
        orig_tiles = set(v & 1023 for v in original_title(rom))
        title_safe = sorted(orig_tiles - used)
        if not title_safe:
            raise ValueError('No provably title-exclusive tiles')
    if record:
        used_r = consumer_tiles(rom, exclude=[(s['off'], s['off'] + s['n'] * 2)
                                              for s in RECORD_SPANS + RECORD_VARIANT_B])
        # v05 leaves variant B raw tables unchanged, so do not steal their IDs.
        # The worker excluded both A and B and would corrupt the untouched B.
        variant_b_ids = {struct.unpack_from('<H',rom,span['off']+i*2)[0]&1023
                         for span in RECORD_VARIANT_B for i in range(span['n'])}
        record_safe = sorted(_record_cells(rom) - used_r - variant_b_ids)
        # An empty exclusive set is valid: variant B shares all glyph IDs.
        # Allocate A only from independently census-unreferenced spare IDs.

    # Parent native16 variant needs a few more tiles than the worker native12.
    # Reserve numeric/OBJ/helper prefix and all traced raw/packed consumers.
    # These are census-unreferenced IDs, not an assertion of every game screen.
    spare = sorted(set(range(256, 1024)) - consumer_tiles(rom))
    title_spares = spare if title else []
    record_spares = spare if record else []
    record_safe = sorted(set(record_safe) | set(record_spares))
    title_safe = sorted(set(title_safe) | set(title_spares))
    meta['census_unreferenced_spares'] = sorted(set(title_spares + record_spares))
    meta['variant_B_original_ids_preserved'] = sorted(variant_b_ids) if record else []
    meta['consumer_census_scope'] = 'declared file-menu maps/raw tables; dynamic prefix0..255 reserved, not full-game proof'

    # 2) 固定内容表只含"两个独占集合之外"的图块。任何单元若不能命中固定图块,
    #    就必须从自己的独占池分配, 绝不引用"稍后会被改写"的槽位。
    fixed_ids = set(range(1024)) - set(title_safe) - set(record_safe)
    by_content = {}
    for i in sorted(fixed_ids):
        by_content.setdefault(bytes(new_atlas[i * 32:i * 32 + 32]), i)

    if title:
        _orig, canvas = build_cn_title(rom, atlas, font, title_label)
        free = sorted(set(title_safe)-set(spare)) + sorted(set(title_safe)&set(spare))
        cells = [(_pack_cell(canvas, r * 8, c * 8), TITLE_BANK) for r in range(4) for c in range(14)]
        entries = assign_cells(cells, new_atlas, free, by_content, allocated_all)
        overlay = b''.join(struct.pack('<H', e) for e in entries)
        writes.append(_guarded_write(rom, TITLE_OVERLAY,
                                     rom[TITLE_OVERLAY:TITLE_OVERLAY + TITLE_ENTRIES * 2],
                                     overlay, 'cn-title-overlay'))
        meta['title'] = {
            'label': title_label, 'font': 'native Unifont16 dark-blue single-color no shadow',
            'source_overlay': TITLE_OVERLAY,
            'format': '14x4 raw u16 entries, bank 8, copied verbatim to the map at 0x0600C850',
            'safe_slots': title_safe,
            'allocated_slots': sorted(set(e & 1023 for e in entries) & allocated_all),
            'reused_existing_tiles': sorted(set(e & 1023 for e in entries) - allocated_all),
            'preserved': 'all non-declared atlas tiles byte-identical; palette/bg map/caller base untouched; decoder source gateway shared with instruction maps',
        }

    if record:
        rcanvas = build_record_canvas(font, record_label)
        free = sorted(set(record_safe) - allocated_all)
        for span in RECORD_SPANS:
            cur = rom[span['off']:span['off'] + span['n'] * 2]
            row = 0 if span['row'] == 3 else 1
            cols = [(_pack_cell(rcanvas, row * 8, c * 8), RECORD_BANK) for c in range(span['n'])]
            entries = assign_cells(cols, new_atlas, free, by_content, allocated_all)
            data = b''.join(struct.pack('<H', e) for e in entries)
            writes.append(_guarded_write(rom, span['off'], cur, data,
                                         'cn-record-row%d-%06x' % (span['row'], span['off'])))
        meta['record'] = {
            'label': record_label, 'font': 'native Unifont16 original dark-brown ink15 no shadow',
            'ink_palette_index': RECORD_INK, 'background_palette_index': RECORD_FILL_SHADE,
            'color_scope': 'record glyph pixels only; original palette, native selected/dimmed handling, variant-B and all art unchanged',
            'format': 'box text rows (map rows 3/4, cols 5..25) as raw u16 entries in variant-A tables',
            'spans': [{'offset': s['off'], 'entries': s['n'], 'row': s['row'], 'fill': hex(s['fill'])}
                      for s in RECORD_SPANS],
            'safe_slots': record_safe,
            'allocated_slots': sorted(set(allocated_all) & (set(record_safe)-set(meta.get('title',{}).get('allocated_slots',[])))),
            'unpatched_variant': [{'offset': s['off'], 'entries': s['n']} for s in RECORD_VARIANT_B],
            'unpatched_note': 'second copy of the same japanese text with fill 0x502A; not shown on the '
                              'verified file-select screen, left unchanged and explicitly unverified.',
        }

    # 除被重新分配的安全槽位外, 其余图块必须逐字节不变
    for i in range(1024):
        if i in allocated_all:
            continue
        if new_atlas[i * 32:i * 32 + 32] != atlas[i * 32:i * 32 + 32]:
            raise ValueError('Non-safe tile modified %d' % i)

    stream = literal(bytes(new_atlas))
    atlas_at = append(stream)

    # loader 顺序守卫: tiles 源必须仍是 base+0xE0, 目标仍是 0x06000000
    if rom[LOADER_TILES_ADD0 - BASE:LOADER_TILES_ADD0 - BASE + 4] != EXPECT_LOADER_ADD:
        raise ValueError('Loader tiles base instructions moved')
    if rom[LOADER_TILES_DEST - BASE:LOADER_TILES_DEST - BASE + 4] != EXPECT_LOADER_DEST:
        raise ValueError('Loader tiles destination moved')
    if rom[LOADER_TILES_BL - BASE:LOADER_TILES_BL - BASE + 4] != EXPECT_LOADER_BL:
        raise ValueError('Loader decoder call moved')

    meta['cn_atlas_stream'] = atlas_at
    meta['atlas_source'] = ATLAS
    meta['allocated_slots'] = sorted(allocated_all)
    meta['gateway_pair'] = [BASE + TILES_SOURCE, BASE + atlas_at]
    meta['scope'] = ('adventure-book top title and the empty-record prompt (variant-A tables); '
                     'other file-menu screens and box variant B unchanged')
    if gateway:
        writes += install_decode_gateway(rom, append,
                                         [(BASE + TILES_SOURCE, BASE + atlas_at)], meta)
    return writes, meta
