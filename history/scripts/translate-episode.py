#!/usr/bin/env python3
"""Translate one cleaned Turkish SRT into English, keeping its cue timing."""

import hashlib
import json
import os
import runpy
import sys
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

base = Path(__file__).parent
srt = runpy.run_path(str(base / "light-pass.py"))
parse_srt, write_srt = srt["parse_srt"], srt["write_srt"]
BATCH = 30
WORKERS = int(os.environ.get("TRANSLATE_WORKERS", "8"))
PROMPT = """Translate Leyla ile Mecnun Turkish subtitles into faithful English.
Return JSON only: {"cues":[{"id":1,"text":"English subtitle"}]}.
Translate EVERY target cue exactly once, keeping its ID. Context cues are for understanding only; do not return them.
Preserve every meaningful spoken detail, speaker turn, repetition, uncertainty, song, insult, proper name and joke. Do not shorten or summarize to meet a reading-speed limit; fast subtitles are acceptable. Do not invent dialogue or resolve ambiguous Turkish by guessing. Use natural English word order; no explanations or notes. Use an em dash or hyphen for separate speakers when needed. Do not put timestamps or cue numbers in text.
"""


def translate(cues, start, key, size=BATCH):
    batch = cues[start : start + size]
    ids = {c["id"] for c in batch}
    previous = cues[max(0, start - 4):start]
    following = cues[start + size:start + size + 4]
    body = {
        "model": "deepseek-flash", "temperature": 0,
        "thinking": {"type": "disabled"}, "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": PROMPT},
            {"role": "user", "content": json.dumps({
                "previous": [{"id": c["id"], "text": c["text"]} for c in previous],
                "target": [{"id": c["id"], "text": c["text"]} for c in batch],
                "next": [{"id": c["id"], "text": c["text"]} for c in following],
            }, ensure_ascii=False)},
        ],
    }
    req = urllib.request.Request(
        "https://api.deepseek.com/chat/completions", data=json.dumps(body).encode(),
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
    )
    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, timeout=45) as response:
                payload = json.load(response)
            items = json.loads(payload["choices"][0]["message"]["content"])["cues"]
            result = {item["id"]: item["text"].strip() for item in items}
            if len(items) != len(ids) or set(result) != ids or not all(result.values()):
                raise ValueError("missing, duplicate, or empty translation")
            return result
        except urllib.error.HTTPError as err:
            if err.code not in (429, 500, 502, 503, 504) or attempt == 3:
                raise
        except (json.JSONDecodeError, KeyError, IndexError, TypeError, ValueError, TimeoutError) as err:
            if attempt == 3 or isinstance(err, TimeoutError):
                if len(batch) > 1:
                    half = len(batch) // 2
                    return (translate(cues, start, key, half)
                            | translate(cues, start + half, key, len(batch) - half))
                raise
        except OSError:
            if attempt == 3:
                raise
        time.sleep(min(8, 2 ** attempt))


def main():
    if len(sys.argv) != 3:
        raise SystemExit("usage: translate-episode.py CLEAN_TR.srt EN.srt")
    if not 1 <= WORKERS <= 32:
        raise SystemExit("TRANSLATE_WORKERS must be 1–32")
    key = os.environ.get("DEEPSEEK_API_KEY", "").strip()
    if not key:
        raise SystemExit("set DEEPSEEK_API_KEY")
    src, dst = map(Path, sys.argv[1:])
    raw = src.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    cues = parse_srt(raw.decode("utf-8"))
    checkpoint = dst.with_suffix(".progress.json")
    progress = json.loads(checkpoint.read_text()) if checkpoint.exists() else {"sha256": digest, "texts": {}}
    if progress["sha256"] != digest:
        raise SystemExit("source changed; remove stale progress file before retrying")
    texts = progress["texts"]
    starts = [start for start in range(0, len(cues), BATCH)
              if not all(str(c["id"]) in texts for c in cues[start:start + BATCH])]
    failures = []
    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        pending = {pool.submit(translate, cues, start, key): start for start in starts}
        for future in as_completed(pending):
            try:
                translated = future.result()
            except Exception as err:
                failures.append((pending[future], err))
                continue
            texts.update({str(k): v for k, v in translated.items()})
            temp = checkpoint.with_suffix(".tmp")
            temp.write_text(json.dumps(progress, ensure_ascii=False), encoding="utf-8")
            temp.replace(checkpoint)
            print(f"translated {len(texts)}/{len(cues)}", flush=True)
    if failures:
        raise RuntimeError(f"{len(failures)} batches failed; rerun to resume") from failures[0][1]
    for cue in cues:
        cue["text"] = texts[str(cue["id"])].replace("\r", "").strip()
    temp = dst.with_suffix(".tmp")
    write_srt(cues, temp)
    temp.replace(dst)
    checkpoint.unlink()
    print(f"done: {dst}", flush=True)


if __name__ == "__main__":
    main()
