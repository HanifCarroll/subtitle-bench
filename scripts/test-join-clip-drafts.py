#!/usr/bin/env python3
"""Check reusable core selection without discarding seam evidence."""

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


SCRIPTS = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location("join_clip_drafts",
                                              SCRIPTS / "join-clip-drafts.py")
JOIN = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(JOIN)


class JoinClipDraftsTest(unittest.TestCase):
    def test_core_draft_selects_one_copy_and_keeps_seam_observations(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            video = root / "episode.webm"
            video.write_bytes(b"test video identity")
            left = root / "left.srt"
            right = root / "right.srt"
            JOIN.write_srt(left, [
                {"start_ms": 200, "end_ms": 400, "text": "First."},
                {"start_ms": 900, "end_ms": 1100, "text": "Seam left."},
            ])
            JOIN.write_srt(right, [
                {"start_ms": 100, "end_ms": 300, "text": "Seam right."},
                {"start_ms": 400, "end_ms": 600, "text": "Last."},
            ])
            manifest = root / "manifest.json"
            manifest.write_text(json.dumps({
                "video": str(video), "language": "tr", "clips": [
                    {"srt": str(left), "offset_ms": 0,
                     "core_start_ms": 0, "core_end_ms": 1000},
                    {"srt": str(right), "offset_ms": 800,
                     "core_start_ms": 1000, "core_end_ms": 2000},
                ],
            }))
            original = JOIN.extract_review_audio
            JOIN.extract_review_audio = lambda _video, _start, _end, path: path.write_bytes(b"clip")
            try:
                JOIN.join(manifest, root / "joined", 200, core_only=True)
            finally:
                JOIN.extract_review_audio = original
            output = JOIN.READ_CUES(root / "joined/draft.tr.srt")
            self.assertEqual([cue["text"] for cue in output],
                             ["First.", "Seam right.", "Last."])
            review = json.loads((root / "joined/seam-review.json").read_text())
            self.assertEqual(review["selection"], "midpoint_core")
            self.assertEqual(review["seams"][0]["left"][-1]["text"], "Seam left.")
            self.assertEqual(review["seams"][0]["right"][0]["text"], "Seam right.")


if __name__ == "__main__":
    unittest.main()
