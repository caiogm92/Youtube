#!/usr/bin/env python3
"""SOUND BED — sintetiza drone sombrio, pulso, ruído de projetor, trem e efeitos a partir de build/cues.json.
Nada é baixado: tudo é gerado com numpy.

Uso: python3 sound_bed.py [build/cues.json] [build/sound_bed.wav]
cues.json = {"duration": s, "cues": [{"t": s, "type": "...", ...}]}
tipos: whoosh, type(n), stamp, circle, string, pin, projector(t1), train(t1), boom, hit, riser(t1), pulse(t1)
"""
import json, sys, os, wave
import numpy as np

SR = 48000
rng = np.random.default_rng(7)

def env(n, a, r):
    e = np.ones(n); a = min(a, n); r = min(r, n)
    if a: e[:a] = np.linspace(0, 1, a)
    if r: e[-r:] *= np.linspace(1, 0, r)
    return e

def lowpass(x, k):
    if k <= 1: return x
    c = np.cumsum(np.concatenate([[0], x])); y = (c[k:] - c[:-k]) / k
    return np.concatenate([y, np.full(k - 1, y[-1])])

def band(x, lo, hi):
    return lowpass(x, lo) - lowpass(x, hi)

def noise(n): return rng.standard_normal(n)

def put(buf, t, sig, gain=1.0, pan=0.0):
    i = int(t * SR)
    if i >= buf.shape[0] or i + len(sig) <= 0: return
    j = min(buf.shape[0], i + len(sig)); s = sig[:j - i] * gain
    buf[i:j, 0] += s * (1 - pan) ** 0.5; buf[i:j, 1] += s * (1 + pan) ** 0.5

# ── efeitos ───────────────────────────────────────────────────────────────
def whoosh(d=1.1):
    n = int(d * SR); x = noise(n); tt = np.linspace(0, 1, n)
    m = np.sin(np.pi * tt)                       # o "brilho" sobe e desce
    out = lowpass(x, 40) * 3.0 * (1 - m) + lowpass(x, 5) * m
    return out * np.sin(np.pi * tt) ** 2 * 0.9

def click(seed):
    r = np.random.default_rng(seed); n = int(0.035 * SR)
    x = r.standard_normal(n) * np.exp(-np.linspace(0, 1, n) * 18)
    x = band(x, 2, 9) * 1.4
    thump = np.sin(2 * np.pi * r.uniform(180, 260) * np.arange(n) / SR) * np.exp(-np.linspace(0, 1, n) * 25) * 0.4
    return x + thump

def typing(nchars, cps=26):
    d = nchars / cps + 0.3; out = np.zeros(int(d * SR))
    for k in range(nchars):
        i = int((k / cps + rng.uniform(-0.008, 0.008)) * SR)
        c = click(k * 13 + nchars) * rng.uniform(0.6, 1.0)
        out[max(0, i):max(0, i) + len(c)] += c[:len(out) - max(0, i)]
    bell = np.sin(2 * np.pi * 2100 * np.arange(int(0.25 * SR)) / SR) * np.exp(-np.linspace(0, 1, int(0.25 * SR)) * 8) * 0.12
    i = int(nchars / cps * SR); out[i:i + len(bell)] += bell[:len(out) - i]
    return out

def stamp():
    n = int(0.5 * SR); t = np.arange(n) / SR
    body = np.sin(2 * np.pi * (90 - 40 * t) * t) * np.exp(-t * 14)
    slap = lowpass(noise(n), 3) * np.exp(-t * 60) * 1.2
    return (body * 1.2 + slap)

def scratch(d=0.7):
    n = int(d * SR); x = band(noise(n), 3, 14)
    am = 0.6 + 0.4 * np.sin(2 * np.pi * 9 * np.arange(n) / SR)
    return x * am * env(n, 800, 4000) * 0.7

def zipstring(d=0.6):
    n = int(d * SR); t = np.arange(n) / SR
    f = 300 + 900 * t / d
    return np.sin(2 * np.pi * np.cumsum(f) / SR) * 0.12 * env(n, 300, 3000) + band(noise(n), 2, 6) * 0.25 * env(n, 300, 5000)

def pinsnd():
    n = int(0.12 * SR); t = np.arange(n) / SR
    out = np.sin(2 * np.pi * 1300 * t) * np.exp(-t * 60) * 0.5; c = click(5); out[:len(c)] += c * 0.6
    return out

def projector(d):
    n = int(d * SR); t = np.arange(n) / SR
    clat = (np.sin(2 * np.pi * 24 * t) > 0.6).astype(float)
    clat = lowpass(clat * noise(n), 4) * 0.5
    hum = np.sin(2 * np.pi * 60 * t) * 0.05 + band(noise(n), 6, 60) * 0.25
    return (clat + hum) * env(n, 6000, 9000)

