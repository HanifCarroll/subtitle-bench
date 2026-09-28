#!/usr/bin/env python3
"""Compare every source cue with an English draft using Google NMT."""

import argparse
import hashlib
import html
import json
import os
import runpy
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path


READ_CUES = runpy.run_path(str(Path(__file__).with_name("subtitle-timing.py")))["read_cues"]
GOOGLE_URL = "https://translation.googleapis.com/language/translate/v2"
MAX_BATCH_CUES = 100
MAX_BATCH_CHARACTERS = 5_000


def file_hash(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save_json(path, value):
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def aligned_cues(source, draft):
    source_cues = READ_CUES(source)
    draft_cues = READ_CUES(draft)
    if len(source_cues) != len(draft_cues):
        raise ValueError("Source and English draft need matching cue counts")

    for original, translated in zip(source_cues, draft_cues):
        if (original["start"], original["end"]) != (translated["start"], translated["end"]):
            raise ValueError(f"English draft timing differs at cue {original['id']}")

    return source_cues, draft_cues


def batches(cues):
    current = []
    characters = 0
    for cue in cues:
        length = len(cue["text"])
        if length > MAX_BATCH_CHARACTERS:
            raise ValueError(f"Cue {cue['id']} exceeds the Google request limit")
        if current and (len(current) == MAX_BATCH_CUES or
                        characters + length > MAX_BATCH_CHARACTERS):
            yield current
            current = []
            characters = 0

        current.append(cue)
        characters += length

    if current:
        yield current


def google_project(override):
    if override:
        return override

    credentials = Path.home() / ".config/gcloud/application_default_credentials.json"
    project = json.loads(credentials.read_text(encoding="utf-8")).get("quota_project_id")
    if not project:
        raise ValueError("Google ADC needs a quota project; pass --google-project")

    return project


def google_translate(cues, language, project):
    # 1. Get a short-lived ADC token without sending it through command arguments.

    token = subprocess.run(
        ["gcloud", "auth", "application-default", "print-access-token"],
        check=True, capture_output=True, text=True, timeout=30,
    ).stdout.strip()
    if not token:
        raise RuntimeError("Google ADC did not return an access token")

    # 2. Translate each cue independently, preserving Google's response order.

    body = {"q": [cue["text"] for cue in cues], "source": language,
            "target": "en", "format": "text"}
    request = urllib.request.Request(
        GOOGLE_URL, data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json",
                 "Authorization": f"Bearer {token}", "x-goog-user-project": project},
    )
    try:
        with urllib.request.urlopen(request, timeout=90) as response:
            translations = json.load(response)["data"]["translations"]
    except urllib.error.HTTPError as error:
        raise RuntimeError(f"Google NMT request failed: HTTP {error.code}") from None

    if len(translations) != len(cues):
        raise ValueError("Google returned the wrong number of cues")

    texts = []
    for translation in translations:
        value = html.unescape(translation["translatedText"]).strip()
        if not value or "\x00" in value:
            raise ValueError("Google returned an empty or invalid cue")
        texts.append(value)

    return texts


def review_report(source, draft, source_cues, draft_cues, translations, settings, seconds):
    rows = []
    for original, english in zip(source_cues, draft_cues):
        rows.append({
            "id": original["id"], "start_ms": original["start"],
            "end_ms": original["end"], "source": original["text"],
            "english_draft": english["text"],
            "google_nmt": translations[str(original["id"])],
            "review_status": "unreviewed",
        })

    windows = {}
    for row in rows:
        window = row["start_ms"] // 300_000 + 1
        windows.setdefault(window, []).append(row["id"])

    return {
        **settings, "source": str(source), "source_sha256": file_hash(source),
        "english_draft": str(draft), "english_draft_sha256": file_hash(draft),
        "cues": len(rows), "request_seconds": seconds,
        "windows": [{"id": number, "start_ms": (number - 1) * 300_000,
                     "end_ms": number * 300_000, "cue_ids": ids}
                    for number, ids in sorted(windows.items())],
        "rows": rows,
        "review_instruction": (
            "Review every five-minute window against the source. Resolve meaning "
            "conflicts; check video audio when the source words are uncertain. "
            "Neither translation automatically wins. This report is not a review receipt."
        ),
    }


