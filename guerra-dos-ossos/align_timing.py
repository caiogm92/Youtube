#!/usr/bin/env python3
"""Alinhamento de tempo palavra a palavra (sem Whisper).

Uso:
  python3 align_timing.py --estimate            # timeline provisória (~140 ppm), sem áudio
  python3 align_timing.py narracao.mp3          # silencedetect do ffmpeg + roteiro
Saída: build/words.json  [{"w": palavra, "t0": s, "t1": s, "p": índice do parágrafo}]
"""
import json, re, subprocess, sys, os

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPT = os.path.join(HERE, 'roteiro.txt')
OUT = os.path.join(HERE, 'build', 'words.json')

def tokens():
    paras = [p.strip() for p in open(SCRIPT, encoding='utf-8').read().split('\n\n') if p.strip()]
    toks = []
    for pi, p in enumerate(paras):
        for w in p.split():
            toks.append({'w': w, 'p': pi})
    return toks

def pause_after(tok, nxt):
    w = tok['w']
    if nxt is not None and nxt['p'] != tok['p']:
        return 0.95
    if w.endswith(('.', '!', '?')):
        return 0.50
    if w.endswith((':', ';')):
        return 0.30
    if w.endswith(','):
        return 0.16
    return 0.0

def weight(w):
    return max(2, len(re.sub(r'[^\wÀ-ÿ]', '', w))) + 1.2

def estimate(toks, lead=0.8, cps=15.2):
    t = lead
    for i, tk in enumerate(toks):
        d = weight(tk['w']) / cps
        tk['t0'], tk['t1'] = round(t, 3), round(t + d, 3)
        t += d + pause_after(tk, toks[i + 1] if i + 1 < len(toks) else None)
    return toks, t + 1.5

def silences(audio, noise='-34dB', dur=0.22):
    r = subprocess.run(['ffmpeg', '-hide_banner', '-i', audio, '-af', f'silencedetect=noise={noise}:d={dur}',
                        '-f', 'null', '-'], capture_output=True, text=True)
    st, out = None, []
    for line in r.stderr.splitlines():
        m = re.search(r'silence_start: ([\d.]+)', line)
        if m: st = float(m.group(1))
        m = re.search(r'silence_end: ([\d.]+)', line)
        if m and st is not None:
            out.append((st, float(m.group(1)))); st = None
    d = float(subprocess.run(['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'csv=p=0', audio],
                             capture_output=True, text=True).stdout.strip())
    return out, d

def align(toks, audio):
    sil, dur = silences(audio)
    # trechos de fala = complementos dos silêncios
    speech, cur = [], 0.0
    for a, b in sil:
        if a - cur > 0.05: speech.append((cur, a))
        cur = b
    if dur - cur > 0.05: speech.append((cur, dur))
    total_speech = sum(b - a for a, b in speech)
    W = [weight(t['w']) for t in toks]
    totW = sum(W)
    # mapeia peso acumulado -> tempo de fala acumulado -> tempo real
    def speech_to_real(s):
        acc = 0.0
        for a, b in speech:
            if s <= acc + (b - a): return a + (s - acc)
            acc += b - a
        return speech[-1][1]
    acc = 0.0
    for tk, w in zip(toks, W):
        s0 = acc / totW * total_speech; acc += w
        s1 = acc / totW * total_speech
        tk['t0'], tk['t1'] = round(speech_to_real(s0), 3), round(speech_to_real(s1 - 1e-4), 3)
    # encaixa inícios de frase no fim de silêncio mais próximo (< 0.8 s)
    ends = [b for a, b in sil]
    for i, tk in enumerate(toks):
        if i == 0 or toks[i - 1]['w'].endswith(('.', '!', '?', ':')) or toks[i - 1]['p'] != tk['p']:
            near = min(ends, key=lambda e: abs(e - tk['t0'])) if ends else tk['t0']
            if abs(near - tk['t0']) < 0.8: tk['t0'] = round(near, 3)
    return toks, dur

if __name__ == '__main__':
    toks = tokens()
    if len(sys.argv) > 1 and sys.argv[1] != '--estimate':
        toks, dur = align(toks, sys.argv[1]); mode = 'audio'
    else:
        toks, dur = estimate(toks); mode = 'estimate'
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    json.dump({'mode': mode, 'duration': round(dur, 3), 'words': toks}, open(OUT, 'w'), ensure_ascii=False, indent=0)
    print(f'{mode}: {len(toks)} palavras, duração {dur:.1f}s -> {OUT}')
