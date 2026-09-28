#!/bin/bash
DEST="$HOME/Movies/Leyla ile Mecnun/Episodes"
OUT="$HOME/Movies/Leyla ile Mecnun/Workflow/raw-whisper"
MODEL="$HOME/.local/share/transcribe-audio/models/ggml-large-v3.bin"
VAD="$HOME/.local/share/transcribe-audio/models/ggml-silero-v6.2.0.bin"
cd "$DEST" || exit 1
  for f in *.webm; do
    [ -f "$f" ] || continue
    base="${f%.webm}"
    out="$OUT/$base.srt"
    [ -f "$out" ] && continue
    wav="/tmp/leyla-transcribe.wav"
    echo "START $base"
    if ! ffmpeg -y -i "$f" -vn -ac 1 -ar 16000 -c:a pcm_s16le "$wav" -hide_banner -loglevel error; then
      echo "FFMPEG_FAIL $base"
      rm -f "$wav"
      continue
    fi
    if whisper-cli -m "$MODEL" -l tr --vad -vm "$VAD" -osrt -of "$OUT/$base" -f "$wav" --no-prints; then
      echo "DONE $base"
    else
      echo "WHISPER_FAIL $base"
    fi
    rm -f "$wav"
  done
echo "ALL_DONE"
