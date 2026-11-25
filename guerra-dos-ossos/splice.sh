#!/usr/bin/env bash
# Substitui intervalos de frames do vídeo do quadro por inserts vintage 2D (baixo uso de memória:
# cada trecho é cortado numa passada própria e tudo é unido pelo concat demuxer).
# uso: ./splice.sh board.mp4 saida.mp4 insert1.mp4 FRAME_INICIAL_1 [insert2.mp4 FRAME_INICIAL_2 ...]
set -euo pipefail
BOARD="$1"; OUT="$2"; shift 2
TMP="$(dirname "$OUT")/splice_tmp"; rm -rf "$TMP"; mkdir -p "$TMP"
TOTAL=$(ffprobe -v error -count_packets -select_streams v:0 -show_entries stream=nb_read_packets -of csv=p=0 "$BOARD")
ENC=(-c:v libx264 -preset medium -crf 17 -pix_fmt yuv420p -r 30 -video_track_timescale 15360)
cur=0; k=0; : > "$TMP/list.txt"
cut_board() {  # $1=início $2=fim (exclusivo)
  [ "$2" -le "$1" ] && return
  ffmpeg -y -loglevel error -i "$BOARD" -vf "trim=start_frame=$1:end_frame=$2,setpts=PTS-STARTPTS" -an "${ENC[@]}" "$TMP/seg_$k.mp4"
  echo "file 'seg_$k.mp4'" >> "$TMP/list.txt"; k=$((k+1))
}
while [ $# -gt 0 ]; do
  INS="$1"; F0="$2"; shift 2
  N=$(ffprobe -v error -count_packets -select_streams v:0 -show_entries stream=nb_read_packets -of csv=p=0 "$INS")
  cut_board "$cur" "$F0"
  ffmpeg -y -loglevel error -i "$INS" -vf "setpts=PTS-STARTPTS" -an "${ENC[@]}" "$TMP/seg_$k.mp4"
  echo "file 'seg_$k.mp4'" >> "$TMP/list.txt"; k=$((k+1))
  echo "insert $(basename "$INS"): frames $F0–$((F0+N))"
  cur=$((F0+N))
done
cut_board "$cur" "$TOTAL"
ffmpeg -y -loglevel error -f concat -safe 0 -i "$TMP/list.txt" -c copy "$OUT"
rm -rf "$TMP"
echo "-> $OUT"
