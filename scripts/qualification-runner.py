#!/usr/bin/env python3
"""Bind a held-out episode run to frozen workflow and normal input files."""

import argparse
import hashlib
import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
FREEZE = ROOT / "qualification/freeze.json"
EVENT_KINDS = {
    "agent_action", "human_intervention", "episode_specific_engineering",
    "provider_use", "failure", "partial", "production_complete",
}


def digest(path):
    value = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def now():
    return datetime.now(timezone.utc).isoformat()


def load_freeze(path=FREEZE):
    freeze = json.loads(path.read_text(encoding="utf-8"))
    for relative, expected in freeze["workflow_sha256"].items():
        target = ROOT / relative
        if not target.is_file() or digest(target) != expected:
            raise ValueError(f"Frozen workflow differs: {relative}")
    for model in freeze["model_files"]:
        target = Path(model["path"])
        if not target.is_file() or digest(target) != model["sha256"]:
            raise ValueError(f"Frozen model differs: {target.name}")
    for runtime in freeze.get("runtime_environments", []):
        expected = (ROOT / runtime["packages"]).read_bytes()
        result = subprocess.run(
            ["uv", "pip", "freeze", "--python", runtime["python"]],
            check=True, capture_output=True,
        )
        if result.stdout != expected:
            raise ValueError(f"Frozen packages differ: {runtime['python']}")
    return freeze


def input_record(path):
    if path is None:
        return None
    target = path.resolve(strict=True)
    if not target.is_file():
        raise ValueError(f"Input is not a file: {target}")
    return {"path": str(target), "sha256": digest(target)}


def start(args):
    # 1. Freeze every supplied input before an agent opens the episode.

    freeze = load_freeze()
    modes = {"video_only": (False, False),
             "source_candidate": (True, False),
             "paired_candidates": (True, True)}
    need_source, need_english = modes[args.mode]
    if bool(args.source) != need_source or bool(args.english) != need_english:
        raise ValueError(f"Input paths do not match mode {args.mode}")
    run = args.output.resolve()
    manifest = {
        "version": 1, "episode_id": args.episode_id, "mode": args.mode,
        "freeze_sha256": digest(FREEZE),
        "video": input_record(args.video),
        "source_candidate": input_record(args.source),
        "english_candidate": input_record(args.english),
        "authorization": "no_billable_provider_use",
        "started_at": now(),
    }
    target = run / "run.json"
    if target.exists():
        previous = json.loads(target.read_text(encoding="utf-8"))
        for key in ("episode_id", "mode", "freeze_sha256", "video",
                    "source_candidate", "english_candidate", "authorization"):
            if previous.get(key) != manifest[key]:
                raise ValueError(f"Existing run belongs to different inputs: {run}")
        print(json.dumps({"run": str(run), "resumed": True}, ensure_ascii=False))
        return
    if run.exists():
        raise ValueError(f"Output exists without run.json: {run}")
    run.mkdir(parents=True)
    target.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
                      encoding="utf-8")
    print(json.dumps({"run": str(run), "resumed": False}, ensure_ascii=False))


def event(args):
    # 2. Record interventions and failures as well as completed work.

    run = args.run.resolve(strict=True)
    if not (run / "run.json").is_file():
        raise ValueError("Not a qualification run")
    entry = {"at": now(), "kind": args.kind, "detail": args.detail}
    with (run / "events.jsonl").open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(entry, ensure_ascii=False) + "\n")
        stream.flush()
        os.fsync(stream.fileno())
    print(json.dumps(entry, ensure_ascii=False))


def status(args):
    # 3. Report checkpoint state without interpreting a passed gate as accuracy.

    run = args.run.resolve(strict=True)
    manifest = json.loads((run / "run.json").read_text(encoding="utf-8"))
    freeze_current = digest(FREEZE) == manifest["freeze_sha256"]
    inputs_current = all(
        Path(item["path"]).is_file() and digest(Path(item["path"])) == item["sha256"]
        for item in (manifest["video"], manifest["source_candidate"],
                     manifest["english_candidate"]) if item
    )
    events = []
    if (run / "events.jsonl").exists():
        events = [json.loads(line) for line in
                  (run / "events.jsonl").read_text(encoding="utf-8").splitlines()]
    check_path = run / "episode-check/episode-check.json"
    check = json.loads(check_path.read_text(encoding="utf-8")) if check_path.exists() else None
    summary = {
        "run": str(run), "episode_id": manifest["episode_id"],
        "mode": manifest["mode"], "freeze_current": freeze_current,
        "inputs_current": inputs_current,
        "events": {kind: sum(item["kind"] == kind for item in events)
                   for kind in sorted(EVENT_KINDS)},
        "episode_check_present": check is not None,
        "installation_checks_passed": check.get("installation_checks_passed") if check else None,
        "blockers": check.get("blockers") if check else None,
        "note": "A release gate or agent claim is not an independent accuracy result.",
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    actions = parser.add_subparsers(dest="action", required=True)
    actions.add_parser("verify", help="check pinned workflow and model files")
    starting = actions.add_parser("start", help="start or resume a held-out episode")
    starting.add_argument("episode_id")
    starting.add_argument("mode", choices=["video_only", "source_candidate",
                                           "paired_candidates"])
    starting.add_argument("video", type=Path)
    starting.add_argument("output", type=Path)
    starting.add_argument("--source", type=Path)
    starting.add_argument("--english", type=Path)
    logging = actions.add_parser("event", help="append one run event")
    logging.add_argument("run", type=Path)
    logging.add_argument("kind", choices=sorted(EVENT_KINDS))
    logging.add_argument("detail")
    reporting = actions.add_parser("status", help="show current run checkpoint")
    reporting.add_argument("run", type=Path)
    args = parser.parse_args()
    if args.action == "verify":
        freeze = load_freeze()
        print(json.dumps({"freeze": str(FREEZE), "version": freeze["version"],
                          "verified": True}))
    elif args.action == "start":
        start(args)
    elif args.action == "event":
        event(args)
    else:
        status(args)


if __name__ == "__main__":
    main()
