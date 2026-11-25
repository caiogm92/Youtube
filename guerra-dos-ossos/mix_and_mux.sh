#!/usr/bin/env bash
# Abaixa a cama sonora sob a narração (ducking), normaliza em -14 LUFS e gera MP4 H.264/AAC (CRF 24).
# uso: ./mix_and_mux.sh video.mp4 narracao.(mp3|wav|none) sound_bed.wav saida.mp4
set -euo pipefail
VID="$1"; NAR="$2"; BED="$3"; OUT="$4"
if [ "$NAR" = "none" ]; then
  # prévia sem narração: só a cama sonora, mais baixa
  ffmpeg -y -loglevel error -i "$VID" -i "$BED" -filter_complex \
   "[1:a]loudnorm=I=-20:TP=-2:LRA=11[a]" -map 0:v -map "[a]" -c:v libx264 -preset slow -crf 24 \
   -pix_fmt yuv420p -c:a aac -b:a 192k -ar 48000 -shortest -movflags +faststart "$OUT"
else
  ffmpeg -y -loglevel error -i "$VID" -i "$NAR" -i "$BED" -filter_complex \
   "[1:a]aresample=48000,aformat=channel_layouts=stereo,asplit=2[n1][n2];\
    [2:a]volume=0.55[bed];\
    [bed][n1]sidechaincompress=threshold=0.03:ratio=8:attack=20:release=450:makeup=1[duck];\
    [duck][n2]amix=inputs=2:duration=first:normalize=0,loudnorm=I=-14:TP=-1.5:LRA=11[a]" \
   -map 0:v -map "[a]" -c:v libx264 -preset slow -crf 24 -pix_fmt yuv420p -c:a aac -b:a 192k -ar 48000 \
   -shortest -movflags +faststart "$OUT"
fi
echo "-> $OUT"
