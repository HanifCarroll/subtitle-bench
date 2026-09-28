#!/bin/zsh
set -euo pipefail

ROOT="/Users/hanifcarroll/Movies/Leyla ile Mecnun/Workflow"
PYTHON="/Users/hanifcarroll/.cache/leyla-whisperx-venv/bin/python"
SCRIPTS="$ROOT/scripts"
STATUS="$ROOT/pilots/overnight-subtitles-status.txt"

finish() {
  local result=$?
  if (( result != 0 )); then
    echo "Failed with exit code $result; $(date)" > "$STATUS"
  fi
}
trap finish EXIT

echo "Running alignment workers; $(date)" > "$STATUS"
while pgrep -f "$SCRIPTS/align-episodes.py" >/dev/null; do
  sleep 30
done

# 1. Complete any episodes left by a failed or interrupted worker.

REPORTS="$ROOT/pilots/whisperx-candidates"
REPORT_COUNT=$(find "$REPORTS" -maxdepth 1 -name '???-report.json' | wc -l)
if (( REPORT_COUNT < 104 )); then
  "$PYTHON" "$SCRIPTS/align-episodes.py" --all
fi

# 2. Normalize and check all paired timing candidates.

"$PYTHON" "$SCRIPTS/finalize-alignment.py"
"$PYTHON" "$SCRIPTS/repair-episode-071.py"
"$PYTHON" "$SCRIPTS/promote-aligned-subtitles.py"

# 3. Preserve current sidecars, then install all validated candidates.

"$PYTHON" "$SCRIPTS/promote-aligned-subtitles.py" --apply
echo "Complete; $(date)" > "$STATUS"
