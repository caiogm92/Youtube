"""Roteiro de planos do documentário, sincronizado às frases da narração.

Cada capítulo lista (frase, plano): o plano começa no início da frase indicada
(build/phrases.json, gerado por prep_audio.py) e vai até o próximo plano.
"""
import json, os

ROOT = os.path.dirname(os.path.abspath(__file__))

# fotos enviadas
P1 = "assets/pele_jovem_cerca.jpg"      # Pelé jovem na cerca (anos 1950)
P2 = "assets/pele_sorriso.jpg"          # Pelé sorrindo
P3 = "assets/pele_agachado.jpg"         # Pelé agachado no gramado, estádio lotado
ESC = "assets/escudo.jpg"               # escudo com coroa e estrelas
NEY = "assets/neymar_aceno.jpg"         # Neymar acenando (2025)
COST = "assets/gabriel_neymar_costas.jpg"  # Gabriel 9 e Neymar Jr 10 de costas (2025)
# b-roll ilustrativo gerado por IA (não retrata pessoas/eventos reais)
B_TORC = "assets/broll_torcida.jpg"
B_MEN = "assets/broll_menino.jpg"
B_PAI = "assets/broll_pai_filho.jpg"

CARD = 3.0        # duração das cartelas de capítulo
OPEN = 4.5        # abertura em preto
LEAD = 0.25       # corte acontece um pouco antes da frase
GOLD = (205, 170, 100)


def chapter_card(num, title):
    return {"type": "black", "text": [
        {"text": f"CAPÍTULO {num}", "font": "cond", "size": 26, "y": 0.43, "spacing": 14, "delay": 0.2,
         "color": GOLD, "wght": 400},
        {"text": title, "size": 58, "y": 0.53, "spacing": 10, "delay": 0.55, "rule": 0.10, "rule_dy": 62},
    ]}


def date_lines(lines, y0=0.47, dy=0.09, delay=0.6, step=1.1):
    out = []
    for i, ln in enumerate(lines):
        out.append({"text": ln, "font": "bebas", "size": 74, "y": y0 + i * dy, "spacing": 10,
                    "delay": delay + i * step})
    return out


