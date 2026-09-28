"""Inventory OpenSubtitles results for the original Leyla ile Mecnun series."""

import argparse
import getpass
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path


ROOT = Path(os.environ.get(
    "OPENSUBTITLES_ARCHIVE_DIR",
    Path.home() / "Movies/Leyla ile Mecnun/Workflow/opensubtitles-archive",
))
BASE = "https://api.opensubtitles.com/api/v1/subtitles"


def request_page(api_key, token, page):
    query = urllib.parse.urlencode(
        {"parent_imdb_id": 1831164, "languages": "en,tr", "page": page}
    )
    headers = {
        "Api-Key": api_key,
        "Authorization": f"Bearer {token}",
        "User-Agent": "LeylaArchive2026 v1",
        "Accept": "application/json",
    }
    request = urllib.request.Request(f"{BASE}?{query}", headers=headers)

    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)


def main():
    api_key = getpass.getpass("API key: ")
    token = getpass.getpass("API token: ")
    entries = []
    page = 1

    while True:
        try:
            result = request_page(api_key, token, page)
        except urllib.error.HTTPError as error:
            body = error.read().decode("utf-8", errors="replace")
            safe_body = body.replace(api_key, "[redacted]").replace(token, "[redacted]")
            print(f"OpenSubtitles HTTP {error.code}: {safe_body[:300]}", file=sys.stderr)
            raise SystemExit(1)
        entries.extend(result.get("data", []))
        total_pages = result.get("total_pages", 1)
        print(f"Page {page}/{total_pages}: {len(result.get('data', []))} entries")

        if page >= total_pages:
            break

        page += 1

    destination = ROOT / "api-inventory.json"
    destination.write_text(json.dumps(entries, ensure_ascii=False, indent=2) + "\n")
    print(f"Saved {len(entries)} listings to {destination}")


if __name__ == "__main__":
    argparse.ArgumentParser(description=__doc__).parse_args()
    try:
        main()
    except urllib.error.URLError as error:
        print(f"OpenSubtitles connection failed: {error.reason}", file=sys.stderr)
        raise SystemExit(1)
