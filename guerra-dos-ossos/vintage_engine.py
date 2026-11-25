#!/usr/bin/env python3
"""VINTAGE ENGINE — inserts 2D de cinema mudo (sépia), A Guerra dos Ossos.

Pessoas aparecem SÓ como silhuetas chapadas, sem rosto. Traços "fervendo" em twos (12 fps),
passando a 30 fps no clarão do impacto. Grão, riscos, poeira, flicker, trepidação da janela,
íris na entrada e na saída, intertítulos com borda dupla e pontos vermelhos nos cantos.

Uso:
  python3 vintage_engine.py stills elasmo 0.5,2,4     -> build/vstill_elasmo_*.jpg
  python3 vintage_engine.py render                    -> build/vintage_<id>.mp4 (todos os inserts)
"""
import math, os, sys, random, subprocess
import numpy as np
from PIL import Image, ImageDraw, ImageFilter
import board_engine as BE
from board_engine import F, T, W, H, FPS, RED, clamp, smooth, ease_out, rot, TYPE, FELL, PLAY, PLAYB, BEBAS

BUILD = BE.BUILD
SEPIA_BG = (214, 190, 146)
INKV = (46, 30, 18)

def insert_windows():
    S, _ = BE.build_scene()
    return {k: (a, b) for k, a, b in S['inserts']}

def frame_range(a, b):
    return math.ceil(a * FPS), math.ceil(b * FPS)

# ── papel sépia base (cache) ──────────────────────────────────────────────
_BASE = None
def base_paper():
    global _BASE
    if _BASE is None:
        _BASE = BE.paper_texture(W, H, SEPIA_BG, 501, stain=0.6, edge=0.55).convert('RGB')
    return _BASE

# ── traço "fervendo" ───────────────────────────────────────────────────────
class Boil:
    def __init__(self, seed, amp=2.2): self.rng = random.Random(seed); self.amp = amp
    def j(self, p): return (p[0] + self.rng.uniform(-self.amp, self.amp), p[1] + self.rng.uniform(-self.amp, self.amp))
    def pts(self, ps): return [self.j(p) for p in ps]

def poly(d, b, ps, fill=INKV, outline=None, width=3):
    q = b.pts(ps); d.polygon(q, fill=fill)
    if outline: d.line(q + [q[0]], fill=outline, width=width, joint='curve')

def line(d, b, ps, width=6, fill=INKV):
    d.line(b.pts(ps), fill=fill, width=width, joint='curve')

def disc(d, b, c, r, fill=INKV):
    x, y = b.j(c); r = r + b.rng.uniform(-1, 1); d.ellipse([x - r, y - r, x + r, y + r], fill=fill)