def build():
    ph = json.load(open(os.path.join(ROOT, "build/phrases.json")))
    ph = {int(k): v for k, v in ph.items()}
    cuts = []   # (tempo_global, plano)
    narr = {}   # capítulo -> início global da narração

    def at(c, i):
        return narr[c] + ph[c]["phrases"][i][0] - (LEAD if i else 0)

    def end(c):
        return narr[c] + ph[c]["dur"]

    # ------------------------------------------------ CAPÍTULO 1
    cuts.append((0.0, {"type": "black", "text": [
        {"text": "CAPÍTULO I", "font": "cond", "size": 26, "y": 0.43, "spacing": 14, "delay": 1.0, "color": GOLD,
         "wght": 400},
        {"text": "ANTES DE SER LENDA", "size": 58, "y": 0.53, "spacing": 10, "delay": 1.4, "rule": 0.10,
         "rule_dy": 62, "fadeout": 0.9}]}))
    narr[1] = OPEN
    c = 1
    cuts += [
        (at(c, 0), {"type": "sea", "fade_in": 1.5}),
        (at(c, 2), {"type": "crop", "img": P1, "c0": (0.30, 0.28), "c1": (0.20, 0.30), "z0": 2.3, "z1": 2.6, "dim": 0.8}),
        (at(c, 4), {"type": "crop", "img": ESC, "c0": (0.5, 0.62), "c1": (0.5, 0.55), "z0": 1.35, "z1": 1.15}),
        (at(c, 5), {"type": "crop", "img": P3, "c0": (0.55, 0.40), "c1": (0.58, 0.36), "z0": 2.5, "z1": 2.9}),
        (at(c, 8), {"type": "crest", "z0": 0.92, "z1": 1.04}),
    ]
    t_title = end(1) + 0.5
    cuts.append((t_title, {"type": "flag", "dark": 0.22, "text": [
        {"text": "SANTOS FC", "size": 120, "y": 0.45, "spacing": 22, "delay": 0.3, "wght": 700},
        {"text": "1912 — ETERNAMENTE.", "font": "cond", "size": 34, "y": 0.60, "spacing": 16, "delay": 1.2,
         "color": GOLD, "wght": 400}]}))

    # ------------------------------------------------ CAPÍTULO 2
    t = t_title + 5.0
    cuts.append((t, chapter_card("II", "O MUNDO AOS SEUS PÉS")))
    narr[2] = t + CARD
    c = 2
    cuts += [
        (at(c, 0), {"type": "crop", "img": P3, "c0": (0.25, 0.17), "c1": (0.75, 0.17), "z0": 2.2, "z1": 2.3}),
        (at(c, 3), {"type": "photo", "img": P1, "z0": 1.0, "z1": 1.07, "x0": 0.01, "x1": -0.01}),
        (at(c, 4), {"type": "crop", "img": P1, "c0": (0.55, 0.30), "c1": (0.55, 0.27), "z0": 2.4, "z1": 2.8}),
        (at(c, 5), {"type": "photo", "img": P2, "h": 0.78, "z0": 1.0, "z1": 1.1}),
        (at(c, 8), {"type": "photo", "img": P3, "z0": 1.04, "z1": 1.0, "y0": 0.0, "y1": 0.0}),
        (at(c, 9), {"type": "crop", "img": P3, "c0": (0.50, 0.33), "c1": (0.49, 0.30), "z0": 1.9, "z1": 2.3}),
        (at(c, 10), {"type": "map", "routes": [("MONTEVIDÉU", "LIBERTADORES 1962"), ("BUENOS AIRES", "LIBERTADORES 1963"),
                                              ("LISBOA", "MUNDIAL 1962"), ("MILÃO", "MUNDIAL 1963")]}),
        (at(c, 11), {"type": "crop", "img": ESC, "c0": (0.5, 0.16), "c1": (0.5, 0.17), "z0": 2.3, "z1": 2.7}),
        (at(c, 13), {"type": "crop", "img": P1, "c0": (0.55, 0.55), "c1": (0.58, 0.52), "z0": 2.0, "z1": 2.3}),
        (at(c, 14), {"type": "photo", "img": P3, "z0": 1.08, "z1": 1.14, "shade": 0.55,
                     "text": date_lines(["1962 — CAMPEÃO DO MUNDO", "1963 — CAMPEÃO DO MUNDO"], delay=0.5, step=1.0)}),
    ]

    # ------------------------------------------------ CAPÍTULO 3
    t = end(2) + 2.0
    cuts.append((t, chapter_card("III", "UMA CAMISA QUE NUNCA PERDEU SUA HISTÓRIA")))
    narr[3] = t + CARD
    c = 3
    cuts += [
        (at(c, 0), {"type": "sea", "dusk": True}),
        (at(c, 4), {"type": "rain", "light": True}),
        (at(c, 5), {"type": "broll", "img": B_TORC, "mode": "color", "c0": (0.5, 0.55), "c1": (0.45, 0.5), "z0": 1.05, "z1": 1.18}),
        (at(c, 9), {"type": "flag", "dark": 0.6}),
        (at(c, 11), {"type": "crop", "img": COST, "c0": (0.70, 0.62), "c1": (0.66, 0.66), "z0": 2.6, "z1": 2.9, "mode": "bw", "dim": 0.75}),
        (at(c, 14), {"type": "crop", "img": COST, "c0": (0.72, 0.52), "c1": (0.72, 0.54), "z0": 2.0, "z1": 2.2, "mode": "bw"}),
        (at(c, 15), {"type": "map", "routes": [("MONTEVIDÉU", "LIBERTADORES 2011")]}),
        (at(c, 17), {"type": "flag", "dark": 0.3, "text": date_lines(["2011 — TRICAMPEÃO DA AMÉRICA."], y0=0.5, delay=0.3)}),
    ]

    # ------------------------------------------------ CAPÍTULO 4
    t = end(3) + 1.6
    cuts.append((t, chapter_card("IV", "QUANDO O GIGANTE PRECISOU LUTAR")))
    narr[4] = t + CARD
    c = 4
    cuts += [
        (at(c, 0), {"type": "rain"}),
        (at(c, 4), {"type": "crop", "img": ESC, "c0": (0.5, 0.6), "c1": (0.5, 0.6), "z0": 1.6, "z1": 1.25, "dim": 0.45}),
        (at(c, 5), {"type": "rain", "close": True}),
        (at(c, 8), {"type": "photo", "img": P3, "z0": 1.0, "z1": 1.08, "x0": -0.01, "x1": 0.01}),
        (at(c, 11), {"type": "broll", "img": B_TORC, "mode": "color", "c0": (0.4, 0.5), "c1": (0.6, 0.45), "z0": 1.25, "z1": 1.1,
                     "text": date_lines(["2024 — O RETORNO."], y0=0.80, delay=1.2)}),
        (at(c, 13), {"type": "flag", "dark": 0.75}),
        (at(c, 15), {"type": "photo", "img": COST, "mode": "color", "z0": 1.0, "z1": 1.08}),
    ]

    # ------------------------------------------------ CAPÍTULO 5
    t = end(4) + 1.6
    cuts.append((t, chapter_card("V", "ETERNAMENTE SANTOS")))
    narr[5] = t + CARD
    c = 5
    cuts += [
        (at(c, 0), {"type": "flag", "dark": 0.45}),
        (at(c, 2), {"type": "crop", "img": ESC, "c0": (0.5, 0.17), "c1": (0.5, 0.16), "z0": 2.0, "z1": 2.4}),
        (at(c, 3), {"type": "crop", "img": P1, "c0": (0.25, 0.32), "c1": (0.30, 0.30), "z0": 2.0, "z1": 2.2, "dim": 0.85}),
        (at(c, 4), {"type": "broll", "img": B_MEN, "mode": "color", "c0": (0.5, 0.55), "c1": (0.5, 0.45), "z0": 1.0, "z1": 1.15}),
        (at(c, 5), {"type": "broll", "img": B_PAI, "mode": "color", "c0": (0.45, 0.5), "c1": (0.55, 0.5), "z0": 1.12, "z1": 1.02}),
        (at(c, 6), {"type": "broll", "img": B_TORC, "mode": "color", "c0": (0.5, 0.4), "c1": (0.5, 0.5), "z0": 1.3, "z1": 1.12}),
        (at(c, 7), {"type": "photo", "img": P2, "h": 0.78, "z0": 1.0, "z1": 1.08}),
        (at(c, 8), {"type": "photo", "img": NEY, "mode": "color", "z0": 1.0, "z1": 1.08}),
        (at(c, 9), {"type": "photo", "img": COST, "mode": "color", "z0": 1.06, "z1": 1.0, "side": 0.5}),
        (at(c, 10), {"type": "photo", "img": P1, "z0": 1.0, "z1": 1.1}),
        (at(c, 13), {"type": "sea"}),
        (at(c, 14), {"type": "map", "fast": True, "routes": [("RIO DE JANEIRO", "BRASIL"), ("MONTEVIDÉU", "AMÉRICA"),
                                                             ("LISBOA", "MUNDO")]}),
        (at(c, 16), {"type": "broll", "img": B_TORC, "mode": "color", "c0": (0.5, 0.5), "c1": (0.5, 0.5), "z0": 1.0, "z1": 1.12}),
        (at(c, 17), {"type": "broll", "img": B_MEN, "mode": "color", "c0": (0.5, 0.35), "c1": (0.5, 0.42), "z0": 1.5, "z1": 1.25}),
        (at(c, 19), {"type": "broll", "img": B_PAI, "mode": "color", "c0": (0.4, 0.45), "c1": (0.35, 0.45), "z0": 1.5, "z1": 1.7}),
        (at(c, 21), {"type": "broll", "img": B_TORC, "mode": "color", "c0": (0.5, 0.62), "c1": (0.5, 0.42), "z0": 1.6, "z1": 1.0}),
        (at(c, 24), {"type": "photo", "img": P1, "z0": 1.04, "z1": 1.1, "fade_out": 1.4}),
    ]
    t_end = end(5) + 0.8
    cuts.append((t_end, {"type": "crest", "black": True, "fade_in": 2.0, "fade_out": 2.2, "z0": 0.62, "z1": 0.66,
                         "y": -0.08, "text": [
                             {"text": "SANTOS FUTEBOL CLUBE", "size": 54, "y": 0.80, "spacing": 12, "delay": 2.4},
                             {"text": "1912 — ETERNAMENTE.", "font": "cond", "size": 28, "y": 0.87, "spacing": 16,
                              "delay": 3.4, "color": GOLD, "wght": 400}]}))
    total = t_end + 9.0

    shots = []
    for i, (t0, s) in enumerate(cuts):
        t1 = cuts[i + 1][0] if i + 1 < len(cuts) else total
        s = dict(s, start=round(t0, 3), dur=round(t1 - t0, 3))
        shots.append(s)
    meta = {"total": total, "narr": narr, "chapter_end": {k: end(k) for k in narr}}
    return shots, meta


if __name__ == "__main__":
    shots, meta = build()
    for i, s in enumerate(shots):
        print(f"{i:02d} {s['start']:7.2f} {s['dur']:5.2f} {s['type']:6s} {s.get('img', '')}")
    print(meta)
