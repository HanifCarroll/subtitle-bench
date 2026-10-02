#!/usr/bin/env python3
"""Offline interval/identity checks; synthetic inputs do not test hearing accuracy."""

import runpy
import itertools
import json
import math
import tempfile
from argparse import Namespace
from pathlib import Path


EVENTS = runpy.run_path(str(Path(__file__).with_name("audio-event-map.py")))
SOURCE = EVENTS["SOURCE"]
CTC = runpy.run_path(str(Path(__file__).with_name("candidate-acoustic-score.py")))
WORKBENCH = runpy.run_path(str(Path(__file__).with_name("subtitle-workbench.py")))
SEPARATE = runpy.run_path(str(Path(__file__).with_name("separate-audio-mlx.py")))


def main():
    # 0. Missing, extra, and wrong-shaped weights must stop before inference.
    parameters = {"codec": Namespace(shape=(2, 3)), "text": Namespace(shape=(4,))}
    SEPARATE["require_complete_weights"](parameters, parameters.copy())
    for weights in [{"codec": parameters["codec"]},
                    {**parameters, "unknown": Namespace(shape=(1,))},
                    {**parameters, "text": Namespace(shape=(3,))}]:
        try:
            SEPARATE["require_complete_weights"](parameters, weights)
        except ValueError:
            pass
        else:
            raise AssertionError("Incomplete pretrained model could run with defaults")
    # 1. Check the CTC dynamic program against exhaustive path probabilities.
    probabilities = [[0.5, 0.3, 0.2], [0.2, 0.5, 0.3], [0.4, 0.2, 0.4]]
    log_probs = [[math.log(v) for v in frame] for frame in probabilities]
    for candidate in [[1], [1, 1], [1, 2], [2, 1]]:
        expected = 0
        for path in itertools.product(range(3), repeat=3):
            collapsed = [token for i, token in enumerate(path)
                         if token != 0 and (i == 0 or token != path[i - 1])]
            if collapsed == candidate:
                expected += math.prod(probabilities[i][t] for i, t in enumerate(path))
        assert abs(math.exp(CTC["ctc_score"](log_probs, candidate)) - expected) < 1e-12
    assert CTC["ctc_score"](log_probs, [1, 1, 1]) == -math.inf
    assert CTC["normalize"]("İSMAİL, IŞIK!") == "ismail ışık"
    for candidate in [[], [0], [9]]:
        try:
            CTC["ctc_score"](log_probs, candidate)
        except ValueError:
            pass
        else:
            raise AssertionError("Invalid CTC candidate accepted")
    # 2. Check event offsets, overlapping labels, and malformed detector output.
    result = {"dur": 2.0, "event2timestamps": {
        "speech": [[0.1, 0.5]], "music": [[0.0, 2.0]], "singing": []}}
    rows = EVENTS["event_rows"](result, [[0.8, 0.0, 0.9]] * 200, 10_000, 12_000)
    assert rows[0]["start_ms"] == 10_100 and rows[0]["end_ms"] == 10_500
    assert abs(rows[0]["confidence"] - 0.8) < 1e-6
    assert rows[1]["label"] == "music" and rows[1]["kind"] == "audio_event"
    assert EVENTS["event_rows"]({"dur": 1.0, "event2timestamps": {}}, [], 0, 1000) == []
    for intervals in [[[0.0, 3.0]], [[-1.0, 1.0]], [[float("nan"), 1.0]]]:
        try:
            EVENTS["event_rows"]({"dur": 2.0, "event2timestamps": {"speech": intervals}},
                                  [], 0, 2000)
        except ValueError:
            pass
        else:
            raise AssertionError("Invalid detector interval was accepted")
    # 3. Keep changed media/frames and event-as-words out of scene review.
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        audio = root / "audio.wav"
        audio.write_bytes(b"synthetic clip")
        receipt = {"status": "complete", "kind": "local_acoustic_evidence",
                   "model": "synthetic detector", "model_revision": "fixed revision",
                   "video_sha256": "a" * 64, "start_ms": 10_000, "end_ms": 12_000,
                   "audio_clip": str(audio), "audio_sha256": SOURCE["FILE_HASH"](audio),
                   "observations": rows}
        path = root / "events.json"
        frames = root / "frames.npy"
        frames.write_bytes(b"synthetic probabilities")
        receipt.update(probabilities=str(frames), probabilities_sha256=SOURCE["FILE_HASH"](frames))
        SOURCE["save_json"](path, receipt)
        case = {"duration_ms": 20_000, "video_sha256": "a" * 64,
                "saved_evidence": [{"path": str(path), "sha256": SOURCE["FILE_HASH"](path),
                                    "start_ms": 10_000, "end_ms": 12_000}]}
        observed = SOURCE["saved_scene_evidence"](root, case, 10_000, 12_000)
        assert len(observed) == 2 and observed[0]["kind"] == "audio_event"
        assert SOURCE["saved_evidence_questions"](root, case, []) == []
        for changed in [{**receipt, "model_revision": 1},
                        {**receipt, "observations": [{**rows[0], "confidence": float("nan")}]},
                        {**receipt, "observations": [{**rows[0], "end_ms": 20_000}]}]:
            try:
                SOURCE["local_acoustic_rows"](changed, 10_000, 12_000)
            except ValueError:
                pass
            else:
                raise AssertionError("Malformed acoustic receipt accepted")
        frames.write_bytes(b"changed probabilities")
        try:
            SOURCE["local_acoustic_rows"](receipt, 10_000, 12_000)
        except ValueError:
            pass
        else:
            raise AssertionError("Changed frame probabilities were accepted")
        frames.write_bytes(b"synthetic probabilities")
        audio.write_bytes(b"changed clip")
        try:
            SOURCE["saved_scene_evidence"](root, case, 10_000, 12_000)
        except ValueError:
            pass
        else:
            raise AssertionError("Changed audio was accepted")
        # 4. Expose token exhaustion even for short text; reject multi-chunk input.
        video = root / "video.mkv"
        video.write_bytes(b"synthetic video")
        working = root / "working.tr.srt"
        working.write_text("1\n00:00:00,000 --> 00:00:01,000\nMerhaba.\n")
        SOURCE["save_json"](root / "case.json", {"video": str(video),
            "video_sha256": SOURCE["FILE_HASH"](video), "duration_ms": 1000, "language": "tr"})
        identity = {"video_sha256": SOURCE["FILE_HASH"](video), "model": "synthetic",
            "model_revision": "fixed", "language": "Turkish", "window_ms": 30000,
            "max_tokens": 256, "windows": {"0": {"start_ms": 0, "end_ms": 1000,
                "text": "Merhaba.", "generation_tokens": 256}}}
        SOURCE["save_json"](root / "cache.json", identity)
        args = Namespace(case=root, output=root / "report.json", cache=root / "cache.json",
            model="synthetic", model_revision="fixed", language="Turkish",
            window_seconds=30, start_seconds=0, end_seconds=None, max_tokens=256)
        WORKBENCH["audio_check"](args)
        assert json.loads(args.output.read_text())["windows"][0]["status"] == "truncated"
        args.window_seconds = 31
        try:
            WORKBENCH["audio_check"](args)
        except ValueError as error:
            assert "10 and 30" in str(error)
        else:
            raise AssertionError("Multi-chunk token budget could conceal an unprocessed tail")
    print("local acoustic evidence checks passed (synthetic only)")


if __name__ == "__main__":
    main()
