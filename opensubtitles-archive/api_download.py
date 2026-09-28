"""Save available OpenSubtitles files within today's free account quota."""

import argparse
import csv
import hashlib
import json
import os
import stat
import subprocess
import sys
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
LOGIN_URL = "https://api.opensubtitles.com/api/v1/login"
# These September 27 transfers failed; retry them after the other pending files.
DEFERRED_IDS = {8658872, 8661745, 8661763}


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

    saved_ids = {int(row["opensubtitles_id"]) for row in existing if row["download_status"] == "saved"}
    candidates = []
    for entry in entries:
        attributes = entry["attributes"]
        feature = attributes["feature_details"]
        legacy_id = attributes.get("legacy_subtitle_id")
        if not legacy_id or int(legacy_id) in saved_ids or str(legacy_id) in sys.argv[1:]:
            continue

        candidates.append((
            1 if int(legacy_id) in DEFERRED_IDS else 0,
            0 if attributes["language"] == "en" else 1,
            overall_episode(feature["season_number"], feature["episode_number"]),
            entry,
        ))

    candidates.sort(key=lambda item: (item[0], item[1], item[2]))
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

    for _, _, number, entry in candidates:
        if downloaded >= MAX_DOWNLOADS:
            break

        attributes = entry["attributes"]
        feature = attributes["feature_details"]
        language = attributes["language"]
        legacy_id = int(attributes["legacy_subtitle_id"])
        files = attributes.get("files") or []
        if len(files) != 1:
            print(f"Skipped {legacy_id}: expected one file")
            continue

        try:
            link = download_link(api_key, token, files[0]["file_id"])
            content = fetch_subtitle(link)
        except urllib.error.HTTPError as error:
            body = error.read().decode("utf-8", errors="replace")
            safe_body = body.replace(api_key, "[redacted]").replace(token, "[redacted]")
            print(f"Stopped at {legacy_id}: HTTP {error.code} {safe_body[:300]}")
            break
        except ValueError as error:
            print(f"Stopped at {legacy_id}: {error}")
            break
        except (urllib.error.URLError, KeyError) as error:
            print(f"Stopped at {legacy_id}: {type(error).__name__}")
            break

        directory = ROOT / f"{number:03d}"
        directory.mkdir(exist_ok=True)
        relative_path = f"{number:03d}/{number:03d}.{language}.opensubtitles-{legacy_id}.srt"
        destination = ROOT / relative_path
        if destination.exists():
            print(f"Stopped at {legacy_id}: destination already exists")
            break

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
                break

        with INDEX.open("w", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=index_fields)
            writer.writeheader()
            writer.writerows(listings)

        downloaded += 1
        print(f"Saved {number:03d} {language} {legacy_id} ({downloaded}/{MAX_DOWNLOADS})", flush=True)
        time.sleep(2)

    print(f"Finished with {downloaded} new files", flush=True)


if __name__ == "__main__":
    argparse.ArgumentParser(description=__doc__).parse_args()
    main()
