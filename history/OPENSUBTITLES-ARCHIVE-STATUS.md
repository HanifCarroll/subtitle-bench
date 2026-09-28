# OpenSubtitles source archive

Collected starting 2026-09-26 for the original 104 episodes of *Leyla ile Mecnun* (site seasons 1–3). These are reference subtitles, not reviewed or installed playback files. Video and existing sidecars were untouched.

## Inventory and files

- `api-inventory.json`: the complete response data for an authenticated [OpenSubtitles.com API](https://api.opensubtitles.com/api/v1/subtitles) search using parent IMDb ID `1831164` and languages `en,tr` (five pages, 207 listings).
- `listing-index.csv`: one row per API listing, with episode, language, release, site and API IDs, source URL, and saved/pending status.
- `manifest.csv`: one row per saved SRT, with relative path and SHA-256 digest.
- Numbered folders: saved SRTs. The three files collected through the legacy site's standard **Download** button also retain their original ZIPs. **Download (beta)** was never used.
- `api_inventory.py` inventories the official API; `api_download.py` reads the local `.env`, signs in for a fresh API token, stops at the free daily limit, and gives English files priority because Turkish working subtitles already exist elsewhere. `archive_browser_downloads.py` validates ZIPs saved through the standard browser button and adds them to the archive. None of these scripts alters working subtitle files.
- `.env` contains the OpenSubtitles username, password, and API key in JSON-quoted dotenv values. It is local, mode `0600`, and must never be shared or added to a repository. The short-lived API token is not saved. The key was removed from the 1Password item after migration to `.env`.

The API returned 104 Turkish and 103 English listings. It has no English listing for site S01E04 (overall episode 4). It returned one listing per other episode and language, so no alternate release was found within this API query. Listings outside the series' structured API association, including any unclassified legacy-site entries, are not proven absent.

## Status

**Partial as of 2026-09-28:** 87 of the 207 API-listed files are saved and hash-verified: 29 through the legacy site's standard Download button and 58 through the official API. The other 120 listings are indexed but not downloaded. On September 28, the free **20 / 20** daily allowance produced 20 saved English files, overall episodes 46–65. The API reports zero remaining downloads and the next quota reset at 2026-09-28 23:59:59 UTC. No paid plan or call was used.

On September 27, the free **20 / 20** allowance produced 18 saved files; transfers for IDs `8658872` and `8661763` consumed slots without producing files. ID `8661745` returned HTTP 500 without consuming a slot. These three listings remain pending and are ordered after the others for a later retry. The earlier browser CAPTCHA and blocked-download attempts did not add files.

After the API allowance ran out, the OpenSubtitles.com **Download SRT** button for episode 46 reported that the same 20-per-24-hour allowance was exhausted. The legacy site's standard **Download** button for episodes 46 and 47 produced no local file; its redirects led to the `.com` download page or a CAPTCHA page that the browser could not load. No **Download (beta)** button was used. Browser downloads did not change the archive count.

The publisher [directs automated collection to its official API](https://github.com/LavX/opensubtitles-scraper/issues/9); the legacy site's robots rules exclude download routes. No bulk legacy-site crawl was run.
