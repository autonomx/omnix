import sys

sys.path.insert(0,'.')
from tests.rpg.autoplay_llm_campaign import (
    _build_final_transcript_artifact_rows,
    _extract_row_presentation_intent,
    _sync_public_presentation_intent_from_validated,
    _validate_presentation_intent_for_row,
)

row = {
    'turn_index': 2,
    'player_action': 'I ask Bran who left through the side door and why they were afraid.',
    'canonical_turn_action': 'I ask Bran who left through the side door and why they were afraid.',
    'presentation_intent': {'primary_category': 'general', 'confidence': 0.0},
    'presentation_intent_parse_source': 'missing',
    'llm_presentation_category': 'general',
    'combined_background_llm_result': {
        'presentation_intent': {
            'primary_category': 'dialogue',
            'secondary_categories': ['investigation'],
            'confidence': 0.95,
            'reason': 'The player is asking Bran a direct question.',
        }
    },
    'direct_graph_action_completion': {
        'action_id': 'ask_bran_who_left_side_door',
        'mechanics': ['dialogue'],
    },
    'mechanics_covered_this_turn': ['dialogue'],
    'dialogue_action_relevance': {'ok': True, 'action_kind': 'general', 'reasons': []},
}
print('extract', _extract_row_presentation_intent(row))
vr = _validate_presentation_intent_for_row(row, action_text=row['canonical_turn_action'])
print('validated', vr)
row2 = dict(row)
row2['validated_presentation_intent'] = vr
print('sync', _sync_public_presentation_intent_from_validated(row2))
print('build', _build_final_transcript_artifact_rows(transcript=[row], transcript_artifacts={}, summary={'turns_executed':1}, session_id='test-session')[0])
