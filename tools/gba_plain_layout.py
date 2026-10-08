"""Source-scoped layout for plain consumers with fixed, unrelocated tilemaps.

Do not shrink the font or insert NEWLINE. The actual 096C40 consumer adds one
pixel for EVERY glyph and rounds ALIGN up to an 8px column; fixed caller maps
still depend on the original continuous field boundaries after translation.
Only compiler-owned blank suffixes may fill the unused field capacity.
"""
import copy, hashlib, json, struct
from cn_codec import ROOT, BASE, same_controls


def round_column(pixels):
    return (pixels + 7) // 8 * 8


def field_spans(tokens, codec, compact=True):
    if not tokens or len(tokens) % 2 != 1:
        raise ValueError('Fixed plain profile needs alternating string/ALIGN')
    cursor = 0
    spans = []
    for index, token in enumerate(tokens):
        if index % 2:
            if token != ['ALIGN']:
                raise ValueError('Fixed plain profile must preserve native ALIGN')
            cursor = round_column(cursor)
        else:
            if not isinstance(token, str):
                raise ValueError('Fixed plain field must be a string')
            cursor += sum(codec.width(c, compact=compact) + 1 for c in codec.units(token))
            spans.append({'raw_end': cursor, 'column_end': round_column(cursor)})
    return spans


def fit_fixed_fields(tokens, codec, boundaries, padding='　'):
    # Full-width and ASCII spaces alias stock glyph 1D; use verified width,
    # never a guessed 9px blank, and never add a font registry entry.
    if len(list(codec.units(padding))) != 1 or padding in codec.ids:
        raise ValueError('Fixed plain padding must be one stock blank glyph')
    if not boundaries or any(p <= 0 or p % 8 for p in boundaries) or boundaries != sorted(set(boundaries)):
        raise ValueError('Invalid fixed plain boundaries')
    if len(field_spans(tokens, codec)) != len(boundaries):
        raise ValueError('Fixed plain field count mismatch')
    result = copy.deepcopy(tokens)
    added = []
    for field, expected in enumerate(boundaries):
        index = field * 2
        count = 0
        while True:
            end = field_spans(result, codec)[field]['column_end']
            if end > expected:
                raise ValueError(f'Fixed plain field {field} overflows {expected}px')
            if end == expected:
                break
            result[index] += padding
            count += 1
        added.append(count)
    if not same_controls(tokens, result):
        raise ValueError('Fixed plain compiler changed controls')
    return result, added


def apply_plain_profile(record, tokens, codec, source):
    profiles = json.loads((ROOT/'data/gba-plain-window-profiles.json').read_text('utf-8'))
    profile = profiles.get(record['id'])
    if profile is None:
        return tokens, None
    p = profile
    a, b = p['consumer_start'], p['consumer_end']
    if (record['format'] != 'plain' or int(record['offset'], 16) != p['source_offset'] or
            record['original_hex'] != p['source_hex'] or
            source[p['source_offset']:p['source_offset']+len(bytes.fromhex(p['source_hex']))].hex() != p['source_hex'] or
            hashlib.sha256(source[a:b]).hexdigest() != p['consumer_sha256']):
        raise ValueError('Fixed plain source/consumer fingerprint mismatch')
    if (struct.unpack_from('<I', source, p['source_literal'])[0] != BASE+p['source_offset'] or
            struct.unpack_from('<I', source, p['destination_literal'])[0] != p['destination'] or
            record['references'] != [{'offset': f"{p['source_literal']:06X}", 'kind': 'code-literal-candidate'}]):
        raise ValueError('Fixed plain source literal/destination/consumer set mismatch')
    if codec.stock.inverse.get(p['padding_glyph']) != p['padding_stock_code']:
        raise ValueError('Fixed plain padding glyph changed')
    source_spans = field_spans(record['tokens'], codec, compact=False)
    if [s['column_end'] for s in source_spans] != p['field_end_pixels']:
        raise ValueError('Fixed plain source native widths changed')
    if not same_controls(record['tokens'], tokens):
        raise ValueError('Fixed plain author controls changed')
    fitted, added = fit_fixed_fields(tokens, codec, p['field_end_pixels'], p['padding_glyph'])
    spans = field_spans(fitted, codec)
    if spans[-1]['column_end'] // 8 * 2 != p['tile_count']:
        raise ValueError('Fixed plain tile capacity mismatch')
    metadata = dict(p)
    metadata.update({'compiler_added_blank_glyphs': added,
                     'author_tokens': copy.deepcopy(tokens),
                     'source_field_spans': source_spans,
                     'compiled_field_spans': spans,
                     'source_controls_preserved': True})
    return fitted, metadata
