#!/usr/bin/env python3
"""Mixagem final: narração + trilha (5 cues) com ducking automático + efeitos.
Saída: build/mix.wav (48 kHz, estéreo, normalizado para -14 LUFS)."""
import os, subprocess, sys
import numpy as np

ROOT = os.path.dirname(os.path.abspath(__file__))
SR = 48000
sys.path.insert(0, ROOT)
from timeline import build


def decode(path, ch=2):
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", path, "-ac", str(ch), "-ar", str(SR), "-f", "f32le", "-"],
                         capture_output=True, check=True).stdout
    return np.frombuffer(raw, np.float32).reshape(-1, ch).copy()


def ramp(n, a, b):
    return np.linspace(a, b, max(n, 1), dtype=np.float32)[:, None]


def place(bus, clip, t0, gain=1.0, fade_in=0.0, fade_out=0.0, skip=0.0, until=None):
    clip = clip[int(skip * SR):]
    if until is not None:
        clip = clip[:max(0, int((until - t0) * SR))]
    clip = clip * gain
    if fade_in:
        n = min(len(clip), int(fade_in * SR)); clip[:n] *= ramp(n, 0, 1)
    if fade_out:
        n = min(len(clip), int(fade_out * SR)); clip[len(clip) - n:] *= ramp(n, 1, 0)
    i0 = int(t0 * SR)
    i1 = min(len(bus), i0 + len(clip))
    bus[i0:i1] += clip[:i1 - i0]


def db(x):
    return 10 ** (x / 20)


def main():
    shots, meta = build()
    total = meta["total"]
    narr = {int(k): v for k, v in meta["narr"].items()}
    N = int(total * SR) + SR
    voice = np.zeros((N, 2), np.float32)
    music = np.zeros((N, 2), np.float32)
    fx = np.zeros((N, 2), np.float32)

    for c, t0 in narr.items():
        v = decode(os.path.join(ROOT, f"build/narr{c}.wav"))
        place(voice, v, t0, gain=db(-1.0))

    # início de cada cue = cartela do capítulo
    cards = [s["start"] for s in shots if s["type"] == "black" and s.get("text")]
    A = lambda n: os.path.join(ROOT, "audio", n)
    m1, m2, m3 = decode(A("music1.mp3")), decode(A("music2.mp3")), decode(A("music3.mp3"))
    if not os.path.exists(A("music1_dark.wav")):  # tema de piano 2 semitons abaixo, mais escuro
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", A("music1.mp3"), "-af",
                        "asetrate=44100*0.89,aresample=48000,lowpass=f=3200,volume=1.3", A("music1_dark.wav")], check=True)
    m1d = decode(A("music1_dark.wav"))
    xf = 2.5
    ret = [s["start"] for s in shots if any("2024" in ln["text"] for ln in s.get("text", []))][0]
    # Cap 1-3: um cue original por capítulo
    place(music, m1, 0.0, fade_in=3.0, fade_out=xf, until=cards[1] + xf / 2)
    place(music, m2, cards[1] - 0.5, fade_in=1.0, fade_out=xf, until=cards[2] + xf / 2)
    place(music, m3, cards[2] - 0.5, fade_in=1.0, fade_out=xf, until=cards[3] + xf / 2)
    # Cap 4: tema do piano, mais grave e escuro -> a construção de m3 no retorno (2024)
    place(music, m1d, cards[3] - 0.5, fade_in=1.5, fade_out=xf, until=ret + xf / 2)
    place(music, m3, ret - xf / 2, fade_in=xf, fade_out=xf, skip=28.0, until=cards[4] + xf / 2)
    # Cap 5: abertura reflexiva de m3 -> reprise de m2 terminando junto com o vídeo
    d2 = len(m2) / SR
    t2 = total - d2
    place(music, m3, cards[4] - xf / 2, fade_in=xf, fade_out=xf, until=t2 + xf)
    place(music, m2, t2, fade_in=xf, fade_out=4.0)

    # efeitos
    op = os.path.join(ROOT, "audio/sfx_abertura.mp3")
    if os.path.exists(op):
        place(fx, decode(op), 0.0, gain=db(-6), fade_out=2.5, until=narr[1] + 3.0)
    fin = os.path.join(ROOT, "audio/sfx_torcida.mp3")
    end_card = shots[-1]["start"]
    if os.path.exists(fin):
        place(fx, decode(fin), end_card - 1.5, gain=db(-10), fade_in=2.5, fade_out=3.0)

    # ducking: envelope da voz (ataque 60 ms, release 500 ms)
    env = np.abs(voice).max(1)
    hop = SR // 100
    e = env[: len(env) // hop * hop].reshape(-1, hop).max(1)
    sm = np.zeros_like(e)
    a_att, a_rel = np.exp(-1 / 6), np.exp(-1 / 50)
    for i in range(1, len(e)):
        a = a_att if e[i] > sm[i - 1] else a_rel
        sm[i] = a * sm[i - 1] + (1 - a) * e[i]
    act = np.clip(sm / 0.08, 0, 1)
    duck_db = -11.0 * act                       # trilha cai ~11 dB sob a voz
    g = np.repeat(db(duck_db), hop)
    g = np.pad(g, (0, N - len(g)), constant_values=1.0)[:, None].astype(np.float32)
    music *= g * db(-9.0)
    # clímax: trilha cresce 3 dB nos últimos 45 s
    tail = int((total - 45) * SR)
    music[tail:] *= ramp(N - tail, 1.0, db(3.0))

    mix = voice + music + fx
    mix = mix[: int(total * SR)]
    tmp = os.path.join(ROOT, "build/mix_raw.wav")
    out = os.path.join(ROOT, "build/mix.wav")
    peak = np.abs(mix).max()
    if peak > 0.99:
        mix *= 0.99 / peak
    pcm = (mix * 32767).astype(np.int16)
    import wave
    with wave.open(tmp, "wb") as w:
        w.setnchannels(2); w.setsampwidth(2); w.setframerate(SR); w.writeframes(pcm.tobytes())
    import json, re
    err = subprocess.run(["ffmpeg", "-hide_banner", "-i", tmp, "-af",
                          "loudnorm=I=-14:TP=-1.5:LRA=20:print_format=json", "-f", "null", "-"],
                         capture_output=True, text=True).stderr
    m = json.loads(re.search(r"\{[^{}]*\"input_i\"[^{}]*\}", err).group(0))
    af = ("loudnorm=I=-14:TP=-1.5:LRA=20:linear=true:"
          f"measured_I={m['input_i']}:measured_TP={m['input_tp']}:measured_LRA={m['input_lra']}:"
          f"measured_thresh={m['input_thresh']}:offset={m['target_offset']}")
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", tmp, "-af", af, "-ar", str(SR), out], check=True)
    print("loudness in:", m["input_i"], "LUFS")
    os.remove(tmp)
    print("mix ok", round(total, 2), "s")


if __name__ == "__main__":
    main()
