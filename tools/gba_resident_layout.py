"""Original eight-cell resident label resource contract, separate from plain UI.
Each source inventory small string contains eight 8px glyph cells. Only its
trailing stock blanks may be resized; the complete semantic name is never cut.
"""
import hashlib
from cn_codec import same_controls

CONSUMER_START=0xCB676
CONSUMER_END=0xCB68A
CONSUMER_SHA='5e57ace1e57c21f0e122ce38ae74c4d8613d9730d37914e535f885ce638885d4'


def fit_resident_cells(record,tokens,codec,source):
 if record['format']!='small' or len(record['tokens'])!=1 or len(tokens)!=1 or not same_controls(record['tokens'],tokens):
  raise ValueError('Resident label must be one source/author string')
 start,end=int(record['offset'],16),int(record['end'],16)
 if source[start:end].hex()!=record['original_hex'] or hashlib.sha256(source[CONSUMER_START:CONSUMER_END]).hexdigest()!=CONSUMER_SHA:
  raise ValueError('Resident source/consumer fingerprint mismatch')
 if not record['references'] or any(ref['kind'] not in ('resident-name-table','code-literal-candidate') for ref in record['references']):
  raise ValueError('Unsupported resident label consumer reference')
 capacity=len(list(codec.units(record['tokens'][0],True)))
 if capacity!=8:raise ValueError('Resident source is not eight native cells')
 body=tokens[0].rstrip(' \u3000')
 count=len(list(codec.units(body,True)))
 if count>capacity:raise ValueError('Resident canonical name longer than eight cells; no truncation allowed')
 # Both old authored and new canonical padding are compiler/layout concerns,
 # not changes to the parent prose record or saved-name glyph ID registry.
 result=[body+'　'*(capacity-count)]
 metadata={'profile':'source-eight-cell-resident8-v1','font':'small8','source_cells':8,'semantic_name_cells':count,'compiled_cells':8,'compiled_tiles':16,'native_pixels':64,'padding_glyph':'　','padding_cells':capacity-count,'source_consumer_start':CONSUMER_START,'source_consumer_end':CONSUMER_END,'source_consumer_sha256':CONSUMER_SHA,'author_tokens':list(tokens),'semantic_name_not_truncated':True}
 return result,metadata
