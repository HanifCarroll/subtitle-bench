#!/usr/bin/env python3
"""Saved evidence cannot clear stale findings or unsupported timing kinds."""
import copy
import json
import runpy
import tempfile
import wave
from pathlib import Path

WORKBENCH = runpy.run_path(str(Path(__file__).with_name('subtitle-workbench.py')))
SOURCE = WORKBENCH['SOURCE_REVIEW']


def check():
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        # 1. Saved receipt/media integrity and interval coverage.
        audio = root / 'audio.wav'
        audio.write_bytes(b'original audio')
        result = {'route': 'saved_asr_agent', 'status': 'supported',
                  'start_ms': 100, 'end_ms': 900, 'video_sha256': 'video',
                  'source_sha256': 'source', 'agent_assessment': {
                      'reviewer': 'agent', 'reason': 'Specific saved evidence.',
                      'heard_original_audio': False}, 'observations': []}
        for index, model in enumerate(('gemini', 'scribe')):
            receipt = root / f'{index}.json'
            receipt.write_text(json.dumps({'status': 'complete', 'model': model,
                'video_sha256': 'video', 'audio_sha256': SOURCE['FILE_HASH'](audio),
                'clip': {'core_start_ms': 0, 'core_end_ms': 1000}}))
            result['observations'].append({'method': 'hosted_asr', 'model': model,
                'raw_response': str(receipt),
                'raw_response_sha256': SOURCE['FILE_HASH'](receipt),
                'audio_path': str(audio)})
        review = root / 'review.json'
        def blockers(value):
            review.write_text(json.dumps(value))
            return SOURCE['review_result_blockers'](root, str(review), 100, 900,
                                               'video', 'source')
        assert not blockers(result)
        changed = copy.deepcopy(result)
        changed['agent_assessment']['heard_original_audio'] = True
        assert blockers(changed)
        changed = copy.deepcopy(result)
        changed['video_sha256'] = 'other video'
        assert blockers(changed)
        changed = copy.deepcopy(result)
        changed['observations'][1] = changed['observations'][0]
        assert blockers(changed)
        # Rehashing a truncated receipt must still fail coverage validation.
        raw = root / '1.json'
        data = json.loads(raw.read_text())
        data['clip']['core_end_ms'] = 899
        raw.write_text(json.dumps(data))
        changed = copy.deepcopy(result)
        changed['observations'][1]['raw_response_sha256'] = SOURCE['FILE_HASH'](raw)
        assert blockers(changed)
        data['clip']['core_end_ms'] = 1000
        data['status'] = 'partial'
        raw.write_text(json.dumps(data))
        changed['observations'][1]['raw_response_sha256'] = SOURCE['FILE_HASH'](raw)
        assert blockers(changed)
        audio.write_bytes(b'changed audio')
        assert blockers(result)

        # A small physical audio/container tail is allowed only at the media end.
        with wave.open(str(audio), 'wb') as sound:
            sound.setparams((1, 2, 1000, 0, 'NONE', 'not compressed'))
            sound.writeframes(b'\0\0' * 1000)
        tail = copy.deepcopy(result)
        tail.update(end_ms=1000, video_sha256=SOURCE['FILE_HASH'](audio),
                    original_video=str(audio))
        for index, observation in enumerate(tail['observations']):
            raw = Path(observation['raw_response'])
            data = json.loads(raw.read_text())
            data.update(status='complete', video_sha256=tail['video_sha256'],
                        audio_sha256=SOURCE['FILE_HASH'](audio))
            data['clip']['core_end_ms'] = 1000 if index == 0 else 979
            raw.write_text(json.dumps(data))
            observation['raw_response_sha256'] = SOURCE['FILE_HASH'](raw)
        review.write_text(json.dumps(tail))
        assert SOURCE['review_result_blockers'](root, str(review), 100, 1000,
                                         tail['video_sha256'], 'source')
        shorter = root / 'shorter.wav'
        with wave.open(str(shorter), 'wb') as sound:
            sound.setparams((1, 2, 1000, 0, 'NONE', 'not compressed'))
            sound.writeframes(b'\0\0' * 979)
        observation = tail['observations'][1]
        raw = Path(observation['raw_response'])
        data = json.loads(raw.read_text())
        data.pop('clip')
        data.update(audio_seconds=.979, audio_sha256=SOURCE['FILE_HASH'](shorter))
        raw.write_text(json.dumps(data))
        observation.update(raw_response_sha256=SOURCE['FILE_HASH'](raw),
                           audio_path=str(shorter))
        review.write_text(json.dumps(tail))
        assert not SOURCE['review_result_blockers'](root, str(review), 100, 1000,
                                             tail['video_sha256'], 'source')
        tail['end_ms'] = 999
        review.write_text(json.dumps(tail))
        assert SOURCE['review_result_blockers'](root, str(review), 100, 999,
                                         tail['video_sha256'], 'source')

        # 2. Grouping cannot clear stale judgments or other timing kinds.
        manifest = root / 'semantic.json'
        manifest.write_text('{}')
        flag = {'id': 'many:1', 'kind': 'many_source_cues_one_target'}
        report = {'source_sha256': 'source', 'target_sha256': 'target', 'flags': [flag]}
        decisions = {'source_sha256': 'source', 'target_sha256': 'target',
            'semantic_manifest_sha256': SOURCE['FILE_HASH'](manifest), 'reviewer': 'agent',
            'findings': [{'id': 'many:1', 'finding_sha256': WORKBENCH['SEMANTIC']['fingerprint'](flag),
                'disposition': 'independent_display_grouping',
                'reason': 'All linked meanings survive across neighboring cues.'}]}
        path = root / 'grouping.json'
        path.write_text(json.dumps(decisions))
        assert not WORKBENCH['translation_decision_blockers'](report, manifest, path)
        unsupported = copy.deepcopy(report)
        unsupported['flags'][0]['kind'] = 'missing_target'
        decisions['findings'][0]['finding_sha256'] = WORKBENCH['SEMANTIC']['fingerprint'](
            unsupported['flags'][0])
        path.write_text(json.dumps(decisions))
        assert WORKBENCH['translation_decision_blockers'](unsupported, manifest, path)
        assert WORKBENCH['translation_decision_blockers'](report, manifest, path)
        manifest.write_text('{"changed": true}')
        assert WORKBENCH['translation_decision_blockers'](report, manifest, path)
    print('finalization evidence checks passed')


if __name__ == '__main__':
    check()
