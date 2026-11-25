#!/usr/bin/env bash
# Substitui um intervalo de frames do vídeo do quadro por um insert vintage 2D.
# uso: ./splice.sh board.mp4 insert.mp4 FRAME_INICIAL saida.mp4
set -euo pipefail
BOARD="$1"; INS="$2"; F0="$3"; OUT="$4"
N=$(ffprobe -v error -count_frames -select_streams v:0 -show_entries stream=nb_read_frames -of csv=p=0 "$INS")
F1=$((F0 + N))
ffmpeg -y -loglevel error -i "$BOARD" -i "$INS" -filter_complex \
 "[0:v]trim=start_frame=0:end_frame=${F0},setpts=PTS-STARTPTS[a];\
  [1:v]setpts=PTS-STARTPTS,fps=30[b];\
  [0:v]trim=start_frame=${F1},setpts=PTS-STARTPTS[c];\
  [a][b][c]concat=n=3:v=1:a=0[v]" -map "[v]" -c:v libx264 -preset medium -crf 17 -pix_fmt yuv420p "$OUT"
echo "emenda: frames ${F0}–${F1} <- $(basename "$INS") -> $OUT"
