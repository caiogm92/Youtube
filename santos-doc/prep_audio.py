#!/usr/bin/env python3
"""Prepara a narração: encurta pausas longas, aplica leve ganho de andamento
e grava os tempos de início/fim de cada frase em build/phrases.json."""
import json, os, re, subprocess
import numpy as np

ROOT = os.path.dirname(os.path.abspath(__file__))
SR = 44100
TEMPO = 1.04          # leve aceleração sem alterar o tom
CAP_SHORT = 0.62      # pausas comuns
CAP_LONG = 1.0        # pausas dramáticas (originalmente > 1.3 s)
FILES = {1: "ch1a", 2: "ch2", 3: "ch3", 4: "ch4", 5: "ch5"}


def decode(path):
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", path, "-ac", "1", "-ar", str(SR), "-f", "f32le", "-"],
                         capture_output=True, check=True).stdout
    return np.frombuffer(raw, np.float32).copy()


def silences(path):
    err = subprocess.run(["ffmpeg", "-hide_banner", "-i", path, "-af", "silencedetect=noise=-38dB:d=0.35",
                          "-f", "null", "-"], capture_output=True, text=True).stderr
    st = [float(x) for x in re.findall(r"silence_start: ([0-9.]+)", err)]
    en = [float(x) for x in re.findall(r"silence_end: ([0-9.]+)", err)]
    return list(zip(st, en))


def main():
    os.makedirs(os.path.join(ROOT, "build"), exist_ok=True)
    out = {}
    for ch, name in FILES.items():
        src = os.path.join(ROOT, "audio", name + ".mp3")
        a = decode(src)
        sil = [s for s in silences(src) if s[1] < len(a) / SR - 0.05]
        pieces, phrases, t_new, cur = [], [], 0.0, 0.0
        bounds = sil + [(len(a) / SR, len(a) / SR)]
        for (s0, s1) in bounds:
            # frase: de cur até s0
            seg = a[int(cur * SR):int(s0 * SR)]
            phrases.append((t_new, t_new + len(seg) / SR))
            pieces.append(seg)
            t_new += len(seg) / SR
            gap = s1 - s0
            if gap <= 0:
                break
            keep = min(gap, CAP_LONG if gap > 1.3 else CAP_SHORT)
            g = a[int(s0 * SR):int(s0 * SR) + int(keep * SR)].copy()
            # funde o fim do silêncio com o início da próxima frase
            fade = min(len(g), int(0.04 * SR))
            if fade:
                g[-fade:] *= np.linspace(1, 0, fade)
            pieces.append(g)
            t_new += len(g) / SR
            cur = s1 - 0.04
        y = np.concatenate(pieces).astype(np.float32)
        tmp = os.path.join(ROOT, "build", f"narr{ch}_raw.f32")
        y.tofile(tmp)
        wav = os.path.join(ROOT, "build", f"narr{ch}.wav")
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "f32le", "-ar", str(SR), "-ac", "1", "-i", tmp,
                        "-af", f"atempo={TEMPO}", "-ar", str(SR), wav], check=True)
        os.remove(tmp)
        dur = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of",
                                    "csv=p=0", wav], capture_output=True, text=True).stdout)
        out[ch] = {"dur": dur, "phrases": [(round(p0 / TEMPO, 3), round(p1 / TEMPO, 3)) for p0, p1 in phrases]}
        print(f"cap {ch}: {len(a)/SR:.1f}s -> {dur:.1f}s, {len(phrases)} frases")
    json.dump(out, open(os.path.join(ROOT, "build", "phrases.json"), "w"), indent=1)
    print("total narração:", round(sum(v["dur"] for v in out.values()), 1))


if __name__ == "__main__":
    main()