def train(d):
    n = int(d * SR); t = np.arange(n) / SR
    rate = 3.2
    chug = (np.sin(2 * np.pi * rate * t) ** 8) * lowpass(noise(n), 6) * 1.4
    rumble = lowpass(noise(n), 200) * 3.0
    whistle = np.zeros(n)
    m = int(1.2 * SR)
    if n > m:
        tw = np.arange(m) / SR
        whistle[:m] = (np.sin(2 * np.pi * 520 * tw) + 0.6 * np.sin(2 * np.pi * 660 * tw)) * env(m, 3000, 12000) * 0.15
    return (chug + rumble + whistle) * env(n, 12000, 24000)

def boom():
    n = int(3.0 * SR); t = np.arange(n) / SR
    sub = np.sin(2 * np.pi * (55 - 25 * t) * t) * np.exp(-t * 1.6) * 1.4
    crack = lowpass(noise(n), 2) * np.exp(-t * 9) * 1.3
    rumble = lowpass(noise(n), 120) * np.exp(-t * 1.2) * 6
    return sub + crack + rumble

def hit():
    n = int(4.0 * SR); t = np.arange(n) / SR
    sub = np.sin(2 * np.pi * 42 * t) * np.exp(-t * 1.1) * 1.2
    metal = sum(np.sin(2 * np.pi * f * t) * np.exp(-t * dcy) for f, dcy in [(173, 2.2), (347, 3.0), (529, 4.0)]) * 0.18
    return sub + metal + lowpass(noise(n), 3) * np.exp(-t * 20) * 0.8

def riser(d):
    n = int(d * SR); t = np.arange(n) / SR
    f = 80 + 300 * (t / d) ** 2
    tone = np.sin(2 * np.pi * np.cumsum(f) / SR) * 0.25
    return (tone + band(noise(n), 2, 30) * 0.4 * (t / d)) * (t / d) ** 1.5

def drone(dur):
    n = int(dur * SR); t = np.arange(n) / SR
    out = np.zeros((n, 2))
    for f, g, lfo in [(55, 0.30, 0.05), (82.4, 0.16, 0.07), (110.3, 0.10, 0.031), (164.8, 0.05, 0.043)]:
        for ch, det in ((0, 0.0), (1, 0.35)):
            out[:, ch] += np.sin(2 * np.pi * (f + det) * t + 2 * np.sin(2 * np.pi * lfo * t)) * g * (0.75 + 0.25 * np.sin(2 * np.pi * lfo * 1.7 * t + ch))
    air = lowpass(noise(n), 400) * 2.5
    out += air[:, None] * 0.6
    out *= env(n, int(3 * SR), int(4 * SR))[:, None]
    return out * 0.5

def pulse(d, bpm=72):
    n = int(d * SR); t = np.arange(n) / SR; out = np.zeros(n)
    per = 60 / bpm; k = int(0.25 * SR); tk = np.arange(k) / SR
    beat = np.sin(2 * np.pi * 50 * tk) * np.exp(-tk * 14)
    for i, bt in enumerate(np.arange(0, d, per)):
        j = int(bt * SR); amp = 0.4 + 0.6 * (bt / d)
        out[j:j + k] += beat[:n - j] * amp
    return out

FX = {'whoosh': lambda c: whoosh(c.get('d', 1.1)), 'type': lambda c: typing(c.get('n', 10)), 'stamp': lambda c: stamp(),
      'circle': lambda c: scratch(c.get('d', 0.7)), 'string': lambda c: zipstring(c.get('d', 0.6)), 'pin': lambda c: pinsnd(),
      'projector': lambda c: projector(c['t1'] - c['t']), 'train': lambda c: train(c['t1'] - c['t']), 'boom': lambda c: boom(),
      'hit': lambda c: hit(), 'riser': lambda c: riser(c['t1'] - c['t']), 'pulse': lambda c: pulse(c['t1'] - c['t'])}
GAIN = {'whoosh': 0.30, 'type': 0.22, 'stamp': 0.55, 'circle': 0.20, 'string': 0.20, 'pin': 0.18, 'projector': 0.30,
        'train': 0.30, 'boom': 0.55, 'hit': 0.6, 'riser': 0.35, 'pulse': 0.40}

if __name__ == '__main__':
    here = os.path.dirname(os.path.abspath(__file__))
    cin = sys.argv[1] if len(sys.argv) > 1 else os.path.join(here, 'build', 'cues.json')
    out = sys.argv[2] if len(sys.argv) > 2 else os.path.join(here, 'build', 'sound_bed.wav')
    C = json.load(open(cin))
    dur = C['duration']
    buf = drone(dur)
    for c in C['cues']:
        sig = FX[c['type']](c)
        put(buf, c['t'], sig, GAIN[c['type']] * c.get('g', 1.0), c.get('pan', 0.0))
    # silencia o drone dentro dos inserts (o projetor assume) e no glitch final o hit domina
    peak = np.max(np.abs(buf)) + 1e-9
    buf = buf / peak * 0.89
    pcm = (buf * 32767).astype(np.int16)
    with wave.open(out, 'wb') as w:
        w.setnchannels(2); w.setsampwidth(2); w.setframerate(SR); w.writeframes(pcm.tobytes())
    print(f'{out}: {dur:.1f}s, {len(C["cues"])} deixas')
