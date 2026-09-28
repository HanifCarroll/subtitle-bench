"""Add standard-button OpenSubtitles ZIP downloads to this archive."""

import argparse
import csv
import hashlib
import os
import re
import shutil
import zipfile
from pathlib import Path


ROOT = Path(os.environ.get(
    "OPENSUBTITLES_ARCHIVE_DIR",
    Path.home() / "Movies/Leyla ile Mecnun/Workflow/opensubtitles-archive",
))
DOWNLOADS = Path.home() / "Downloads"
MANIFEST = ROOT / "manifest.csv"
INDEX = ROOT / "listing-index.csv"
ZIP_ID = re.compile(r"\((\d+)\)\.zip$")


def main():
    # 1. Match downloaded ZIPs to the indexed subtitle IDs.

    with INDEX.open(newline="") as stream:
        reader = csv.DictReader(stream)
        index_fields = reader.fieldnames
        listings = list(reader)

    by_id = {row["opensubtitles_id"]: row for row in listings}
    with MANIFEST.open(newline="") as stream:
        reader = csv.DictReader(stream)
        manifest_fields = reader.fieldnames
        saved = list(reader)

    saved_ids = {row["opensubtitles_id"] for row in saved}
    added = 0

    # 2. Validate each new archive and retain its original ZIP and SRT bytes.

    for source in sorted(DOWNLOADS.glob("*.zip")):
        match = ZIP_ID.search(source.name)
        if not match or match.group(1) not in by_id or match.group(1) in saved_ids:
            continue

        listing = by_id[match.group(1)]
        with zipfile.ZipFile(source) as archive:
            if archive.testzip() is not None:
                raise ValueError(f"Damaged ZIP: {source.name}")

            subtitle_names = [name for name in archive.namelist() if name.lower().endswith(".srt")]
            if len(subtitle_names) != 1:
                raise ValueError(f"Expected one SRT in {source.name}")

            subtitle = archive.read(subtitle_names[0])

        if b"-->" not in subtitle[:1000]:
            raise ValueError(f"Invalid SRT in {source.name}")

        number = int(listing["overall_episode"])
        language = listing["language"]
        subtitle_id = listing["opensubtitles_id"]
        folder = ROOT / f"{number:03d}"
        folder.mkdir(exist_ok=True)
        base = f"{number:03d}.{language}.opensubtitles-{subtitle_id}"
        subtitle_path = folder / f"{base}.srt"
        zip_path = folder / f"{base}.zip"
        if subtitle_path.exists() or zip_path.exists():
            raise FileExistsError(base)

        subtitle_path.write_bytes(subtitle)
        shutil.copy2(source, zip_path)
        saved.append({
            "overall_episode": number,
            "site_season": listing["site_season"],
            "site_episode": listing["site_episode"],
            "language": language,
            "opensubtitles_id": subtitle_id,
            "release": listing["release"],
            "source_url": f"https://www.opensubtitles.org/en/subtitles/{subtitle_id}",
            "download_status": "saved",
            "subtitle_file": subtitle_path.relative_to(ROOT).as_posix(),
            "zip_file": zip_path.relative_to(ROOT).as_posix(),
            "sha256_srt": hashlib.sha256(subtitle).hexdigest(),
        })
        listing["archive_status"] = "saved"
        listing["subtitle_file"] = subtitle_path.relative_to(ROOT).as_posix()
        saved_ids.add(subtitle_id)
        added += 1

    # 3. Record only files that passed validation.

    with MANIFEST.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=manifest_fields)
        writer.writeheader()
        writer.writerows(saved)

    with INDEX.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=index_fields)
        writer.writeheader()
        writer.writerows(listings)

    print(f"Archived {added} browser downloads; {len(saved)} files total")


if __name__ == "__main__":
    argparse.ArgumentParser(description=__doc__).parse_args()
    main()
