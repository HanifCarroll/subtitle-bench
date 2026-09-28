#!/usr/bin/env python3
"""Live, non-duplicating throughput trial. Uses episodes 2–8 as real outputs."""

import os
import runpy
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

root = Path(__file__).parents[2]
parse = runpy.run_path(str(Path(__file__).with_name("light-pass.py")))["parse_srt"]
output = root / "Episodes"
logs = root / "Workflow/logs/benchmark"
logs.mkdir(exist_ok=True)
report = root / "Workflow/metadata/benchmark.tsv"


def job(number, workers):
    src = next((root / "Episodes").glob(f"{number:03d}*.tr.srt"))
    dst = output / src.name.replace(".tr.srt", ".en.srt")
    if dst.exists():
        raise RuntimeError(f"refusing to overwrite episode {number}")
    cues = parse(src.read_text())
    env = os.environ.copy()
    env["TRANSLATE_WORKERS"] = str(workers)
    start = time.monotonic()
    with (logs / f"{number:03d}.log").open("w") as log:
        result = subprocess.run([sys.executable, str(Path(__file__).with_name("translate-episode.py")), str(src), str(dst)],
                                env=env, stdout=log, stderr=subprocess.STDOUT)
    elapsed = time.monotonic() - start
    if result.returncode == 0:
        translated = parse(dst.read_text())
        assert [(c["id"], c["time"]) for c in cues] == [(c["id"], c["time"]) for c in translated]
    return number, workers, len(cues), elapsed, result.returncode


def record(label, results, elapsed):
    count = sum(row[2] for row in results if row[4] == 0)
    errors = sum(row[4] != 0 for row in results)
    line = f"{label}\t{','.join(str(row[0]) for row in results)}\t{count}\t{elapsed:.1f}\t{count / elapsed:.1f}\t{errors}\n"
    with report.open("a") as file:
        file.write(line)
    print(line.strip(), flush=True)


if __name__ == "__main__":
    if not os.environ.get("DEEPSEEK_API_KEY"):
        raise SystemExit("set DEEPSEEK_API_KEY")
    if report.exists():
        raise SystemExit("benchmark.tsv exists; refusing to repeat API calls")
    report.write_text("setting\tepisodes\tcues\tseconds\tcues_per_second\tfailed_files\n")
    for number, workers in ((2, 8), (3, 16), (4, 32)):
        result = job(number, workers)
        record(str(workers), [result], result[3])
    start = time.monotonic()
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda number: job(number, 8), range(5, 9)))
    record("4x8", results, time.monotonic() - start)
