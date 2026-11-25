# A Guerra dos Ossos — Charlie Dark Lab

Documentário de ~5 min, 1920×1080, 30 fps, no estilo quadro de evidências + inserts vintage de cinema mudo.

## Gerar

```bash
pip install numpy pillow global-land-mask
./make_all.sh                 # prévia: timeline estimada (~140 ppm), sem voz
./make_all.sh narracao.mp3    # final: alinha ao áudio, renderiza, mixa em -14 LUFS -> out/guerra_dos_ossos_1080p.mp4
```

Etapas individuais:

| Script | Função |
|---|---|
| `align_timing.py` | tempo de cada palavra (silencedetect do ffmpeg + roteiro) → `build/words.json` |
| `board_engine.py` | quadro: `beats`, `mapgrid`, `stills t1,t2`, `sheet` (folha de contato), `render`, `cues` |
| `vintage_engine.py` | inserts sépia: Elasmossauro (1868) e Como Bluff (1877) |
| `sound_bed.py` | drone, pulso, projetor, trem, explosão, datilografia, carimbos — tudo sintetizado |
| `splice.sh` | emenda os inserts no vídeo do quadro |
| `mix_and_mux.sh` | ducking sob a narração, -14 LUFS, H.264/AAC CRF 24 |

Os beats são ancorados em frases do `roteiro.txt` (função `T("frase")`), então qualquer narração nova
realinha câmera, barbantes, círculos, carimbos e inserts automaticamente.

## Pendências antes do corte final

1. **Narração** (MP3/WAV do `roteiro.txt`).
2. **Fotos reais** em `assets/photos/` (veja `assets/photos/LEIA-ME.md`) e `fontes.md` preenchido.