# ── silhueta humana (sem rosto) ────────────────────────────────────────────
def person(d, b, x, y, s=1.0, phase=0.0, walking=True, arms=None, hat='bowler', face=1):
    """x,y = pés. phase = ciclo de caminhada. arms = (ângulo_braço_frente, ângulo_braço_trás) em graus."""
    sw = math.sin(phase) * (24 if walking else 0)
    hip = (x, y - 92 * s); neck = (x + 4 * face * s, y - 168 * s)
    for a in (sw, -sw):   # pernas
        kx, ky = hip[0] + math.sin(math.radians(a)) * 46 * s, hip[1] + 46 * s
        fx, fy = kx + math.sin(math.radians(a * 0.6)) * 46 * s, y
        line(d, b, [hip, (kx, ky), (fx, fy)], int(15 * s))
        line(d, b, [(fx, fy), (fx + 14 * face * s, fy)], int(10 * s))
    poly(d, b, [(hip[0] - 18 * s, hip[1]), (hip[0] + 18 * s, hip[1]), (neck[0] + 20 * s, neck[1] + 6 * s),
                (neck[0] - 20 * s, neck[1] + 6 * s)])            # tronco / casaco
    poly(d, b, [(hip[0] - 22 * s, hip[1] - 4 * s), (hip[0] + 24 * s, hip[1] - 4 * s), (hip[0] + 26 * s, hip[1] + 22 * s), (hip[0] - 24 * s, hip[1] + 22 * s)])
    fa, ba = arms if arms else (-sw * 1.2, sw * 1.2)
    sh = (neck[0], neck[1] + 12 * s)
    for a in (fa, ba):
        ex, ey = sh[0] + math.sin(math.radians(a)) * 44 * s, sh[1] + math.cos(math.radians(a)) * 44 * s
        hx, hy = ex + math.sin(math.radians(a * 1.1)) * 40 * s, ey + math.cos(math.radians(a * 1.1)) * 40 * s
        line(d, b, [sh, (ex, ey), (hx, hy)], int(12 * s))
    head = (neck[0] + 2 * face * s, neck[1] - 22 * s)
    disc(d, b, head, 19 * s)
    if hat == 'bowler':
        poly(d, b, [(head[0] - 30 * s, head[1] - 12 * s), (head[0] + 30 * s, head[1] - 12 * s), (head[0] + 28 * s, head[1] - 17 * s), (head[0] - 28 * s, head[1] - 17 * s)])
        d.chord(b.pts([(head[0] - 19 * s, head[1] - 40 * s)])[0] + b.pts([(head[0] + 19 * s, head[1] + 2 * s)])[0], 180, 360, fill=INKV)
    elif hat == 'wide':
        poly(d, b, [(head[0] - 40 * s, head[1] - 12 * s), (head[0] + 40 * s, head[1] - 12 * s), (head[0] + 36 * s, head[1] - 18 * s), (head[0] - 36 * s, head[1] - 18 * s)])
        poly(d, b, [(head[0] - 18 * s, head[1] - 16 * s), (head[0] + 18 * s, head[1] - 16 * s), (head[0] + 14 * s, head[1] - 38 * s), (head[0] - 14 * s, head[1] - 38 * s)])
    return {'hand_front': (sh[0] + math.sin(math.radians(fa)) * 84 * s, sh[1] + math.cos(math.radians(fa)) * 84 * s)}

def bone(d, b, x, y, L=40, ang=0, w=7):
    dx, dy = rot(L / 2, 0, ang)
    line(d, b, [(x - dx, y - dy), (x + dx, y + dy)], w)
    for sx in (-1, 1):
        cx, cy = x + sx * dx, y + sx * dy
        px, py = rot(0, w * 0.7, ang)
        disc(d, b, (cx + px, cy + py), w * 0.75); disc(d, b, (cx - px, cy - py), w * 0.75)

def skull(d, b, x, y, s=1.0, face=1):
    poly(d, b, [(x - 30 * s * face, y - 14 * s), (x + 34 * s * face, y - 4 * s), (x + 52 * s * face, y + 6 * s),
                (x + 30 * s * face, y + 16 * s), (x - 30 * s * face, y + 16 * s)])
    disc(d, b, (x - 8 * s * face, y + 0 * s), 6 * s, fill=SEPIA_BG)

