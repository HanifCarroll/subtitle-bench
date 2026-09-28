#!/bin/zsh
set -euo pipefail

ROOT='/Users/hanifcarroll/Movies/Leyla ile Mecnun'
VIDEO="$ROOT/Episodes/069 - Leyla ile Mecnun 69. Bölüm.webm"
OUTPUT="$ROOT/Workflow/pilots/english-reading/069-large-v3-chunks"
MODEL='/Users/hanifcarroll/.local/share/transcribe-audio/models/ggml-large-v3.bin'
VAD='/Users/hanifcarroll/.local/share/transcribe-audio/models/ggml-silero-v6.2.0.bin'
mkdir -p "$OUTPUT"

# 1. Transcribe overlapping five-minute clips so a loop cannot spread across the episode.

for chunk in {0..17}; do
  first=$(( chunk * 300 ))
  begin=$(( first > 0 ? first - 2 : 0 ))
  name=$(printf '%02d' "$chunk")
  path="$OUTPUT/$name"
  if [[ -s "$path.srt" ]]; then
    echo "cached $name"
    continue
  fi

  /opt/homebrew/bin/ffmpeg -y -ss "$begin" -t 304 -i "$VIDEO" -vn -ac 1 -ar 16000 -c:a pcm_s16le "$path.wav" -hide_banner -loglevel error
  /opt/homebrew/bin/whisper-cli -m "$MODEL" -l tr --vad -vm "$VAD" -osrt -of "$path" -f "$path.wav" --no-prints > "$path.log" 2>&1
  [[ -s "$path.srt" ]]
  /bin/rm "$path.wav"
  echo "done $name"
done
