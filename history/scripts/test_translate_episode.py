#!/usr/bin/env python3
"""Offline concurrency/checkpoint smoke test: python3 test_translate_episode.py."""

import json
import os
import runpy
import sys
import tempfile
import threading
import urllib.request
import time
from pathlib import Path
from unittest.mock import patch

module = runpy.run_path(str(Path(__file__).with_name("translate-episode.py")))
main = module["main"]
parse_srt = runpy.run_path(str(Path(__file__).with_name("light-pass.py")))["parse_srt"]
lock = threading.Lock()
active = peak = 0
attempts = []
fail_once = True


def fake_translate(cues, start, key):
    global active, peak, fail_once
    with lock:
        active += 1
        peak = max(peak, active)
        attempts.append(start)
    time.sleep(0.03)
    with lock:
        active -= 1
        fail = start == 30 and fail_once
        if fail:
            fail_once = False
    if fail:
        raise RuntimeError("temporary provider failure")
    return {c["id"]: f"English {c['id']}" for c in cues[start:start + 30]}


with tempfile.TemporaryDirectory() as tmp:
    src, dst = Path(tmp)/"test.tr.srt", Path(tmp)/"test.en.srt"
    src.write_text("\n\n".join(f"{i}\n00:00:00,000 --> 00:00:01,000\nMerhaba {i}" for i in range(1, 96)) + "\n")
    with patch.dict(os.environ, {"DEEPSEEK_API_KEY": "test"}), patch.object(sys, "argv", ["translate-episode.py", str(src), str(dst)]):
        main.__globals__["translate"] = fake_translate
        try:
            main()
        except RuntimeError as err:
            assert "1 batches failed" in str(err)
        else:
            raise AssertionError("expected one failed batch")
        checkpoint = dst.with_suffix(".progress.json")
        assert not dst.exists() and len(json.loads(checkpoint.read_text())["texts"]) == 65
        assert peak > 1, "batches ran serially"
        attempts.clear()
        main()
        assert attempts == [30], f"resume repeated finished batches: {attempts}"
    original, translated = parse_srt(src.read_text()), parse_srt(dst.read_text())
    assert [c["time"] for c in original] == [c["time"] for c in translated]
    assert [c["text"] for c in translated] == [f"English {i}" for i in range(1, 96)]
    assert not checkpoint.exists()


class Response:
    def __init__(self, payload):
        self.payload = json.dumps(payload).encode()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        pass

    def read(self, *_):
        return self.payload


def incomplete_large_batch(request, timeout):
    target = json.loads(json.loads(request.data)["messages"][1]["content"])["target"]
    items = [{"id": c["id"], "text": f"English {c['id']}"} for c in target]
    if len(target) > 15:
        items.pop()
    return Response({"choices": [{"message": {"content": json.dumps({"cues": items})}}]})


main.__globals__["translate"] = module["translate"]
with patch.object(urllib.request, "urlopen", incomplete_large_batch), patch.object(time, "sleep"):
    translated = module["translate"]([{"id": i, "text": "Merhaba"} for i in range(1, 31)], 0, "test")
    assert set(translated) == set(range(1, 31))


def timeout_large_batch(request, timeout):
    target = json.loads(json.loads(request.data)["messages"][1]["content"])["target"]
    if len(target) > 15:
        raise TimeoutError("slow response")
    return incomplete_large_batch(request, timeout)


with patch.object(urllib.request, "urlopen", timeout_large_batch), patch.object(time, "sleep"):
    translated = module["translate"]([{"id": i, "text": "Merhaba"} for i in range(1, 31)], 0, "test")
    assert set(translated) == set(range(1, 31))
print("parallel + resume + split-on-invalid-or-timeout check ok")
