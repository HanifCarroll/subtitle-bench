"""Save available OpenSubtitles files within today's free account quota."""

import argparse
import csv
import hashlib
import json
import os
import stat
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path


ROOT = Path(os.environ.get(
    "OPENSUBTITLES_ARCHIVE_DIR",
    Path.home() / "Movies/Leyla ile Mecnun/Workflow/opensubtitles-archive",
))
MANIFEST = ROOT / "manifest.csv"
INDEX = ROOT / "listing-index.csv"
INVENTORY = ROOT / "api-inventory.json"
ENV_FILE = ROOT / ".env"
DOWNLOAD_URL = "https://api.opensubtitles.com/api/v1/download"
MAX_DOWNLOADS = 20
MAX_FAILED_FILES = 3
LOGIN_URL = "https://api.opensubtitles.com/api/v1/login"


def account_credentials():
    if stat.S_IMODE(ENV_FILE.stat().st_mode) != 0o600:
        raise ValueError("OpenSubtitles .env permissions must be 0600")

    fields = {}
    for line in ENV_FILE.read_text().splitlines():
        if not line or line.startswith("#"):
            continue

        name, separator, value = line.partition("=")
        if not separator:
            raise ValueError("Invalid OpenSubtitles .env entry")
        fields[name] = json.loads(value)

    username = fields.get("OPENSUBTITLES_USERNAME")
    password = fields.get("OPENSUBTITLES_PASSWORD")
    api_key = fields.get("OPENSUBTITLES_API_KEY")
    if not username or not password or not api_key:
        raise ValueError("OpenSubtitles credentials are incomplete in .env")

    return username, password, api_key


