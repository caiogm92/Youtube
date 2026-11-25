#!/usr/bin/env bash
# Pipeline completo. uso: ./make_all.sh [narracao.mp3]   (sem argumento = prévia com timeline estimada, sem voz)
set -euo pipefail
cd "$(dirname "$0")"
NAR="${1:-none}"
if [ "$NAR" = "none" ]; then python3 align_timing.py --estimate; else python3 align_timing.py "$NAR"; fi
python3 board_engine.py beats > /dev/null
python3 board_engine.py sheet                 # folha de contato para QA visual (build/contact_sheet.jpg)
python3 board_engine.py render --workers "$(nproc)"
python3 vintage_engine.py render
python3 board_engine.py cues
python3 sound_bed.py
python3 - <<'PY'
import json, math, subprocess
m = json.load(open('build/render_meta.json')); src = 'build/board.mp4'
for i, (k, a, b) in enumerate(m['inserts']):
    out = f'build/spliced_{i}.mp4'
    subprocess.run(['./splice.sh', src, f'build/vintage_{k}.mp4', str(math.ceil(a * 30)), out], check=True); src = out
subprocess.run(['cp', src, 'build/video_full.mp4'], check=True)
PY
mkdir -p out
if [ "$NAR" = "none" ]; then OUTF=out/guerra_dos_ossos_PREVIA.mp4; else OUTF=out/guerra_dos_ossos_1080p.mp4; fi
./mix_and_mux.sh build/video_full.mp4 "$NAR" build/sound_bed.wav "$OUTF"
