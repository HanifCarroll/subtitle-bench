#!/usr/bin/env python3
"""Offline checks for source-linked translation drafts."""

import json
import runpy
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


SCRIPTS = Path(__file__).resolve().parent
TRANSLATE = runpy.run_path(str(SCRIPTS / "translate-subtitles.py"))
SEMANTIC = runpy.run_path(str(SCRIPTS / "semantic-review.py"))


class TranslationUnitTests(unittest.TestCase):
    def test_independent_english_layout_produces_linked_draft(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.srt"
            english = root / "english.srt"
            mapping = root / "utterances.json"
            output = root / "draft.json"
            source.write_text(
                "1\n00:00:01,000 --> 00:00:02,000\nMerhaba.\n\n"
                "2\n00:00:02,000 --> 00:00:03,000\nNasılsın?\n",
                encoding="utf-8")
            english.write_text(
                "1\n00:00:01,000 --> 00:00:03,000\nHello. How are you?\n",
                encoding="utf-8")
            manifest = SEMANTIC["prepare"](source, english, mapping)
            args = SimpleNamespace(source=source, output=output, utterance_map=mapping,
                                   source_language="tr", batch_size=15)
            calls = []

            def answer(prompt, context):
                calls.append(context)
                return json.dumps({"cues": [
                    {"id": 1, "text": "Hello."},
                    {"id": 2, "text": "How are you?"},
                ]}), {"test_tokens": 2}

            with patch.dict(TRANSLATE["translate"].__globals__,
                            {"request_translation": answer}):
                TRANSLATE["translate"](args)
            result = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(len(calls), 1)
            self.assertEqual(result["translations"], [
                {"source_ids": [manifest["utterances"][0]["id"]], "text": "Hello."},
                {"source_ids": [manifest["utterances"][1]["id"]],
                 "text": "How are you?"},
            ])
            self.assertEqual(english.read_text(encoding="utf-8").count("-->"), 1)
            self.assertTrue(output.with_suffix(".translation.json").is_file())


if __name__ == "__main__":
    unittest.main()