# ── efeitos de película ────────────────────────────────────────────────────
class Film:
    def __init__(self, seed):
        self.rng = np.random.default_rng(seed)
        self.grains = [(self.rng.normal(0, 1, (H // 2, W // 2)) * 13).astype(np.float32) for _ in range(8)]
        yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
        self.rr = np.sqrt((xx - W / 2) ** 2 + (yy - H / 2) ** 2)
        r = self.rr / math.hypot(W / 2, H / 2)
        self.vig = np.clip(1 - 0.75 * np.clip(r - 0.35, 0, 1) ** 1.4, 0, 1)[..., None]
        self.scr = []

    def apply(self, img, fi, t, dur, flash=0.0):
        rng = random.Random(fi * 7 + 3)
        # trepidação da janela
        ox, oy = rng.randint(-3, 3), rng.randint(-4, 4) + (6 if rng.random() < 0.02 else 0)
        img = img.transform(img.size, Image.AFFINE, (1, 0, ox, 0, 1, oy), Image.BILINEAR, fillcolor=(20, 14, 8))
        d = ImageDraw.Draw(img)
        # riscos verticais e poeira
        if rng.random() < 0.55:
            for _ in range(rng.randint(1, 3)):
                x = rng.randint(0, W); c = rng.choice([(250, 236, 205), (40, 28, 18)])
                d.line([(x, 0), (x + rng.randint(-8, 8), H)], fill=c, width=rng.choice([1, 1, 2]))
        for _ in range(rng.randint(2, 9)):
            x, y, r = rng.randint(0, W), rng.randint(0, H), rng.uniform(1, 4.5)
            d.ellipse([x - r, y - r, x + r, y + r], fill=rng.choice([(20, 14, 8), (250, 238, 210)]))
        if rng.random() < 0.05:
            x, y = rng.randint(0, W), rng.randint(0, H)
            d.arc([x, y, x + rng.randint(30, 90), y + rng.randint(30, 120)], rng.randint(0, 200), rng.randint(220, 360), fill=(28, 20, 12), width=2)
        a = np.asarray(img, np.float32)
        redm = ((a[..., 0] > 150) & (a[..., 1] < 100) & (a[..., 2] < 100))[..., None]   # vermelho = significado
        lum = a.mean(axis=2, keepdims=True)
        a = np.where(redm, a * 0.92, lum * np.array([1.08, 0.94, 0.74]) * 0.92 + a * 0.08)   # tonalidade sépia
        flick = 1 + 0.07 * math.sin(fi * 2.1) * math.sin(fi * 0.7) + rng.uniform(-0.04, 0.04)
        g = np.repeat(np.repeat(self.grains[fi % 8], 2, 0), 2, 1)[..., None]
        a = a * self.vig * flick + g
        if flash > 0: a = a * (1 - flash) + 255 * flash
        # íris (entrada / saída)
        rmax = math.hypot(W / 2, H / 2) + 4
        k = min(smooth(t / 0.5), smooth((dur - t) / 0.45))
        if k < 1:
            R = rmax * k
            m = np.clip((R - self.rr) / 3.0, 0, 1)[..., None]
            a = a * m
        return Image.fromarray(np.clip(a, 0, 255).astype(np.uint8))

def intertitle(lines, k=1.0):
    img = base_paper().copy(); img = Image.blend(img, Image.new('RGB', (W, H), (24, 16, 10)), 0.86)
    d = ImageDraw.Draw(img)
    c = (226, 206, 168)
    d.rectangle([150, 110, W - 150, H - 110], outline=c, width=6)
    d.rectangle([172, 132, W - 172, H - 132], outline=c, width=2)
    for (x, y) in [(150, 110), (W - 150, 110), (150, H - 110), (W - 150, H - 110)]:
        d.ellipse([x - 13, y - 13, x + 13, y + 13], fill=RED)
    y = H / 2 - (len(lines) - 1) * 60
    for i, (txt, fn, sz) in enumerate(lines):
        d.text((W / 2, y + i * 120), txt, font=F(fn, sz), fill=c, anchor='mm')
    # ornamento
    d.line([(W / 2 - 160, H - 230), (W / 2 + 160, H - 230)], fill=c, width=2)
    d.ellipse([W / 2 - 6, H - 236, W / 2 + 6, H - 224], fill=c)
    return img

# ════════════════════════════════════════════════════════════════════════════
# SEQUÊNCIA 1 — Elasmossauro: a cabeça no lugar errado
# ════════════════════════════════════════════════════════════════════════════
def elasmo_frame(t, dur, fi):
    draw_i = int(t * 12)       # twos: o desenho muda 12x por segundo
    b = Boil(draw_i * 31 + 1)
    if t < 1.9:
        return intertitle([('1868 · FILADÉLFIA', TYPE, 44), ('A CABEÇA', FELL, 110), ('NO LUGAR ERRADO', FELL, 110)])
    img = base_paper().copy(); d = ImageDraw.Draw(img)
    # chão do laboratório / cavaletes
    line(d, b, [(0, 860), (W, 860)], 5)
    for x in (520, 900, 1280):
        line(d, b, [(x, 860), (x, 700)], 9); line(d, b, [(x - 60, 860), (x, 760), (x + 60, 860)], 6)
    # esqueleto: pescoço longo à ESQUERDA (sem cabeça), cauda curta à direita (onde Cope põe o crânio)
    cx, cy = 900, 650
    pts = []
    for i in range(42):          # pescoço (esquerda) -> tronco
        u = i / 41; x = 180 + u * 560; y = 600 - 120 * math.sin(u * math.pi * 0.9) + 40 * u
        pts.append((x, y))
    for i in range(16):          # cauda (direita)
        u = i / 15; pts.append((1060 + u * 300, 655 - 20 * math.sin(u * 3)))
    for p in pts: disc(d, b, p, 9)
    d.ellipse(b.pts([(760, 590)])[0] + b.pts([(1080, 720)])[0], outline=INKV, width=8)   # caixa torácica
    for k in range(6):
        x = 800 + k * 45; d.arc([x - 30, 590, x + 30, 720], 200, 340, fill=INKV, width=5)
    for (px, py, a) in [(820, 720, 30), (1000, 720, -30)]:   # nadadeiras
        line(d, b, [(px, py), (px + 50 * math.sin(math.radians(a)) * 2, py + 90)], 12)
    # silhueta de Cope carregando o crânio até a ponta da cauda
    k = clamp((t - 1.9) / (dur - 2.6))
    px = 1750 - 260 * smooth(k * 1.4)
    walking = k < 0.7
    sk_target = (1380, 646)
    hand = person(d, b, px, 860, 1.25, phase=t * 9, walking=walking, arms=(-40, 10), hat='bowler', face=-1)['hand_front']
    if k < 0.72:
        skull(d, b, hand[0] - 20, hand[1] - 10, 1.0, face=1)
    else:
        u = smooth((k - 0.72) / 0.18)
        sx = hand[0] - 20 + (sk_target[0] - hand[0] + 20) * u; sy = hand[1] - 10 + (sk_target[1] - hand[1] + 10) * u - 60 * math.sin(u * math.pi)
        skull(d, b, sx, sy, 1.0, face=1)
        if u >= 1 and (t * 4) % 1 < 0.6:   # seta vermelha de alerta (significado)
            d.line([(1380, 520), (1380, 600)], fill=RED, width=8)
            d.polygon([(1360, 590), (1400, 590), (1380, 620)], fill=RED)
    d.text((W / 2, 980), 'O pescoço sem cabeça… e o crânio na ponta da cauda.', font=F(PLAY, 40), fill=INKV, anchor='mm')
    return img

# ════════════════════════════════════════════════════════════════════════════
# SEQUÊNCIA 2 — Como Bluff: espionagem, trem desviado, ossos destruídos, dinamite
# ════════════════════════════════════════════════════════════════════════════
def comobluff_frame(t, dur, fi, cues):
    t_spy, t_train, t_smash, t_boom = cues
    boom_dt = t - t_boom
    fast = 0 <= boom_dt < 1.2
    draw_i = fi if fast else int(t * 12)
    b = Boil(draw_i * 17 + 5, amp=3.5 if fast else 2.2)
    img = base_paper().copy(); d = ImageDraw.Draw(img)
    if t < t_spy:   # mapa esquemático em sépia
        d.text((W / 2, 110), 'TERRITÓRIO DO WYOMING · 1877', font=F(FELL, 70), fill=INKV, anchor='mm')
        rail = [(140, 640), (520, 610), (820, 560), (1120, 600), (1460, 560), (1800, 600)]
        line(d, b, rail, 7)
        for i in range(len(rail) - 1):
            (x0, y0), (x1, y1) = rail[i], rail[i + 1]
            for u in np.linspace(0, 1, 9)[:-1]:
                x, y = x0 + (x1 - x0) * u, y0 + (y1 - y0) * u
                line(d, b, [(x, y - 14), (x, y + 14)], 4)
        d.text((330, 680), 'Ferrovia Union Pacific', font=F(PLAY, 34), fill=INKV)
        for nm, (x, y) in [('LARAMIE', (520, 610)), ('MEDICINE BOW', (1460, 560))]:
            disc(d, b, (x, y), 12); d.text((x, y - 50), nm, font=F(TYPE, 32), fill=INKV, anchor='mm')
        k = smooth(t / max(0.5, t_spy - 0.6))
        x = 520 + (1120 - 520) * k
        for u in np.arange(520, x, 26): disc(d, b, (u, 600 - 40 * math.sin((u - 520) / 600 * math.pi)), 4, fill=RED)
        if k > 0.95:
            r = 22 + 8 * math.sin(t * 8)
            d.ellipse([1120 - r, 600 - r, 1120 + r, 600 + r], outline=RED, width=7)
            d.text((1120, 680), 'COMO BLUFF', font=F(TYPE, 46), fill=RED, anchor='mm')
        for (mx, my) in [(300, 400), (380, 420), (700, 380), (1600, 420), (1680, 390)]:
            line(d, b, [(mx - 40, my + 30), (mx, my - 20), (mx + 40, my + 30)], 5)
        return img
    # cena lateral: a escarpa
    hill = [(0, 900), (0, 640), (260, 600), (520, 520), (820, 470), (1100, 500), (1400, 560), (1700, 610), (W, 660), (W, 900)]
    poly(d, b, hill, fill=(170, 140, 98), outline=INKV, width=5)
    for (bx, by, a) in [(640, 540, 20), (760, 520, -10), (900, 515, 40), (1020, 530, -30), (1150, 545, 5)]:
        bone(d, b, bx, by, 48, a, 8)
    line(d, b, [(0, 900), (W, 900)], 5)
    if t < t_train:                       # espionagem
        hand = person(d, b, 1180, 545, 0.9, phase=0, walking=False, arms=(150, 160), hat='wide', face=-1)['hand_front']
        person(d, b, 760, 520, 0.9, phase=0, walking=False, arms=(160, -20), hat='wide', face=1)
        line(d, b, [(1680, 600), (1610, 575)], 10)                       # luneta
        person(d, b, 1730, 640, 1.0, phase=0, walking=False, arms=(-100, 20), hat='bowler', face=-1)
        if int(t * 3) % 2 == 0: d.ellipse([1585, 560, 1615, 590], outline=RED, width=5)
        d.text((W / 2, 1000), 'Equipes rivais vigiam umas às outras.', font=F(PLAY, 40), fill=INKV, anchor='mm')
    elif t < t_smash:                     # trem com caixotes desviados
        k = (t - t_train) / max(0.5, t_smash - t_train)
        x0 = -900 + 2900 * k
        ty = 900
        poly(d, b, [(x0 + 600, ty - 40), (x0 + 820, ty - 40), (x0 + 820, ty - 150), (x0 + 600, ty - 150)])     # cabine
        poly(d, b, [(x0 + 360, ty - 40), (x0 + 610, ty - 40), (x0 + 610, ty - 120), (x0 + 360, ty - 120)])     # caldeira
        poly(d, b, [(x0 + 380, ty - 120), (x0 + 420, ty - 120), (x0 + 430, ty - 200), (x0 + 370, ty - 200)])   # chaminé
        for k2 in range(5):
            r = 26 + k2 * 14 + (t * 30 % 10); cx = x0 + 390 - k2 * 80 - (t * 60 % 40); cy = ty - 230 - k2 * 40
            d.ellipse([cx - r, cy - r, cx + r, cy + r], outline=INKV, width=4)
        for wx in (x0 + 420, x0 + 520, x0 + 700, x0 + 780):
            d.ellipse([wx - 34, ty - 34, wx + 34, ty + 34], outline=INKV, width=8)
            a = t * 9
            line(d, b, [(wx - 30 * math.cos(a), ty - 30 * math.sin(a)), (wx + 30 * math.cos(a), ty + 30 * math.sin(a))], 5)
        for c in range(2):   # vagões
            cx = x0 - 60 - c * 420
            poly(d, b, [(cx, ty - 30), (cx + 380, ty - 30), (cx + 380, ty - 130), (cx, ty - 130)], fill=(120, 92, 60), outline=INKV)
            for j in range(3):
                bx = cx + 30 + j * 115
                poly(d, b, [(bx, ty - 130), (bx + 95, ty - 130), (bx + 95, ty - 210), (bx, ty - 210)], fill=(150, 118, 78), outline=INKV)
                d.text((bx + 47, ty - 170), 'OSSOS', font=F(TYPE, 22), fill=INKV, anchor='mm')
            for wx in (cx + 70, cx + 310): d.ellipse([wx - 28, ty - 28, wx + 28, ty + 28], outline=INKV, width=7)
        d.text((W / 2, 1010), 'Cargas desviadas no meio do caminho.', font=F(PLAY, 40), fill=INKV, anchor='mm')
    else:                                 # ossos destruídos + dinamite
        if boom_dt < 0:
            k = t - t_smash
            hit = abs(math.sin(k * 5))
            person(d, b, 980, 520, 0.95, phase=0, walking=False, arms=(170 - 140 * hit, -30), hat='wide', face=-1)
            hx, hy = 980 - 60 + 40 * hit, 360 + 120 * hit
            line(d, b, [(980, 380), (hx, hy)], 8); poly(d, b, [(hx - 20, hy - 12), (hx + 20, hy - 12), (hx + 20, hy + 12), (hx - 20, hy + 12)])
            if hit > 0.92:
                for j in range(6):
                    a = j * 1.05 + k; disc(d, b, (900 + 50 * math.cos(a), 520 - 40 * abs(math.sin(a))), 6)
            # pavio
            line(d, b, [(1300, 548), (1420, 560), (1520, 580)], 4)
            sp = 1520 - 200 * clamp(k / max(0.3, t_boom - t_smash))
            disc(d, b, (sp, 575), 9, fill=RED)
            poly(d, b, [(1290, 520), (1310, 520), (1310, 560), (1290, 560)], fill=RED)
            d.text((W / 2, 1010), 'O que não podiam levar… destruíam.', font=F(PLAY, 40), fill=INKV, anchor='mm')
        elif boom_dt < 2.0:               # explosão (30 fps)
            u = clamp(boom_dt / 1.2)
            R = 120 + 900 * ease_out(u)
            star = []
            rr = random.Random(fi)
            for j in range(26):
                a = j / 26 * 2 * math.pi; rad = R * (0.55 if j % 2 else 1.0) * rr.uniform(0.8, 1.15)
                star.append((1300 + rad * math.cos(a), 540 + rad * 0.7 * math.sin(a)))
            for j in range(7):
                r = 140 + 260 * u * (1 + j * 0.15); cx = 1300 + (j - 3) * 170 * u; cy = 470 - 300 * u - (j % 3) * 50
                d.ellipse([cx - r, cy - r * 0.6, cx + r, cy + r * 0.6], fill=(118, 96, 70))
            d.polygon(star, fill=(250, 236, 200), outline=INKV)
            for j in range(10):
                a = rr.uniform(-3.0, -0.2); dist = 200 + 800 * u * rr.uniform(0.5, 1.2)
                bone(d, b, 1300 + dist * math.cos(a), 540 + dist * math.sin(a) + 400 * u * u, 40, rr.uniform(0, 180), 7)
        else:
            return None   # -> intertítulo final
    return img

def comobluff_title():
    return intertitle([('COMO BLUFF · 1877–1889', TYPE, 44), ('CIÊNCIA', FELL, 120), ('COM DINAMITE', FELL, 120)])

# ════════════════════════════════════════════════════════════════════════════
def render_insert(key, a, b, still_times=None):
    f0, f1 = frame_range(a, b); n = f1 - f0; dur = n / FPS
    film = Film(hash(key) % 1000)
    if key == 'comobluff':
        cues = (T('Equipes rivais') - a, T('desviam cargas de trem') - a, T('destroem os ossos') - a, T('É ciência feita') - a - 0.25)
    def make(fi):
        t = fi / FPS
        flash = 0.0
        if key == 'elasmo':
            img = elasmo_frame(t, dur, fi)
        else:
            img = comobluff_frame(t, dur, fi, cues)
            if img is None: img = comobluff_title()
            bd = t - cues[3]
            if 0 <= bd < 0.25: flash = 1 - bd / 0.25
        return film.apply(img, fi, t, dur, flash)
    if still_times:
        for t in still_times:
            make(int(t * FPS)).save(os.path.join(BUILD, f'vstill_{key}_{t:05.2f}.jpg'), quality=90)
        return
    out = os.path.join(BUILD, f'vintage_{key}.mp4')
    p = subprocess.Popen(['ffmpeg', '-y', '-loglevel', 'error', '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-s', f'{W}x{H}',
                          '-r', str(FPS), '-i', '-', '-c:v', 'libx264', '-preset', 'medium', '-crf', '17', '-pix_fmt', 'yuv420p', out],
                         stdin=subprocess.PIPE)
    for fi in range(n): p.stdin.write(make(fi).tobytes())
    p.stdin.close(); p.wait()
    print(f'{out}: {n} frames ({dur:.2f}s), início no frame {f0}')

if __name__ == '__main__':
    win = insert_windows()
    if sys.argv[1] == 'stills':
        key = sys.argv[2]; a, b = win[key]
        render_insert(key, a, b, [float(x) for x in sys.argv[3].split(',')])
    elif sys.argv[1] == 'render':
        for key, (a, b) in win.items(): render_insert(key, a, b)
