#!/usr/bin/env bash
# Junta os blocos de vídeo renderizados com a mixagem final.
set -euo pipefail
cd "$(dirname "$0")"
mkdir -p output
# master para YouTube: H.264 1080p30, ~12 Mbps, AAC 320k
ffmpeg -v error -y -f concat -safe 0 -i build/chunks_full/list.txt -i build/mix.wav \
  -map 0:v -map 1:a -c:v libx264 -preset slow -b:v 12M -maxrate 16M -bufsize 24M -tune grain \
  -pix_fmt yuv420p -movflags +faststart -c:a aac -b:a 320k -shortest \
  output/Santos_FC_O_Eterno_Gigante_1080p.mp4
# versão leve para revisão no celular
ffmpeg -v error -y -i output/Santos_FC_O_Eterno_Gigante_1080p.mp4 -vf scale=1280:720 \
  -c:v libx264 -preset medium -crf 25 -c:a aac -b:a 160k -movflags +faststart \
  output/Santos_FC_O_Eterno_Gigante_720p_revisao.mp4
ls -la output
