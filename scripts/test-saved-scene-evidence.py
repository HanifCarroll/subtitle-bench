#!/usr/bin/env python3
"""Focused saved evidence reaches scene review and invalidates prior readiness."""
import json
import runpy
import tempfile
from pathlib import Path

S = runpy.run_path(str(Path(__file__).with_name('source-review.py')))
W = runpy.run_path(str(Path(__file__).with_name('subtitle-workbench.py')))
T = runpy.run_path(str(Path(__file__).with_name('agent-translate.py')))


def check():
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        def save(name, data):
            path = root / name
            path.write_text(json.dumps(data))
            return path
        video, audio = root / 'video', root / 'audio.wav'
        video.write_bytes(b'synthetic video'); audio.write_bytes(b'synthetic audio')
        source = root / 'working.tr.srt'
        S['WRITE_SRT'](source, [{'start_ms': 500, 'end_ms': 1500, 'text': 'Teşekkürler.'}])
        video_hash = S['FILE_HASH'](video)
        case = {'language': 'tr', 'video': str(video), 'video_sha256': video_hash,
                'duration_ms': 2000, 'reference': None,
                'reference_alignment': {'offset_ms': None}, 'seam_report': None}
        raw = {'status': 'complete', 'video_sha256': video_hash, 'model': 'synthetic',
               'start_ms': 900, 'comparison_parsed': [{'interval': [0, .2],
               'current_wording': 'Teşekkürler.', 'proposed_repair': 'Banyo sağda.',
               'evidence_explanation': 'Synthetic wrong recognizer alternative.'}]}
        receipt = save('focused.json', raw)
        case['saved_evidence'] = [{'path': str(receipt), 'sha256': S['FILE_HASH'](receipt),
                                  'start_ms': 900, 'end_ms': 1100}]
        save('case.json', case)
        issue = S['build_queue'](root)['issues'][0]
        assert S['saved_scene_evidence'](root, case, 800, 1200)[0]['alternative'] == 'Banyo sağda.'
        decision = {'case': str(root), 'source_sha256': S['FILE_HASH'](source),
                    'reviewer': 'synthetic test', 'reason': 'Fixture complete',
                    'coverage_assessed': True, 'material_defects_repaired': True,
                    'speech_timing_usable': True, 'ordinary_dialogue_review_complete': True,
                    'remaining_source_work': [], 'evidence': [str(receipt)]}
        ready_decision = save('ready-decision.json', decision)
        def blocked():
            try:
                S['ready_checkpoint'](source, ready_decision, root / 'blocked.json')
            except ValueError as error:
                assert 'open' in str(error)
            else:
                raise AssertionError('Known evidence escaped readiness')
        blocked()
        save('clip.json', {'video_sha256': video_hash, 'video_start_ms': 900,
             'video_end_ms': 1100, 'audio_clip': str(audio), 'audio_sha256': S['FILE_HASH'](audio)})
        review = save('review.json', {'video_sha256': video_hash,
             'source_sha256': S['FILE_HASH'](source), 'start_ms': 900, 'end_ms': 1100,
             'status': 'model_artifact', 'stages': [{'stage': stage,
             'method': 'audio_capable_model', 'model': 'synthetic-test-only',
             'prompt_version': 'fixture', 'assessment': 'Synthetic fixture only',
             'raw_response': str(receipt), 'raw_response_sha256': S['FILE_HASH'](receipt)}
             for stage in ('independent', 'comparison')]})
        S['record_decision'](root, save('retain.json', {'issue_id': issue['id'],
             'status': 'reviewed', 'reviewer': 'synthetic test',
             'expected_working_sha256': S['FILE_HASH'](source), 'evidence': ['clip.json'],
             'review_result': str(review), 'evidence_assessment': 'recognition_artifact',
             'reason': 'Fixture recognizer is wrong; retain the independently supported candidate.'}))
        assert not W['current_queue'](root)[1]
        checkpoint = root / 'ready.json'
        S['ready_checkpoint'](source, ready_decision, checkpoint)
        S['check_ready'](source, checkpoint)
        # A newly registered material finding reopens ready while old evidence stays intact.
        save('evidence-disagreements.json', {'version': 1, 'video_sha256': video_hash,
             'disagreements': [{'id': 'new-material', 'start_ms': 900, 'end_ms': 1100,
             'summary': 'New material question', 'evidence': [{'path': str(receipt),
             'sha256': S['FILE_HASH'](receipt)}]}]})
        try:
            S['check_ready'](source, checkpoint)
        except ValueError as error:
            assert 'open' in str(error)
        else:
            raise AssertionError('New finding escaped an earlier ready approval')
        save('evidence-disagreements.json', {'version': 1, 'video_sha256': video_hash,
                                         'disagreements': []})
        # A new rejection at the same interval invalidates approval without editing subtitles.
        raw['comparison_parsed'][0]['evidence_explanation'] = 'New material contrary evidence.'
        save('focused.json', raw)
        case['saved_evidence'][0]['sha256'] = S['FILE_HASH'](receipt)
        save('case.json', case)
        blocked()
        assert W['current_queue'](root)[1]
        # Native word timings expose speech wholly inside a subtitle gap, in the same scene.
        native = save('scribe.json', {'status': 'complete', 'video_sha256': video_hash,
             'model': 'synthetic-scribe', 'raw_response': {'words': [
             {'type': 'word', 'text': 'Baba', 'start': 1.8, 'end': 1.9}]}})
        case['saved_evidence'].append({'path': str(native), 'sha256': S['FILE_HASH'](native),
                                      'start_ms': 1600, 'end_ms': 2000})
        save('case.json', case)
        assert any(i['kind'] == 'possible_speech_gap' and i['summary'] == 'Baba'
                   for i in S['build_queue'](root)['issues'])
        assert any(o['text'] == 'Baba' for o in S['saved_scene_evidence'](root, case, 800, 2000))
        # Existing English correction/export survives without touching Turkish.
        progress = root / 'progress.json'
        _, record = T['current'](source, progress, 12)
        first = save('draft.json', {'source_sha256': record['source_sha256'],
             'reviewer': 'synthetic test', 'translations': [{'cue_id': 1, 'text': 'Bathroom.'}]})
        T['import_responses'](source, progress, first)
        before = S['FILE_HASH'](source)
        correction = save('correct.json', {'source_sha256': before,
             'progress_sha256': T['digest'](progress), 'reviewer': 'synthetic test',
             'reason': 'Thank-you meaning', 'translations': [{'cue_id': 1, 'text': 'Thank you.'}]})
        T['import_responses'](source, progress, correction, correction=True)
        output = root / 'export.en.srt'
        T['export'](source, progress, output)
        assert S['READ_CUES'](output)[0]['text'] == 'Thank you.'
        assert S['FILE_HASH'](source) == before
    print('saved scene evidence check ok (synthetic development tests only)')


if __name__ == '__main__':
    check()