def run(args):
    # 1. Validate the two inputs and calculate the complete paid request size.

    source = args.source.resolve(strict=True)
    draft = args.english_draft.resolve(strict=True)
    output = args.output.resolve()
    if (source == draft or output in (source, draft) or output.suffix.lower() != ".json"):
        raise ValueError("Use separate source, English draft, and .json report paths")
    if not args.source_language.isalpha() or not 2 <= len(args.source_language) <= 8:
        raise ValueError("Use a source-language code such as tr")
    if output.exists():
        raise FileExistsError(f"Review report already exists: {output}")

    source_cues, draft_cues = aligned_cues(source, draft)
    planned_batches = list(batches(source_cues))
    characters = sum(len(cue["text"]) for cue in source_cues)
    plan = {"cues": len(source_cues), "requests": len(planned_batches),
            "source_characters_sent": characters, "provider": "google-nmt"}
    if not args.run:
        print(json.dumps({**plan, "status": "dry_run"}))
        return

    if args.max_source_characters is None or characters > args.max_source_characters:
        raise ValueError("Live Google run needs --max-source-characters covering the full input")

    # 2. Resume only a checkpoint bound to these exact files and settings.

    output.parent.mkdir(parents=True, exist_ok=True)
    project = google_project(args.google_project)
    settings = {"provider": "google-nmt", "source_language": args.source_language.lower(),
                "target_language": "en", "google_project": project,
                "source_sha256": file_hash(source), "english_draft_sha256": file_hash(draft)}
    progress_path = output.with_suffix(".progress.json")
    progress = (json.loads(progress_path.read_text(encoding="utf-8"))
                if progress_path.exists() else {**settings, "translations": {}, "request_seconds": []})
    if any(progress.get(key) != value for key, value in settings.items()):
        raise ValueError("Google checkpoint belongs to different inputs or settings")
    expected_ids = {str(cue["id"]) for cue in source_cues}
    if (not isinstance(progress.get("translations"), dict)
            or not set(progress["translations"]).issubset(expected_ids)
            or any(not isinstance(value, str) or not value.strip()
                   for value in progress["translations"].values())):
        raise ValueError("Google checkpoint contains unknown cue IDs")

    # 3. Save every complete request before making the next paid request.

    for group in planned_batches:
        ids = [str(cue["id"]) for cue in group]
        if all(cue_id in progress["translations"] for cue_id in ids):
            continue
        if any(cue_id in progress["translations"] for cue_id in ids):
            raise ValueError("Google checkpoint contains a partial request")

        started = time.monotonic()
        translated = google_translate(group, args.source_language.lower(), project)
        progress["translations"].update(zip(ids, translated))
        progress["request_seconds"].append(round(time.monotonic() - started, 3))
        save_json(progress_path, progress)
        print(f"checked {len(progress['translations'])}/{len(source_cues)} cues", flush=True)

    # 4. Produce a review-only report; never edit the English draft.

    if set(progress["translations"]) != expected_ids:
        raise ValueError("Google second opinion is incomplete")
    if (file_hash(source) != settings["source_sha256"] or
            file_hash(draft) != settings["english_draft_sha256"]):
        raise ValueError("Subtitle inputs changed during the Google run")

    report = review_report(source, draft, source_cues, draft_cues,
                           progress["translations"], settings,
                           round(sum(progress["request_seconds"]), 3))
    save_json(output, report)
    progress_path.unlink()
    print(json.dumps({**plan, "status": "needs_review", "report": str(output)}))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("english_draft", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--source-language", required=True)
    parser.add_argument("--google-project")
    parser.add_argument("--run", action="store_true", help="make paid Google NMT calls")
    parser.add_argument("--max-source-characters", type=int,
                        help="explicit cap on total source characters sent")
    run(parser.parse_args())


if __name__ == "__main__":
    main()
