"""Native-width Chinese line breaking for GBA dialogue.

Author controls are never dropped/reordered. COLOR is a widthless soft boundary;
player-name/dynamic slots remain indivisible. No enlargement or font resampling.
SCROLL/NEWLINE are still consumed by the original runtime, not rewritten hooks.
"""
LINE_START_FORBIDDEN = frozenset('，。！？、；：,.;:!?%％‰）)]｝}》〉」』】〕〗〙〛”’…')
LINE_END_FORBIDDEN = frozenset('（([｛{《〈「『【〔〖〘〚“‘')


def _glyph_width(token, codec, compact):
    if isinstance(token, str):
        return codec.width(token, compact=compact)
    if token == ['PLAYER-NAME']:
        # This reader uses PRIMARY IDs even in compact dialogue. Do not reserve
        # 4*12 here: a saved four-cell CJK name still renders at main_px.
        return 4 * (codec.main_px + 1) - 1
    if token[0] == 'DYNAMIC-TEXT':
        return 55  # Existing build contract, not all possible dynamic texts.
    if token[0] == 'GLYPH':
        return codec.stock_width(token[1])
    raise ValueError('Not a visible glyph ' + repr(token))


def _clusters(tokens, codec):
    """Yield drawable clusters and hard controls; COLOR remains in source order."""
    group = []
    pending = []
    previous = None
    for token in tokens:
        units = list(codec.units(token)) if isinstance(token, str) else [token]
        for unit in units:
            if isinstance(unit, list) and unit[0] == 'COLOR':
                pending.append(unit)
                continue
            visible = isinstance(unit, str) or (isinstance(unit, list) and
                       unit[0] in ('PLAYER-NAME', 'DYNAMIC-TEXT', 'GLYPH'))
            if not visible:
                if group:
                    yield True, group
                    group = []
                for item in pending:
                    yield False, [item]
                pending = []
                yield False, [unit]
                previous = None
                continue
            joined = (previous in LINE_END_FORBIDDEN if isinstance(previous, str) else False) or \
                     (unit in LINE_START_FORBIDDEN if isinstance(unit, str) else False)
            if group and not joined:
                yield True, group
                group = []
            group.extend(pending)
            pending = []
            group.append(unit)
            previous = unit
    if group:
        yield True, group
    for item in pending:
        yield False, [item]


def reflow(tokens, codec, width=208, interactive=True, compact=False):
    if width <= 0:
        raise ValueError('Nonpositive dialogue width')
    out = []
    x = 0
    lines = 1
    inserted = 0
    maxwidth = 0
    protected = 0
    warnings = []

    def emit(token):
        if isinstance(token, str) and out and isinstance(out[-1], str):
            out[-1] += token
        else:
            out.append(token)

    def newline(automatic):
        nonlocal x, lines, inserted, maxwidth
        if automatic and not interactive:
            raise ValueError('Noninteractive line overflow requires window profile')
        if automatic and lines >= 2:
            out.extend([['SHOW-PROMPT'], ['WAIT-INPUT']])
            lines = 0
            inserted += 1
        out.append(['NEWLINE'])
        lines += 1
        maxwidth = max(maxwidth, x)
        x = 0

    for visible, cluster in _clusters(tokens, codec):
        if not visible:
            token = cluster[0]
            if token == ['NEWLINE']:
                newline(False)
            else:
                emit(token)
                if token in (['WAIT-INPUT'], ['YES-NO']):
                    lines = 0
                if token in (['CLEAR'], ['SWITCH-WINDOW']):
                    x = 0
                    lines = 1
            continue
        advances = [_glyph_width(t, codec, compact) for t in cluster
                    if not isinstance(t, list) or t[0] != 'COLOR']
        # Fixed engine advances include one separator only after the first item.
        cluster_width = sum(advances) + max(0, len(advances) - 1)
        if cluster_width > width:
            # A malformed long punctuation chain or undersized custom window
            # must not silently overrun. Preserve readable characters, report.
            warnings.append('unbreakable_cluster_exceeds_width')
            for token in cluster:
                if isinstance(token, list) and token[0] == 'COLOR':
                    emit(token)
                    continue
                w = _glyph_width(token, codec, compact)
                if w > width:
                    raise ValueError('Glyph/placeholder exceeds dialogue width')
                if x + w + bool(x) > width:
                    newline(True)
                x += w + bool(x)
                emit(token)
            continue
        if x + cluster_width + bool(x) > width:
            newline(True)
            protected += len(advances) > 1
        for token in cluster:
            if not isinstance(token, list) or token[0] != 'COLOR':
                x += _glyph_width(token, codec, compact) + bool(x)
            emit(token)
    maxwidth = max(maxwidth, x)
    return out, {'max_width': maxwidth, 'added_waits': inserted,
                 'linebreak_profile': 'native-width-kinsoku-v05',
                 'protected_punctuation_wraps': protected,
                 'layout_warnings': warnings}