def login(username, password, api_key):
    request = urllib.request.Request(
        LOGIN_URL,
        data=json.dumps({"username": username, "password": password}).encode(),
        headers={
            "Api-Key": api_key,
            "User-Agent": "LeylaArchive2026 v1",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        result = json.load(response)

    if result.get("base_url") != "api.opensubtitles.com" or not result.get("token"):
        raise ValueError("Unexpected OpenSubtitles login response")

    return result["token"]


def overall_episode(season, episode):
    return {1: 0, 2: 20, 3: 61}[season] + episode


def ordered_candidates(entries, listings, existing):
    saved_tracks = {
        (int(row["overall_episode"]), row["language"])
        for row in existing if row["download_status"] == "saved"
    }
    saved_ids = {
        row["opensubtitles_id"]
        for row in existing if row["download_status"] == "saved"
    }
    pending_ids = {
        row["opensubtitles_id"]
        for row in listings
        if row["archive_status"] == "not_downloaded"
        and row["opensubtitles_id"] not in saved_ids
    }
    candidates = []
    for entry in entries:
        attributes = entry["attributes"]
        legacy_id = str(attributes.get("legacy_subtitle_id") or "")
        if legacy_id not in pending_ids or attributes["language"] not in ("en", "tr"):
            continue

        feature = attributes["feature_details"]
        number = overall_episode(feature["season_number"], feature["episode_number"])
        if not 1 <= number <= 104:
            continue

        other_language = "tr" if attributes["language"] == "en" else "en"
        completes_pair = (number, other_language) in saved_tracks
        candidates.append((not completes_pair, number, attributes["language"], entry))

    candidates.sort(key=lambda item: item[:3])
    return [(number, entry) for _, number, _, entry in candidates]


def save_index(listings, fieldnames):
    with INDEX.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(listings)


def record_failure(listings, fieldnames, legacy_id, reason):
    for listing in listings:
        if listing["opensubtitles_id"] == str(legacy_id):
            listing["last_download_error"] = reason
            break

    save_index(listings, fieldnames)
    print(f"Skipped {legacy_id}: {reason}", flush=True)


def download_link(api_key, token, file_id):
    payload = json.dumps({"file_id": file_id}).encode()
    request = urllib.request.Request(
        DOWNLOAD_URL,
        data=payload,
        headers={
            "Api-Key": api_key,
            "Authorization": f"Bearer {token}",
            "User-Agent": "LeylaArchive2026 v1",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        method="POST",
    )

    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)["link"]


def fetch_subtitle(link):
    parsed = urllib.parse.urlparse(link)
    if parsed.scheme != "https" or not parsed.hostname.endswith(".opensubtitles.com"):
        raise ValueError("Unexpected download host")

    quoted_link = link.replace("\\", "\\\\").replace('"', '\\"')
    result = subprocess.run(
        ["curl", "--config", "-", "--fail", "--silent", "--show-error", "--location", "--max-time", "60"],
        input=f'url = "{quoted_link}"\n'.encode(),
        capture_output=True,
        check=False,
    )
    if result.returncode:
        raise ValueError(f"Subtitle transfer failed (curl {result.returncode})")

    content = result.stdout

    if not content or content.startswith(b"PK\x03\x04") or b"-->" not in content[:1000]:
        raise ValueError("Unexpected subtitle response")

    return content


def main():
    entries = json.loads(INVENTORY.read_text())
    with MANIFEST.open(newline="") as stream:
        reader = csv.DictReader(stream)
        fieldnames = reader.fieldnames
        existing = list(reader)

    with INDEX.open(newline="") as stream:
        reader = csv.DictReader(stream)
        index_fields = reader.fieldnames
        listings = list(reader)

    if "last_download_error" not in index_fields:
        index_fields.append("last_download_error")
        for listing in listings:
            listing["last_download_error"] = ""

    candidates = ordered_candidates(entries, listings, existing)
    username, password, api_key = account_credentials()
    try:
        token = login(username, password, api_key)
    except urllib.error.HTTPError as error:
        print(f"OpenSubtitles login failed: HTTP {error.code}")
        return
    except (urllib.error.URLError, ValueError) as error:
        print(f"OpenSubtitles login failed: {type(error).__name__}")
        return
    downloaded = 0
    failed_files = 0

    for number, entry in candidates:
        if downloaded >= MAX_DOWNLOADS or failed_files >= MAX_FAILED_FILES:
            break

        attributes = entry["attributes"]
        feature = attributes["feature_details"]
        language = attributes["language"]
        legacy_id = int(attributes["legacy_subtitle_id"])
        files = attributes.get("files") or []
        if len(files) != 1:
            record_failure(listings, index_fields, legacy_id, "expected one API file")
            failed_files += 1
            continue

        relative_path = f"{number:03d}/{number:03d}.{language}.opensubtitles-{legacy_id}.srt"
        destination = ROOT / relative_path
        if destination.exists():
            record_failure(listings, index_fields, legacy_id, "destination already exists outside manifest")
            failed_files += 1
            continue

        try:
            link = download_link(api_key, token, files[0]["file_id"])
            content = fetch_subtitle(link)
        except urllib.error.HTTPError as error:
            if error.code == 401:
                try:
                    token = login(username, password, api_key)
                    link = download_link(api_key, token, files[0]["file_id"])
                    content = fetch_subtitle(link)
                except (urllib.error.HTTPError, urllib.error.URLError, ValueError, KeyError) as retry_error:
                    reason = f"HTTP {retry_error.code}" if isinstance(retry_error, urllib.error.HTTPError) else type(retry_error).__name__
                    record_failure(listings, index_fields, legacy_id, f"fresh login failed: {reason}")
                    break
            elif error.code == 406:
                print(f"Free daily allowance exhausted at {legacy_id}", flush=True)
                break
            else:
                record_failure(listings, index_fields, legacy_id, f"HTTP {error.code}")
                failed_files += 1
                continue
        except ValueError as error:
            record_failure(listings, index_fields, legacy_id, str(error))
            failed_files += 1
            continue
        except (urllib.error.URLError, KeyError) as error:
            record_failure(listings, index_fields, legacy_id, type(error).__name__)
            failed_files += 1
            continue

        directory = ROOT / f"{number:03d}"
        directory.mkdir(exist_ok=True)

        destination.write_bytes(content)
        row = {
            "overall_episode": number,
            "site_season": feature["season_number"],
            "site_episode": feature["episode_number"],
            "language": language,
            "opensubtitles_id": legacy_id,
            "release": attributes.get("release", ""),
            "source_url": attributes.get("url", ""),
            "download_status": "saved",
            "subtitle_file": relative_path,
            "zip_file": "",
            "sha256_srt": hashlib.sha256(content).hexdigest(),
        }
        existing.append(row)
        with MANIFEST.open("w", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(existing)

        for listing in listings:
            if listing["opensubtitles_id"] == str(legacy_id):
                listing["archive_status"] = "saved"
                listing["subtitle_file"] = relative_path
                listing["last_download_error"] = ""
                break

        save_index(listings, index_fields)

        downloaded += 1
        print(f"Saved {number:03d} {language} {legacy_id} ({downloaded}/{MAX_DOWNLOADS})", flush=True)
        time.sleep(2)

    print(f"Finished with {downloaded} new files and {failed_files} skipped failures", flush=True)


if __name__ == "__main__":
    argparse.ArgumentParser(description=__doc__).parse_args()
    main()
