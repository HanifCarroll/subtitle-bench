#!/usr/bin/env python3
"""Resume remaining episodes; eight episodes x 32 requests, no duplicate outputs."""

import os
import runpy
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

root = Path(__file__).parents[2]
parse = runpy.run_path(str(Path(__file__).with_name("light-pass.py")))["parse_srt"]
logs = root / "Workflow/logs/translation"
logs.mkdir(exist_ok=True)


def run(src):
    dst = root / "Episodes" / src.name.replace(".tr.srt", ".en.srt")
    if dst.exists():
        return src.name[:3], "skipped", 0
    env = os.environ.copy()
    env["TRANSLATE_WORKERS"] = "32"
    start = time.monotonic()
    with (logs / f"{src.name[:3]}.log").open("w") as log:
        status = subprocess.run([sys.executable, str(Path(__file__).with_name("translate-episode.py")), str(src), str(dst)],
                                env=env, stdout=log, stderr=subprocess.STDOUT).returncode
    if status == 0:
        original = parse(src.read_text())
        result = parse(dst.read_text())
        assert [(c["id"], c["time"]) for c in original] == [(c["id"], c["time"]) for c in result]
    return src.name[:3], "done" if status == 0 else "failed", round(time.monotonic() - start, 1)


if __name__ == "__main__":
    if not os.environ.get("DEEPSEEK_API_KEY"):
        raise SystemExit("set DEEPSEEK_API_KEY")
    sources = sorted((root / "Episodes").glob("*.tr.srt"))
    if len(sources) != 104:
        raise SystemExit(f"expected 104 Turkish subtitles, found {len(sources)}")
    failures = []
    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = [pool.submit(run, src) for src in sources]
        for future in as_completed(futures):
            number, status, elapsed = future.result()
            if status == "failed":
                failures.append(number)
            if status != "skipped":
                print(number, status, elapsed, flush=True)
    if failures:
        raise SystemExit(f"Incomplete episodes (rerun to resume): {', '.join(failures)}")
    print("ALL_ENGLISH_DONE", flush=True)
