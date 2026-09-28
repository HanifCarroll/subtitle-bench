# OpenSubtitles archive helpers

These scripts maintain the local OpenSubtitles reference archive. The inventory, manifest, downloaded subtitle files, ZIPs, and mode-0600 `.env` remain in `~/Movies/Leyla ile Mecnun/Workflow/opensubtitles-archive`; none are versioned here. Set `OPENSUBTITLES_ARCHIVE_DIR` if that workspace moves.

`api_inventory.py` and `api_download.py` use the official API. `archive_browser_downloads.py` imports ZIPs already obtained through the site's standard button. API downloads consume the account's daily allowance; run them only when authorized. These files are reference candidates, not reviewed playback subtitles.
