#!/usr/bin/env python3
"""BOARD ENGINE — A Guerra dos Ossos (Charlie Dark Lab)

Quadro de evidências com câmera contínua, cartões com alfinete, etiquetas
datilografadas, barbantes vermelhos, círculos tremidos, carimbos, cartões de ano,
tese e título final com glitch.

Uso:
  python3 board_engine.py stills 12.5,40,77        -> build/still_XXX.jpg
  python3 board_engine.py sheet                    -> build/contact_sheet.jpg (1 still por beat)
  python3 board_engine.py mapgrid                  -> build/map_grid.jpg
  python3 board_engine.py render [--workers 4]     -> build/board.mp4
  python3 board_engine.py beats                    -> imprime beats/tempos (JSON em build/beats.json)

Maquinário (não mexer) no topo; DADOS DO VÍDEO no bloco "DATA".
"""
import json, math, os, sys, subprocess, random, unicodedata, re
from functools import lru_cache
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageOps, ImageChops

HERE = os.path.dirname(os.path.abspath(__file__))
BUILD = os.path.join(HERE, 'build'); os.makedirs(BUILD, exist_ok=True)
FONTS = os.path.join(HERE, 'fonts')
PHOTOS = os.path.join(HERE, 'assets', 'photos')
W, H, FPS = 1920, 1080, 30
RED = (208, 49, 45)
INK = (28, 24, 20)

def F(name, size):
    return _font(name, int(size))

@lru_cache(maxsize=256)
def _font(name, size):
    return ImageFont.truetype(os.path.join(FONTS, name), size)

TYPE = 'SpecialElite.woff'; BEBAS = 'BebasNeue.woff'; OSW = 'Oswald-Bold.woff'
PLAY = 'Playfair.woff'; PLAYB = 'Playfair-Bold.woff'; FELL = 'IMFellSC.woff'

# ════════════════════════════════════════════════════════════════════════════
# TEMPO (palavras alinhadas)
# ════════════════════════════════════════════════════════════════════════════
_WJ = json.load(open(os.path.join(BUILD, 'words.json'), encoding='utf-8'))
WORDS = _WJ['words']; DURATION = _WJ['duration']

def _norm(s):
    s = unicodedata.normalize('NFD', s.lower())
    s = ''.join(c for c in s if unicodedata.category(c) != 'Mn')
    return re.sub(r'[^a-z0-9]', '', s)

_NW = [_norm(w['w']) for w in WORDS]

def T(phrase, occ=1, end=False, offset=0.0):
    """Instante (s) em que a frase começa (ou termina, end=True) na narração."""
    toks = [_norm(x) for x in phrase.split() if _norm(x)]
    n, found = len(toks), 0
    for i in range(len(_NW) - n + 1):
        if _NW[i:i + n] == toks:
            found += 1
            if found == occ:
                return (WORDS[i + n - 1]['t1'] if end else WORDS[i]['t0']) + offset
    raise KeyError(f'frase não encontrada no roteiro: {phrase!r}')

# ════════════════════════════════════════════════════════════════════════════
# UTILIDADES
# ════════════════════════════════════════════════════════════════════════════
def clamp(x, a=0.0, b=1.0): return a if x < a else b if x > b else x
def smooth(x): x = clamp(x); return x * x * x * (x * (x * 6 - 15) + 10)
def ease_out(x): x = clamp(x); return 1 - (1 - x) ** 3
def ease_out_back(x, s=1.4):
    x = clamp(x); x -= 1; return x * x * ((s + 1) * x + s) + 1
def rot(px, py, deg):
    a = math.radians(deg); c, s = math.cos(a), math.sin(a)
    return px * c - py * s, px * s + py * c

def noise2(h, w, scale, seed):
    rng = np.random.default_rng(seed)
    sh, sw = max(2, h // scale + 2), max(2, w // scale + 2)
    g = Image.fromarray((rng.random((sh, sw)) * 255).astype(np.uint8))
    return np.asarray(g.resize((w, h), Image.BICUBIC), np.float32) / 255.0

def paper_texture(w, h, tone=(232, 221, 196), seed=1, stain=0.5, edge=0.35):
    n = (noise2(h, w, 60, seed) * 0.5 + noise2(h, w, 12, seed + 1) * 0.3 + noise2(h, w, 3, seed + 2) * 0.2)
    base = np.array(tone, np.float32)[None, None, :] * (0.90 + 0.14 * n[..., None])
    if stain:
        st = noise2(h, w, 140, seed + 7); st = np.clip((st - 0.62) * 3.0, 0, 1) * stain
        base *= (1 - 0.18 * st[..., None]); base[..., 2] *= (1 - 0.10 * st)
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    d = np.minimum.reduce([xx, yy, w - 1 - xx, h - 1 - yy]) / (0.12 * min(w, h) + 1)
    base *= (1 - edge * np.clip(1 - d, 0, 1) ** 2)[..., None]
    return Image.fromarray(np.clip(base, 0, 255).astype(np.uint8))

# ════════════════════════════════════════════════════════════════════════════
# CARTÕES (sprites no mundo) + GEOMETRIA DE PRECISÃO
# ════════════════════════════════════════════════════════════════════════════
class Card:
    """Sprite no mundo. img = conteúdo (RGBA). x,y = centro no mundo; rot em graus."""
    def __init__(self, cid, img, x, y, rot=0.0, scale=1.0, t_in=-1.0, pin=(0.0, -0.46), shadow=True,
                 drop=True, z=0, meta=None):
        self.id, self.img, self.x, self.y, self.rot, self.scale = cid, img, x, y, rot, scale
        self.t_in, self.pin, self.z, self.meta, self.drop = t_in, pin, z, meta, drop
        self.w, self.h = img.size
        self.pad = 40 if shadow else 0
        self.sprite = add_shadow(img, self.pad) if shadow else img

def add_shadow(img, pad):
    w, h = img.size
    out = Image.new('RGBA', (w + 2 * pad, h + 2 * pad), (0, 0, 0, 0))
    a = img.split()[3]
    sh = Image.new('L', out.size, 0); sh.paste(a, (pad + 10, pad + 16))
    sh = sh.filter(ImageFilter.GaussianBlur(14)).point(lambda v: int(v * 0.62))
    out.paste(Image.new('RGBA', out.size, (0, 0, 0, 255)), (0, 0), sh)
    out.alpha_composite(img, (pad, pad))
    return out

def card_local_to_world(cd, px, py):
    """Pixel (px,py) da imagem de conteúdo do cartão -> ponto no mundo (já rotacionado)."""
    dx, dy = (px - cd.w / 2) * cd.scale, (py - cd.h / 2) * cd.scale
    rx, ry = rot(dx, dy, cd.rot)
    return cd.x + rx, cd.y + ry

def card_anchor(cd, u, v):
    """u,v normalizados em [-0.5,+0.5] -> mundo. (0,-0.46)=alfinete do topo; (0.48,0)=borda direita."""
    return card_local_to_world(cd, (u + 0.5) * cd.w, (v + 0.5) * cd.h)

def make_paper_tracked(lines, width, tone=(232, 221, 196), margin=(56, 52), seed=3, gap=1.0,
                       min_h=0, decor=None):
    """Bilhete/telegrama/carta. lines = [(texto, fonte, tamanho, cor, alinhamento)].
    Retorna (img RGBA, meta) com caixa delimitadora exata e linha de base de cada linha renderizada."""
    mx, my = margin
    tmp = ImageDraw.Draw(Image.new('L', (8, 8)))
    rows, y = [], my
    for (txt, fn, sz, col, al) in lines:
        f = F(fn, sz)
        if txt == '':
            y += int(sz * 0.7 * gap); rows.append(None); continue
        bb = tmp.textbbox((0, 0), txt, font=f)
        asc, desc = f.getmetrics()
        tw = bb[2] - bb[0]
        x = mx if al == 'l' else (width - tw) // 2 if al == 'c' else width - mx - tw
        rows.append((txt, f, col, x - bb[0], y, asc))
        y += int((asc + desc) * 1.12 * gap)
    hgt = max(min_h, y + my)
    img = paper_texture(width, hgt, tone, seed).convert('RGBA')
    d = ImageDraw.Draw(img)
    if decor: decor(img, d)
    meta = {'lines': []}
    for r in rows:
        if r is None: meta['lines'].append(None); continue
        txt, f, col, x, yy, asc = r
        d.text((x, yy), txt, font=f, fill=col)
        bb = d.textbbox((x, yy), txt, font=f)
        meta['lines'].append({'bbox': bb, 'baseline': yy + asc, 'text': txt})
    return img, meta

def text_underline_world(cd, meta, i, gap=7, ext=6):
    L = meta['lines'][i]; x0, _, x1, _ = L['bbox']; yb = L['baseline'] + gap
    return card_local_to_world(cd, x0 - ext, yb), card_local_to_world(cd, x1 + ext, yb)

def text_circle_world(cd, meta, i, margin=20):
    x0, y0, x1, y1 = meta['lines'][i]['bbox']
    cx, cy = card_local_to_world(cd, (x0 + x1) / 2, (y0 + y1) / 2)
    rx = ((x1 - x0) / 2 + margin * 1.5) * cd.scale; ry = ((y1 - y0) / 2 + margin) * cd.scale
    return (cx, cy), rx, ry, cd.rot

def bbox_circle_world(cd, box, margin=16):
    x0, y0, x1, y1 = box
    cx, cy = card_local_to_world(cd, (x0 + x1) / 2, (y0 + y1) / 2)
    return (cx, cy), ((x1 - x0) / 2 + margin) * cd.scale, ((y1 - y0) / 2 + margin) * cd.scale, cd.rot

# ── construtores de cartões ────────────────────────────────────────────────
def archival_grade(im, seed=0):
    g = ImageOps.grayscale(im)
    g = ImageOps.autocontrast(g, cutoff=1)
    a = np.asarray(g, np.float32) / 255
    a = np.clip((a - 0.5) * 1.12 + 0.5, 0, 1) ** 1.05
    n = noise2(a.shape[0], a.shape[1], 2, seed) - 0.5
    a = np.clip(a + n * 0.06, 0, 1)
    rgb = np.stack([a * 240 + 10, a * 232 + 12, a * 214 + 16], -1)   # gelatina e prata, levemente quente
    return Image.fromarray(rgb.astype(np.uint8))

def photo_card(pid, name, size=(470, 590), border=26, bottom=70, seed=0, caption=None):
    pw, ph = size
    path = None
    for ext in ('.jpg', '.jpeg', '.png', '.webp'):
        p = os.path.join(PHOTOS, pid + ext)
        if os.path.exists(p): path = p; break
    W_, H_ = pw + 2 * border, ph + border + bottom
    card = paper_texture(W_, H_, (226, 214, 188), seed + 50, stain=0.35, edge=0.25).convert('RGBA')
    if path:
        src = Image.open(path).convert('RGB')
        src = ImageOps.fit(src, (pw, ph), Image.LANCZOS, centering=(0.5, 0.32))
        ph_img = archival_grade(src, seed)
    else:   # marcador provisório (nunca vai para o corte final)
        ph_img = Image.new('RGB', (pw, ph), (58, 56, 52)); d = ImageDraw.Draw(ph_img)
        for k in range(-ph, pw, 28): d.line([(k, 0), (k + ph, ph)], fill=(68, 66, 62), width=6)
        d.text((pw / 2, ph / 2 - 40), 'FOTO DE ARQUIVO', font=F(TYPE, 34), fill=(200, 195, 185), anchor='mm')
        d.text((pw / 2, ph / 2 + 4), 'A INSERIR', font=F(TYPE, 34), fill=(200, 195, 185), anchor='mm')
        d.text((pw / 2, ph / 2 + 60), name, font=F(TYPE, 22), fill=RED, anchor='mm')
    card.paste(ph_img, (border, border))
    d = ImageDraw.Draw(card)
    d.rectangle([border - 1, border - 1, border + pw, border + ph], outline=(90, 80, 66), width=2)
    if caption:
        d.text((W_ / 2, border + ph + bottom / 2), caption, font=F(TYPE, 26), fill=INK, anchor='mm')
    return card

def index_card(lines, width=420, seed=0, ruled=True, tone=(238, 230, 210)):
    def decor(img, d):
        if not ruled: return
        w, h = img.size
        d.line([(0, 62), (w, 62)], fill=(200, 90, 90), width=2)
        for yy in range(100, h - 10, 38): d.line([(0, yy), (w, yy)], fill=(150, 170, 200), width=1)
    return make_paper_tracked(lines, width, tone, margin=(30, 18), seed=seed, decor=decor)

def label_img(text, size=30, n=None):
    """Etiqueta datilografada (fita branca). n = caracteres já 'datilografados'."""
    f = F(TYPE, size)
    full = ImageDraw.Draw(Image.new('L', (8, 8))).textbbox((0, 0), text, font=f)
    w = full[2] - full[0] + 36; h = int(size * 1.55)
    im = paper_texture(w, h, (244, 240, 230), 77, stain=0, edge=0.1).convert('RGBA')
    d = ImageDraw.Draw(im)
    shown = text if n is None else text[:n]
    d.text((18 - full[0], (h - size) / 2 - 2), shown, font=f, fill=INK)
    return im

@lru_cache(maxsize=64)
def stamp_img(text, size=92, seed=0):
    f = F(OSW, size)
    bb = ImageDraw.Draw(Image.new('L', (8, 8))).textbbox((0, 0), text, font=f)
    tw, th = bb[2] - bb[0], bb[3] - bb[1]
    w, h = tw + 70, th + 64
    m = Image.new('L', (w, h), 0); d = ImageDraw.Draw(m)
    d.rounded_rectangle([6, 6, w - 7, h - 7], radius=10, outline=255, width=8)
    d.text((35 - bb[0], 32 - bb[1]), text, font=f, fill=255)
    n = noise2(h, w, 3, seed + 11) * 0.6 + noise2(h, w, 18, seed + 12) * 0.4
    a = np.asarray(m, np.float32) / 255 * np.clip((n - 0.18) * 2.2, 0, 1) * 0.92
    out = np.zeros((h, w, 4), np.uint8); out[..., 0], out[..., 1], out[..., 2] = RED
    out[..., 3] = (a * 255).astype(np.uint8)
    return Image.fromarray(out)

# ════════════════════════════════════════════════════════════════════════════
# MAPA (gerado por código — sem pessoas)
# ════════════════════════════════════════════════════════════════════════════
MAP_LAT = (24.5, 49.6); MAP_LON = (-125.5, -66.0); MAP_W, MAP_H = 3200, 1720

def map_px(lat, lon):
    x = (lon - MAP_LON[0]) / (MAP_LON[1] - MAP_LON[0]) * MAP_W
    y = (MAP_LAT[1] - lat) / (MAP_LAT[1] - MAP_LAT[0]) * MAP_H
    return x, y

def build_map():
    cache = os.path.join(BUILD, 'map.png')
    if os.path.exists(cache): return Image.open(cache).convert('RGBA')
    from global_land_mask import globe
    sw, sh = MAP_W // 2, MAP_H // 2
    lats = np.linspace(MAP_LAT[1], MAP_LAT[0], sh); lons = np.linspace(MAP_LON[0], MAP_LON[1], sw)
    LO, LA = np.meshgrid(lons, lats)
    land = globe.is_land(LA, LO).astype(np.uint8) * 255
    lm = Image.fromarray(land).resize((MAP_W, MAP_H), Image.BICUBIC).filter(ImageFilter.GaussianBlur(2))
    la = np.asarray(lm, np.float32) / 255
    paper = np.asarray(paper_texture(MAP_W, MAP_H, (222, 205, 168), 21, stain=0.8, edge=0.5), np.float32)
    landf = np.clip((la - 0.5) * 6 + 0.5, 0, 1)[..., None]
    sea = paper * np.array([0.80, 0.82, 0.80])
    img = sea * (1 - landf) + paper * landf
    coast = np.clip(1 - np.abs(la - 0.5) * 7, 0, 1)
    img = img * (1 - 0.75 * coast[..., None]) + np.array([60, 44, 30]) * 0.75 * coast[..., None]
    out = Image.fromarray(np.clip(img, 0, 255).astype(np.uint8)).convert('RGBA')
    d = ImageDraw.Draw(out)
    gcol = (120, 96, 66)
    for lon in range(-125, -64, 5):
        x, _ = map_px(0, lon); d.line([(x, 0), (x, MAP_H)], fill=gcol + (90,), width=2)
    for lat in range(25, 50, 5):
        _, y = map_px(lat, 0); d.line([(0, y), (MAP_W, y)], fill=gcol + (90,), width=2)
    # ondas no mar (hachuras)
    rng = random.Random(4)
    for _ in range(260):
        lat, lon = rng.uniform(25, 49), rng.uniform(-125, -66)
        if globe.is_land(lat, lon): continue
        x, y = map_px(lat, lon)
        d.arc([x - 16, y - 6, x + 16, y + 6], 200, 340, fill=(110, 100, 84), width=2)
    # Montanhas Rochosas (símbolos)
    for k in range(60):
        lat = 33 + (k % 15) * 1.0 + rng.uniform(-0.3, 0.3); lon = -106.9 - (k // 15) * 1.15 - (lat - 33) * 0.42 + rng.uniform(-0.3, 0.3)
        x, y = map_px(lat, lon)
        d.line([(x - 18, y + 10), (x, y - 14), (x + 18, y + 10)], fill=(92, 72, 50), width=3)
    f = F(FELL, 46); fs = F(FELL, 32)
    d.text((MAP_W / 2, 70), 'ESTADOS UNIDOS — FRONTEIRA DOS OSSOS', font=F(FELL, 64), fill=(60, 42, 26), anchor='mm')
    d.text((MAP_W / 2, 126), 'Mapa esquemático · 1868 – 1892', font=fs, fill=(90, 66, 44), anchor='mm')
    for txt, lat, lon in [('TERRITÓRIO DO WYOMING', 43.3, -108.0), ('COLORADO', 37.6, -106.2),
                          ('OCEANO PACÍFICO', 33.0, -121.5), ('OCEANO ATLÂNTICO', 33.5, -71.5),
                          ('MONTANHAS ROCHOSAS', 47.6, -117.5)]:
        x, y = map_px(lat, lon); d.text((x, y), txt, font=fs, fill=(80, 60, 40), anchor='mm')
    # rosa dos ventos
    cx, cy = MAP_W - 260, MAP_H - 250
    for a, L in [(0, 110), (90, 110), (180, 110), (270, 110), (45, 60), (135, 60), (225, 60), (315, 60)]:
        dx, dy = rot(0, -L, a); px, py = rot(10, 0, a)
        d.polygon([(cx + dx, cy + dy), (cx + px, cy + py), (cx - px, cy - py)], fill=(70, 50, 32))
    d.text((cx, cy - 140), 'N', font=f, fill=(70, 50, 32), anchor='mm')
    d.rectangle([14, 14, MAP_W - 15, MAP_H - 15], outline=(70, 50, 32), width=6)
    d.rectangle([30, 30, MAP_W - 31, MAP_H - 31], outline=(70, 50, 32), width=2)
    out.save(cache)
    return out

# ════════════════════════════════════════════════════════════════════════════
# FUNDO DO QUADRO + mipmaps
# ════════════════════════════════════════════════════════════════════════════
WORLD_W, WORLD_H = 8400, 5400

def build_board_bg():
    cache = os.path.join(BUILD, 'board_bg.jpg')
    if os.path.exists(cache): return Image.open(cache).convert('RGB')
    h, w = WORLD_H // 2, WORLD_W // 2
    n = noise2(h, w, 300, 5) * 0.4 + noise2(h, w, 40, 6) * 0.3 + noise2(h, w, 4, 7) * 0.3
    speck = (np.random.default_rng(8).random((h, w)) > 0.985).astype(np.float32)
    base = np.array([44, 36, 30], np.float32) * (0.78 + 0.45 * n[..., None]) - speck[..., None] * 14
    img = Image.fromarray(np.clip(base, 0, 255).astype(np.uint8)).resize((WORLD_W, WORLD_H), Image.BICUBIC)
    img.save(cache, quality=92)
    return img

# ════════════════════════════════════════════════════════════════════════════
# OVERLAYS VETORIAIS (no mundo) — barbantes, círculos, sublinhados, alfinetes
# ════════════════════════════════════════════════════════════════════════════
class Vec:
    def __init__(self, kind, t_in, dur, **kw):
        self.kind, self.t_in, self.dur, self.kw = kind, t_in, dur, kw

def string(p0, p1, t_in, dur=0.7, sag=0.06): return Vec('string', t_in, dur, p0=p0, p1=p1, sag=sag)
def circle(c, rx, ry, rr, t_in, dur=0.65, seed=0, width=7): return Vec('circle', t_in, dur, c=c, rx=rx, ry=ry, rr=rr, seed=seed, width=width)
def underline(p0, p1, t_in, dur=0.45, seed=0): return Vec('underline', t_in, dur, p0=p0, p1=p1, seed=seed)
def pin(p, t_in): return Vec('pin', t_in, 0.2, p=p)

def string_pts(p0, p1, sag, n=48):
    (x0, y0), (x1, y1) = p0, p1
    L = math.hypot(x1 - x0, y1 - y0)
    return [(x0 + (x1 - x0) * k / n, y0 + (y1 - y0) * k / n + sag * L * 4 * (k / n) * (1 - k / n)) for k in range(n + 1)]

def circle_pts(v, prog):
    c, rx, ry, rr, seed = v.kw['c'], v.kw['rx'], v.kw['ry'], v.kw['rr'], v.kw['seed']
    rng = random.Random(seed); ph = rng.uniform(0, 6.28); a0 = rng.uniform(-2.6, -2.0)
    turns = 1.12; n = int(90 * prog) + 2
    pts = []
    for k in range(n):
        a = a0 + 2 * math.pi * turns * prog * k / (n - 1)
        grow = 1 + 0.06 * (a - a0) / (2 * math.pi)
        wob = 1 + 0.025 * math.sin(3 * a + ph) + 0.015 * math.sin(7 * a + ph * 2)
        x, y = rx * grow * wob * math.cos(a), ry * grow * wob * math.sin(a)
        x, y = rot(x, y, rr)
        pts.append((c[0] + x, c[1] + y))
    return pts

# ════════════════════════════════════════════════════════════════════════════
# CÂMERA
# ════════════════════════════════════════════════════════════════════════════
class Camera:
    def __init__(self, keys):
        self.keys = sorted(keys, key=lambda k: k[0])   # (t, x, y, zoom, rot, [dur_transição])
    def at(self, t):
        ks = self.keys
        if t <= ks[0][0]: k = ks[0]; x, y, z, r = k[1:5]
        else:
            x, y, z, r = ks[-1][1:5]
            for a, b in zip(ks, ks[1:]):
                if a[0] <= t < b[0]:
                    move = b[5] if len(b) > 5 else min(1.4, b[0] - a[0])
                    start = b[0] - move
                    u = smooth((t - start) / move) if t >= start else 0.0
                    # transição em escala logarítmica para o zoom (sensação de dolly)
                    z = math.exp(math.log(a[3]) + (math.log(b[3]) - math.log(a[3])) * u)
                    x = a[1] + (b[1] - a[1]) * u; y = a[2] + (b[2] - a[2]) * u; r = a[4] + (b[4] - a[4]) * u
                    break
        # deriva contínua (a câmera nunca para)
        x += 14 * math.sin(t * 0.31) / z; y += 10 * math.sin(t * 0.23 + 1) / z
        z *= 1 + 0.012 * math.sin(t * 0.17); r += 0.25 * math.sin(t * 0.13)
        return x, y, z, r

def w2s(p, cam):
    cx, cy, z, r = cam
    dx, dy = rot(p[0] - cx, p[1] - cy, -r)
    return dx * z + W / 2, dy * z + H / 2

# ════════════════════════════════════════════════════════════════════════════
# ════════════════════════════  DATA  (Guerra dos Ossos)  ════════════════════
# ════════════════════════════════════════════════════════════════════════════
def build_scene():
    S = {'cards': [], 'vecs': [], 'labels': [], 'stamps': [], 'overlays': [], 'cam': [], 'beats': [], 'inserts': []}
    C = {}
    def add(cd): S['cards'].append(cd); C[cd.id] = cd; return cd
    def beat(name, t): S['beats'].append((name, round(t, 2)))

    # ── mapa ─────────────────────────────────────────────────────────────
    mp = build_map()
    MAPX, MAPY, MAPR, MAPS = 5450, 1350, -0.8, 1.0
    add(Card('map', mp, MAPX, MAPY, MAPR, MAPS, t_in=-1, pin=None, drop=False, z=-5))
    def on_map(lat, lon):
        x, y = map_px(lat, lon); return card_local_to_world(C['map'], x, y)
    CITY = {'filadelfia': (39.95, -75.17), 'newhaven': (41.31, -72.92), 'novayork': (40.71, -74.00),
            'washington': (38.90, -77.04), 'morrison': (39.65, -105.19), 'canon': (38.44, -105.24),
            'comobluff': (41.90, -106.15)}
    P = {k: on_map(*v) for k, v in CITY.items()}

    # ── Berlim: Cope e Marsh ─────────────────────────────────────────────
    t_berlim = T('Berlim, 1864.')
    add(Card('cope', photo_card('cope', 'Edward Drinker Cope', seed=1, caption='E. D. COPE'), 1150, 1180, -3.0, t_in=t_berlim + 0.6))
    add(Card('marsh', photo_card('marsh', 'Othniel Charles Marsh', seed=2, caption='O. C. MARSH'), 2000, 1200, 2.6, t_in=t_berlim + 1.0))
    ic1, m1 = index_card([('HOMENAGEM DE COPE', TYPE, 24, INK, 'l'), ('', TYPE, 10, INK, 'l'),
                          ('Colosteus marshii', PLAY, 34, INK, 'l'), ('Cope, 1867', TYPE, 24, (80, 70, 60), 'l')], 400, 31)
    ic2, m2 = index_card([('HOMENAGEM DE MARSH', TYPE, 24, INK, 'l'), ('', TYPE, 10, INK, 'l'),
                          ('Mosasaurus copeanus', PLAY, 34, INK, 'l'), ('Marsh, 1869', TYPE, 24, (80, 70, 60), 'l')], 420, 32)
    t_bat = T('batizar espécies')
    add(Card('hom_cope', ic1, 1120, 1830, 2.0, t_in=t_bat - 0.2, meta=m1, z=1))
    add(Card('hom_marsh', ic2, 1990, 1850, -2.2, t_in=t_bat + 0.4, meta=m2, z=1))

    # ── Haddonfield ──────────────────────────────────────────────────────
    t_hadd = T('A primeira rachadura')
    note, mn = make_paper_tracked([
        ('HADDONFIELD, N.J. — 1868', TYPE, 30, INK, 'l'), ('', TYPE, 14, INK, 'l'),
        ('Poços de marga — West Jersey', TYPE, 28, INK, 'l'),
        ('Operários da pedreira:', TYPE, 28, INK, 'l'),
        ('enviar todo fóssil achado', TYPE, 28, INK, 'l'),
        ('ao Prof. Marsh, em Yale.', TYPE, 28, INK, 'l'), ('', TYPE, 14, INK, 'l'),
        ('— pago por O. C. Marsh', TYPE, 28, INK, 'l'), ('', TYPE, 18, INK, 'l'),
        ('reconstituição', TYPE, 18, (120, 105, 90), 'r')], 560, (228, 216, 186), seed=41)
    add(Card('hadd', note, 1180, 2780, -2.5, t_in=t_hadd + 0.3, meta=mn))

    # ── Elasmossauro ─────────────────────────────────────────────────────
    t_elas = T('Cope revida')
    def elas_decor(img, d):
        w, h = img.size; y0 = 250
        # esqueleto "errado": crânio na ponta da cauda (reconstrução esquemática)
        xs = np.linspace(60, w - 60, 46)
        for i, x in enumerate(xs):
            yy = y0 + 40 * math.sin(i / 7.0)
            d.ellipse([x - 7, yy - 7, x + 7, yy + 7], outline=INK, width=3)
        d.ellipse([w / 2 - 70, y0 - 10, w / 2 + 110, y0 + 70], outline=INK, width=4)   # tronco
        for k in range(4):
            fx = w / 2 - 40 + k * 50; d.line([(fx, y0 + 60), (fx - 30 + k * 20, y0 + 130)], fill=INK, width=4)
        d.polygon([(w - 60, y0 - 4), (w - 6, y0 + 12), (w - 60, y0 + 28)], outline=INK, width=4)  # crânio na cauda
    page, mp_ = make_paper_tracked([
        ('TRANSACTIONS', FELL, 46, INK, 'c'), ('of the American Philosophical Society', PLAY, 26, INK, 'c'),
        ('', TYPE, 360, INK, 'l'),
        ('Elasmosaurus platyurus — Cope', PLAY, 30, INK, 'c'),
        ('restauração publicada (1869–70)', TYPE, 22, (80, 70, 60), 'c'), ('', TYPE, 12, INK, 'l'),
        ('reconstituição esquemática', TYPE, 18, (120, 105, 90), 'r')], 820, (236, 228, 204), seed=42,
        decor=elas_decor)
    add(Card('elas', page, 2450, 2760, 1.8, t_in=t_elas - 0.2, meta=mp_))
    t_leidy = T('Joseph Leidy')
    add(Card('leidy', photo_card('leidy', 'Joseph Leidy', size=(380, 470), seed=3, caption='J. LEIDY'), 3330, 2700, -2.0, t_in=t_leidy - 0.1))

    # ── Oeste, 1877 ──────────────────────────────────────────────────────
    t_1877 = T('Em 1877')
    t_lakes = T('Arthur Lakes')
    add(Card('lakes', photo_card('lakes', 'Arthur Lakes', size=(380, 470), seed=4, caption='A. LAKES'), 4150, 2900, 2.4, t_in=t_lakes - 0.1))
    t_carta = T('uma carta chega a Yale')
    letter, ml = make_paper_tracked([
        ('Laramie City, Wyoming — 1877', TYPE, 26, INK, 'r'), ('', TYPE, 10, INK, 'l'),
        ('Prof. O. C. Marsh — Yale College', TYPE, 26, INK, 'l'), ('', TYPE, 10, INK, 'l'),
        ('Encontramos grande número de', TYPE, 26, INK, 'l'),
        ('ossos fósseis perto da ferrovia', TYPE, 26, INK, 'l'),
        ('em Como Bluff. Guardamos sigilo.', TYPE, 26, INK, 'l'), ('', TYPE, 14, INK, 'l'),
        ('Harlow & Edwards', PLAY, 40, INK, 'r'), ('', TYPE, 12, INK, 'l'),
        ('reconstituição', TYPE, 18, (120, 105, 90), 'r')], 600, (230, 220, 192), seed=43)
    add(Card('carta', letter, 5250, 3020, -1.8, t_in=t_carta + 0.2, meta=ml))
    t_reed = T('William Harlow Reed')
    add(Card('reed', photo_card('reed', 'William Harlow Reed', size=(380, 470), seed=5, caption='W. H. REED'), 6280, 2930, 2.0, t_in=t_reed - 0.1))

    # ── Rede de espécies ─────────────────────────────────────────────────
    t_nomes = T('nascem os nomes')
    hdr_m, _ = index_card([('MARSH', BEBAS, 70, RED, 'c'), ('Yale', TYPE, 24, INK, 'c')], 300, 60, ruled=False)
    hdr_c, _ = index_card([('COPE', BEBAS, 70, RED, 'c'), ('Filadélfia', TYPE, 24, INK, 'c')], 300, 61, ruled=False)
    add(Card('net_marsh', hdr_m, 6550, 4350, -1.5, t_in=t_nomes, z=2))
    add(Card('net_cope', hdr_c, 4350, 4350, 1.5, t_in=t_nomes + 0.3, z=2))
    species = [  # (id, nome, ano, autor, palavra-gatilho, posição)
        ('esteg', 'ESTEGOSSAURO', 1877, 'marsh', 'Estegossauro', (7250, 3800)),
        ('alos', 'ALOSSAURO', 1877, 'marsh', 'Alossauro', (7500, 4250)),
        ('apato', 'APATOSSAURO', 1877, 'marsh', 'Apatossauro', (7350, 4720)),
        ('diplo', 'DIPLÓDOCO', 1878, 'marsh', 'Diplódoco', (6800, 4980)),
        ('trice', 'TRICERÁTOPS', 1889, 'marsh', 'Tricerátops', (6050, 4980)),
        ('bronto', 'BRONTOSSAURO', 1879, 'marsh', 'Brontossauro', (7700, 5120)),
        ('camara', 'CAMARASSAURO', 1877, 'cope', 'Camarassauro', (3650, 3800)),
        ('dimetro', 'DIMETRODONTE', 1878, 'cope', 'Dimetrodonte', (3450, 4380)),
        ('celo', 'CELÓFISE', 1889, 'cope', 'Celófise', (3800, 4930)),
    ]
    for i, (sid, nm, yr, au, trig, (x, y)) in enumerate(species):
        img, mm = index_card([(nm, OSW, 36, INK, 'l'), (f'{"Marsh" if au == "marsh" else "Cope"}, {yr}', TYPE, 24, (80, 70, 60), 'l')], 360, 70 + i)
        cd = add(Card(sid, img, x, y, random.Random(i).uniform(-4, 4), t_in=T(trig) - 0.15, meta=mm, z=2))
        hub = C['net_' + au]; sg = 1 if au == 'marsh' else -1
        S['vecs'].append(string(card_anchor(hub, 0.47 * sg, 0.0), card_anchor(cd, -0.47 * sg, 0.0), cd.t_in + 0.1, 0.5, 0.04))
    t_136 = T('cento e trinta e seis')
    big, mb = make_paper_tracked([('136', BEBAS, 150, RED, 'c'), ('espécies novas de dinossauros', TYPE, 28, INK, 'c')],
                                 520, (238, 230, 210), seed=90)
    add(Card('n136', big, 5450, 4430, 0.8, t_in=t_136, meta=mb, z=3))

    # ── 1890: o Herald ───────────────────────────────────────────────────
    t_1890 = T('doze de janeiro de 1890')
    t_herald = T('O New York Herald')
    def herald_decor(img, d):
        w, h = img.size
        d.line([(40, 150), (w - 40, 150)], fill=INK, width=4); d.line([(40, 160), (w - 40, 160)], fill=INK, width=1)
        for k in range(14):
            yy = 470 + k * 26
            for col in range(3):
                x0 = 50 + col * (w - 80) / 3
                d.line([(x0 + 8, yy), (x0 + (w - 80) / 3 - 14 - (k * 13 % 60), yy)], fill=(110, 100, 90), width=5)
    herald, mh = make_paper_tracked([
        ('THE NEW YORK HERALD', FELL, 64, INK, 'c'), ('NOVA YORK, DOMINGO, 12 DE JANEIRO DE 1890', TYPE, 20, INK, 'c'),
        ('', TYPE, 30, INK, 'l'),
        ('SCIENTISTS WAGE BITTER WARFARE', OSW, 50, INK, 'c'),
        ('“Cientistas travam uma guerra amarga”', PLAY, 30, INK, 'c'), ('', TYPE, 16, INK, 'l'),
        ('PLÁGIO · INCOMPETÊNCIA · ROUBO DE MÉRITO', TYPE, 28, INK, 'c'),
        ('', TYPE, 330, INK, 'l')], 900, (226, 218, 196), seed=44, decor=herald_decor)
    add(Card('herald', herald, 1500, 4300, -1.2, t_in=t_herald - 0.6, meta=mh))
    ball, mbl = index_card([('O JORNALISTA', TYPE, 24, INK, 'l'), ('', TYPE, 8, INK, 'l'),
                            ('William Hosea', PLAY, 34, INK, 'l'), ('Ballou', PLAY, 34, INK, 'l'),
                            ('recebe o diário de Cope', TYPE, 22, (80, 70, 60), 'l')], 380, 33)
    add(Card('ballou', ball, 2480, 3880, 3.0, t_in=T('William Hosea Ballou') - 0.2, meta=mbl))

    # ── 1892 ─────────────────────────────────────────────────────────────
    t_1892 = T('O escândalo não poupa')
    tele, mt = make_paper_tracked([
        ('WESTERN UNION TELEGRAPH', OSW, 30, (90, 60, 40), 'c'), ('', TYPE, 10, INK, 'l'),
        ('WASHINGTON · 1892', TYPE, 26, INK, 'l'), ('', TYPE, 8, INK, 'l'),
        ('CONGRESSO CORTA VERBA DO', TYPE, 28, INK, 'l'),
        ('SERVIÇO GEOLÓGICO PT', TYPE, 28, INK, 'l'),
        ('PALEONTOLOGIA DE MARSH EXTINTA PT', TYPE, 28, INK, 'l'), ('', TYPE, 10, INK, 'l'),
        ('reconstituição', TYPE, 18, (120, 105, 90), 'r')], 640, (232, 222, 176), seed=45)
    add(Card('tele', tele, 2600, 4650, 1.6, t_in=t_1892 + 0.2, meta=mt))
    col, mc = index_card([('COLEÇÃO DE FÓSSEIS', OSW, 30, INK, 'l'), ('E. D. Cope · Filadélfia', TYPE, 24, (80, 70, 60), 'l')], 400, 34)
    add(Card('colecao', col, 3020, 4160, -2.6, t_in=T('Cope é obrigado a vender') - 0.2, meta=mc))

    # ════════ BARBANTES, CÍRCULOS, SUBLINHADOS ═══════════════════════════
    V = S['vecs']
    cope, marsh = C['cope'], C['marsh']
    V.append(string(card_anchor(cope, 0.0, -0.46), card_anchor(marsh, 0.0, -0.46), T('Os dois são apaixonados'), 0.9, 0.05))
    c_, rx, ry, rr = text_circle_world(C['hom_cope'], m1, 2, 14); V.append(circle(c_, rx, ry, rr, T('um em homenagem'), seed=1))
    c_, rx, ry, rr = text_circle_world(C['hom_marsh'], m2, 2, 14); V.append(circle(c_, rx, ry, rr, T('um em homenagem', offset=0.5), seed=2))
    V.append(string(card_anchor(marsh, -0.46, 0.40), card_anchor(C['hadd'], 0.46, -0.44), T('Marsh visita o local'), 0.9, 0.05))
    p0, p1 = text_underline_world(C['hadd'], mn, 4); V.append(underline(p0, p1, T('Marsh tinha pago'), seed=3))
    p0, p1 = text_underline_world(C['hadd'], mn, 7); V.append(underline(p0, p1, T('Marsh tinha pago', offset=0.7), seed=4))
    # crânio na cauda (caixa conhecida no decor: x de w-60 a w-6, y0-4..y0+28; topo da página = linhas)
    hdr_h = mp_['lines'][1]['bbox'][3]
    skull_box = (820 - 72, 250 - 14, 820 - 2, 250 + 38)
    c_, rx, ry, rr = bbox_circle_world(C['elas'], skull_box, 18); V.append(circle(c_, rx, ry, rr, T('Marsh aponta o erro'), seed=5))
    V.append(string(card_anchor(C['leidy'], -0.47, 0.0), card_anchor(C['elas'], 0.47, 0.28), T('O paleontólogo Joseph Leidy', end=True), 0.7, 0.05))
    # 1877
    V.append(string(card_anchor(C['lakes'], 0.0, -0.46), P['morrison'], T('envia amostras'), 0.9, 0.03))
    V.append(string(card_anchor(C['carta'], 0.0, -0.46), P['comobluff'], T('em Como Bluff, no Wyoming'), 0.9, 0.03))
    V.append(string(card_anchor(C['reed'], 0.0, -0.46), card_anchor(C['carta'], 0.46, -0.30), T('Um deles se chama', end=True), 0.6, 0.06))
    p0, p1 = text_underline_world(C['carta'], ml, 8); V.append(underline(p0, p1, T('com nomes falsos'), seed=6))
    c_, rx, ry, rr = text_circle_world(C['carta'], ml, 8, 16); V.append(circle(c_, rx, ry, rr, T('com nomes falsos', offset=0.45), seed=7))
    for k in ('filadelfia', 'newhaven'):
        V.append(pin(P[k], T('A primeira rachadura')))
    V.append(pin(P['morrison'], T('Em Morrison')))
    V.append(pin(P['canon'], T('Em Morrison', offset=0.5)))
    V.append(pin(P['comobluff'], T('Como Bluff, no Wyoming', offset=-0.3)))
    # Brontossauro = Apatossauro
    c_, rx, ry, rr = text_circle_world(C['bronto'], C['bronto'].meta, 0, 14); V.append(circle(c_, rx, ry, rr, T('o mesmo animal'), seed=8))
    V.append(string(card_anchor(C['bronto'], 0.0, -0.46), card_anchor(C['apato'], 0.0, 0.46), T('já tinha descrito'), 0.8, 0.05))
    # Herald
    p0, p1 = text_underline_world(C['herald'], mh, 3); V.append(underline(p0, p1, T('estampa a manchete', end=True), 0.6, seed=9))
    for j, w in enumerate(['Plágio', 'incompetência', 'roubo de mérito']):
        pass
    c_, rx, ry, rr = text_circle_world(C['herald'], mh, 6, 16); V.append(circle(c_, rx, ry, rr, T('Plágio'), 1.6, seed=10))
    V.append(string(card_anchor(C['ballou'], -0.46, 0.0), card_anchor(C['herald'], 0.46, -0.35), T('entrega tudo ao jornalista'), 0.8, 0.04))
    V.append(pin(P['novayork'], T('O New York Herald')))
    V.append(pin(P['washington'], T('o Congresso corta')))
    p0, p1 = text_underline_world(C['tele'], mt, 6); V.append(underline(p0, p1, T('Marsh perde o cargo'), seed=11))

    # ════════ ETIQUETAS (datilografadas) ═════════════════════════════════
    L = S['labels']
    def lab(text, cd, u, v, t, dx=0, dy=0, size=30):
        L.append({'text': text, 'card': cd.id, 'u': u, 'v': v, 'dx': dx, 'dy': dy, 't': t, 'size': size})
    lab('EDWARD DRINKER COPE · 1840', cope, 0, 0.5, T('Edward Drinker Cope', 1), 0, 36)
    lab('OTHNIEL CHARLES MARSH · 1831', marsh, 0, 0.5, T('Othniel Charles Marsh'), 0, 36)
    lab('SOBRINHO DO MAGNATA GEORGE PEABODY', marsh, 0, -0.5, T('sobrinho de um dos'), 0, -34, 24)
    lab('POÇOS DE MARGA — HADDONFIELD', C['hadd'], 0, -0.5, T('nos poços de marga'), 0, -34, 26)
    lab('JOSEPH LEIDY · O ÁRBITRO', C['leidy'], 0, 0.5, T('Joseph Leidy', end=True), 0, 34, 26)
    lab('ARTHUR LAKES · MORRISON, CO', C['lakes'], 0, 0.5, T('Arthur Lakes', end=True), 0, 34, 26)
    lab('WILLIAM HARLOW REED · FERROVIÁRIO', C['reed'], 0, 0.5, T('William Harlow Reed', end=True), 0, 34, 26)
    lab('COMO BLUFF · WYOMING', C['map'], *[(v / s) - 0.5 for v, s in zip(map_px(*CITY['comobluff']), (MAP_W, MAP_H))],
        T('Como Bluff, no Wyoming'), 0, -60, 30)
    lab('MORRISON', C['map'], *[(v / s) - 0.5 for v, s in zip(map_px(*CITY['morrison']), (MAP_W, MAP_H))], T('Em Morrison'), 130, 0, 26)
    lab('CAÑON CITY', C['map'], *[(v / s) - 0.5 for v, s in zip(map_px(*CITY['canon']), (MAP_W, MAP_H))], T('Em Morrison', offset=0.5), 140, 26, 24)
    lab('FILADÉLFIA · COPE', C['map'], *[(v / s) - 0.5 for v, s in zip(map_px(*CITY['filadelfia']), (MAP_W, MAP_H))], T('A primeira rachadura'), -170, 40, 24)
    lab('YALE · MARSH', C['map'], *[(v / s) - 0.5 for v, s in zip(map_px(*CITY['newhaven']), (MAP_W, MAP_H))], T('A primeira rachadura'), -40, -52, 24)
    lab('= APATOSSAURO (MESMO ANIMAL)', C['bronto'], 0, 0.5, T('o mesmo animal', offset=0.4), 0, 32, 22)
    lab('† 1897 · FILADÉLFIA', cope, 0, -0.5, T('morre em 1897'), 0, -34, 28)
    lab('† 1899 · QUASE SEM DINHEIRO', marsh, 0, -0.5, T('Morreu dois anos depois'), 0, -76, 26)

    # ════════ CARIMBOS ═══════════════════════════════════════════════════
    ST = S['stamps']
    def stp(text, cd, u, v, t, r=-12, size=92):
        ST.append({'text': text, 'card': cd.id, 'u': u, 'v': v, 't': t, 'rot': r, 'size': size})
    stp('SUBORNADO', C['hadd'], 0.22, 0.36, T('mandar tudo para ele'), -10)
    stp('HUMILHADO', C['elas'], -0.31, -0.33, T('Humilhado'), -8, 70)
    stp('SILÊNCIO PAGO', C['lakes'], 0.0, 0.18, T('fique em silêncio'), -14, 64)
    stp('NO PODER', marsh, 0.0, 0.28, T('Marsh conquista o poder'), -9)
    stp('FALIDO', cope, 0.0, 0.28, T('Cope perde a fortuna'), 10)
    stp('DEMITIDO', C['tele'], 0.30, 0.47, T('Marsh perde o cargo', offset=0.5), -11)
    stp('VENDIDA', C['colecao'], 0.20, 0.05, T('com prejuízo'), 12, 70)
    stp('LENDA?', cope, -0.18, 0.36, T('Diz a lenda'), -6, 60)

    # ════════ CARTÕES DE ANO / TESE / TÍTULO (tela) ══════════════════════
    O = S['overlays']
    O.append(('year', t_berlim, 2.8, '1864', 'BERLIM'))
    O.append(('year', t_hadd, 2.6, '1868', 'NOVA JERSEY'))
    O.append(('year', t_1877, 2.6, '1877', 'O OESTE AMERICANO'))
    O.append(('year', t_1890 - 0.2, 2.8, '1890', 'NOVA YORK'))
    O.append(('year', t_1892, 2.6, '1892', 'WASHINGTON'))
    t_thesis = T('E mostrou que')
    O.append(('thesis', t_thesis, DURATION - t_thesis - 0.6, 'A maior descoberta da ciência', 'nasceu do pior lado de quem a fez.'))
    S['title_t'] = DURATION - 0.4
    S['end'] = DURATION + 5.0

    # ════════ INSERTS VINTAGE (o board_engine deixa o intervalo para o splice) ══
    S['inserts'] = [('elasmo', T('Mas, ao montar o esqueleto', offset=-0.15), T('Marsh aponta o erro', offset=-0.1)),
                    ('comobluff', T('Como Bluff vira um campo', offset=-0.15), T('E, mesmo assim', offset=-0.1))]

    # ════════ CÂMERA (t, x, y, zoom, rot, [duração do movimento]) ═══════
    K = S['cam']
    def cam_card(t, cid, z, dx=0, dy=0, r=0, mv=None):
        cd = C[cid]; K.append((t, cd.x + dx, cd.y + dy, z, r) + ((mv,) if mv else ()))
    K.append((0.0, 4200, 2700, 0.235, 0))
    K.append((T('Havia espiões'), 5100, 2200, 0.25, 0.5, 4.0))
    K.append((T('E tudo começou'), 1580, 1350, 0.42, -0.5, 2.2))
    K.append((t_berlim + 0.2, 1580, 1300, 0.82, 0, 1.6)); beat('YEAR_CARD 1864 + REVEAL Cope/Marsh', t_berlim)
    cam_card(T('Edward Drinker Cope', 1), 'cope', 1.25, 0, 40, -1); beat('NAME_TAG Cope', T('Edward Drinker Cope', 1))
    cam_card(T('Othniel Charles Marsh'), 'marsh', 1.25, 0, 30, 1); beat('NAME_TAG Marsh', T('Othniel Charles Marsh'))
    K.append((T('Os dois são apaixonados'), 1580, 1250, 0.80, 0, 1.4)); beat('CONNECT Cope–Marsh', T('Os dois são apaixonados'))
    K.append((T('batizar espécies'), 1560, 1700, 0.95, 0, 1.2)); beat('DOC_FOCUS homenagens', T('um em homenagem'))
    K.append((T('Seria a última'), 1560, 1500, 0.70, 0, 2.5))
    K.append((t_hadd, 1450, 2200, 0.52, -1, 1.6)); beat('YEAR_CARD 1868 Haddonfield', t_hadd)
    cam_card(T('Marsh visita o local'), 'hadd', 0.62, 300, -500, 0, 1.6); beat('CONNECT Marsh→bilhete', T('Marsh visita o local'))
    cam_card(T('Pouco depois'), 'hadd', 1.15, 0, 20, -1, 1.6); beat('HIGHLIGHT_LINE bilhete + STAMP SUBORNADO', T('Marsh tinha pago'))
    cam_card(t_elas, 'elas', 0.95, 0, -40, 0.5, 1.5); beat('DOC_FOCUS Elasmossauro', t_elas)
    beat('VINTAGE INSERT 1 — Elasmossauro', S['inserts'][0][1])
    cam_card(T('Marsh aponta o erro', offset=-0.05), 'elas', 1.2, 280, -60, 0, 0.1); beat('CIRCLE crânio na cauda', T('Marsh aponta o erro'))
    K.append((T('O paleontólogo Joseph Leidy'), 2950, 2750, 0.78, 0, 1.3)); beat('REVEAL Leidy + CONNECT', T('Joseph Leidy'))
    cam_card(T('Humilhado'), 'elas', 0.9, 100, 60, 0, 1.0); beat('STAMP HUMILHADO', T('Humilhado'))
    K.append((T('A amizade termina'), 2300, 2300, 0.36, 0, 2.2))
    K.append((t_1877, 5450, 1400, 0.36, -0.6, 1.8)); beat('YEAR_CARD 1877 + mapa', t_1877)
    K.append((T('Em Morrison'), P['morrison'][0], P['morrison'][1] + 60, 0.95, 0, 1.6)); beat('PIN Morrison', T('Em Morrison'))
    K.append((T('Arthur Lakes'), (P['morrison'][0] + C['lakes'].x) / 2, (P['morrison'][1] + C['lakes'].y) / 2 + 150, 0.48, 0, 1.4))
    cam_card(T('Marsh paga para que'), 'lakes', 1.0, 0, 30, 1, 1.2); beat('STAMP SILÊNCIO PAGO', T('fique em silêncio'))
    cam_card(T('uma carta chega a Yale'), 'carta', 0.95, 0, 0, -0.5, 1.4); beat('DOC_FOCUS carta Harlow & Edwards', T('com nomes falsos'))
    K.append((T('Eles descrevem um cemitério'), (P['comobluff'][0] + C['carta'].x) / 2 + 200, (P['comobluff'][1] + C['carta'].y) / 2, 0.44, 0, 1.4))
    beat('PIN Como Bluff + CONNECT carta', T('em Como Bluff, no Wyoming'))
    K.append((T('Um deles se chama'), (C['carta'].x + C['reed'].x) / 2, 2950, 0.68, 0.5, 1.2)); beat('REVEAL Reed', t_reed)
    beat('VINTAGE INSERT 2 — Como Bluff', S['inserts'][1][1])
    K.append((T('E, mesmo assim', offset=-0.05), 5450, 4380, 0.48, 0, 0.1))
    K.append((T('Marsh revela o'), 6600, 4380, 0.52, 0, 1.4)); beat('NETWORK_REVEAL espécies', t_nomes)
    K.append((T('Cope responde com'), 3950, 4380, 0.55, 0, 1.4))
    cam_card(T('Na pressa de vencer'), 'bronto', 0.85, -170, -200, 0, 1.4); beat('CIRCLE Brontossauro = Apatossauro', T('o mesmo animal'))
    K.append((T('Somados'), 5450, 4380, 0.40, 0, 1.6)); beat('≈136 espécies', t_136)
    K.append((T('Mas a guerra cobra'), 1580, 1350, 0.62, 0, 2.0)); beat('STAMP NO PODER / FALIDO', T('Marsh conquista o poder'))
    cam_card(T('Marsh conquista o poder'), 'marsh', 0.95, 0, 40, 0, 1.2)
    cam_card(T('Cope perde a fortuna'), 'cope', 0.95, 0, 40, 0, 1.2)
    K.append((T('Cope guarda um arsenal'), 1900, 3700, 0.45, 0, 2.0))
    K.append((t_1890, 2000, 4050, 0.62, 0, 1.4)); beat('YEAR_CARD 1890 + Ballou', t_1890)
    cam_card(t_herald, 'herald', 0.88, 0, -120, 0, 1.4); beat('HIGHLIGHT_LINE manchete do Herald', T('estampa a manchete'))
    cam_card(T('Plágio'), 'herald', 1.05, 0, 0, 0, 1.0)
    K.append((T('Durante semanas'), 1900, 4300, 0.50, 0, 2.0))
    K.append((t_1892, 2700, 4450, 0.70, 0, 1.6)); beat('YEAR_CARD 1892 + STAMP DEMITIDO', T('Marsh perde o cargo'))
    cam_card(T('Cope é obrigado'), 'colecao', 0.95, -100, 120, 0, 1.2); beat('STAMP VENDIDA', T('com prejuízo'))
    K.append((T('Os dois homens que'), 2500, 3600, 0.34, 0, 2.4))
    cam_card(T('Edward Drinker Cope morre'), 'cope', 0.92, 0, -40, 0, 2.0); beat('† 1897 / LENDA?', T('morre em 1897'))
    cam_card(T('Marsh nunca aceitou'), 'marsh', 0.92, 0, -40, 0, 1.6); beat('† 1899', T('Morreu dois anos depois'))
    K.append((T('Hoje, os esqueletos'), 4200, 2700, 0.30, 0, 3.0)); beat('NETWORK_REVEAL quadro inteiro', T('Hoje, os esqueletos'))
    K.append((t_thesis, 4200, 2700, 0.235, 0, 4.0)); beat('THESIS', t_thesis)
    beat('TITLE_GLITCH', S['title_t'])
    return S, C

# ════════════════════════════════════════════════════════════════════════════
# RENDER
# ════════════════════════════════════════════════════════════════════════════
class Renderer:
    def __init__(self):
        self.S, self.C = build_scene()
        bg = build_board_bg()
        self.mips = [bg]
        for _ in range(3):
            p = self.mips[-1]; self.mips.append(p.resize((p.width // 2, p.height // 2), Image.LANCZOS))
        self.cards = sorted(self.S['cards'], key=lambda c: (c.z, c.t_in))
        self.cam = Camera(self.S['cam'])
        self.vig = self._vignette()
        rng = np.random.default_rng(3)
        self.grain = [(rng.normal(0, 1, (H // 2, W // 2)) * 7).astype(np.float32) for _ in range(6)]
        self._sprite_cache = {}

    def _vignette(self):
        yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
        r = np.sqrt(((xx - W / 2) / (W / 2)) ** 2 + ((yy - H / 2) / (H / 2)) ** 2)
        return np.clip(1 - 0.42 * np.clip(r - 0.45, 0, 1) ** 1.6, 0, 1)[..., None]

    # ── fundo ──
    def draw_bg(self, cam):
        cx, cy, z, r = cam
        lvl = 0
        while lvl < 3 and z * (2 ** (lvl + 1)) <= 1.25: lvl += 1
        f = 1 / 2 ** lvl; src = self.mips[lvl]
        a_ = math.radians(r); c, s = math.cos(a_), math.sin(a_)
        A = f * c / z; B = -f * s / z; D = f * s / z; E = f * c / z
        Cc = f * cx - (A * W / 2 + B * H / 2); Ff = f * cy - (D * W / 2 + E * H / 2)
        return src.transform((W, H), Image.AFFINE, (A, B, Cc, D, E, Ff), Image.BILINEAR).convert('RGBA')

    # ── sprite genérico no mundo ──
    def draw_sprite(self, frame, img, wx, wy, wrot, wscale, cam, key=None):
        cx, cy, z, r = cam
        tot = wscale * z
        lvl = 0
        while lvl < 3 and tot * (2 ** (lvl + 1)) <= 1.3: lvl += 1
        if lvl and key is not None:
            ck = (key, lvl)
            if ck not in self._sprite_cache:
                self._sprite_cache[ck] = img.resize((max(1, img.width >> lvl), max(1, img.height >> lvl)), Image.LANCZOS)
            img = self._sprite_cache[ck]; f = 2 ** lvl
        else:
            f = 1
        w, h = img.size
        ang = wrot - r; s_ = tot * f
        a_ = math.radians(ang); c, s = math.cos(a_), math.sin(a_)
        sx, sy = w2s((wx, wy), cam)
        # canto -> tela
        corners = []
        for (px, py) in [(0, 0), (w, 0), (w, h), (0, h)]:
            dx, dy = (px - w / 2) * s_, (py - h / 2) * s_
            corners.append((sx + dx * c - dy * s, sy + dx * s + dy * c))
        x0 = max(0, int(min(p[0] for p in corners)) - 1); x1 = min(W, int(max(p[0] for p in corners)) + 2)
        y0 = max(0, int(min(p[1] for p in corners)) - 1); y1 = min(H, int(max(p[1] for p in corners)) + 2)
        if x1 <= x0 or y1 <= y0: return
        # inversa: local = R(-ang)*(tela - (sx,sy))/s_ + (w/2,h/2)
        ia, ib = c / s_, s / s_
        A = ia; B = ib; Cc = -(ia * (sx - x0) + ib * (sy - y0)) + w / 2
        D = -ib; E = ia; Ff = -(-ib * (sx - x0) + ia * (sy - y0)) + h / 2
        part = img.transform((x1 - x0, y1 - y0), Image.AFFINE, (A, B, Cc, D, E, Ff), Image.BICUBIC)
        frame.alpha_composite(part, (x0, y0))

    def clamp_cam(self, cam):
        x, y, z, r = cam
        z = max(z, (W + 40) / WORLD_W, (H + 40) / WORLD_H)
        hw, hh = (W / 2 + 20) / z, (H / 2 + 20) / z
        return min(max(x, hw), WORLD_W - hw), min(max(y, hh), WORLD_H - hh), z, r

    def card_visible(self, cd, cam):
        cx, cy, z, r = cam
        rad = math.hypot(cd.sprite.width, cd.sprite.height) * cd.scale / 2
        sx, sy = w2s((cd.x, cd.y), cam)
        return -rad * z < sx < W + rad * z and -rad * z < sy < H + rad * z

    def frame(self, t):
        S, C = self.S, self.C
        cam = self.clamp_cam(self.cam.at(t))
        fr = self.draw_bg(cam)
        # cartões
        for cd in self.cards:
            if t < cd.t_in or not self.card_visible(cd, cam): continue
            k = (t - cd.t_in) / 0.45 if cd.drop else 1.0
            if k < 1:
                sc = 1.0 + 0.10 * (1 - ease_out(k)); alpha = clamp(k * 2.2)
                spr = cd.sprite
                if alpha < 1:
                    spr = spr.copy(); spr.putalpha(spr.split()[3].point(lambda v, a=alpha: int(v * a)))
                self.draw_sprite(fr, spr, cd.x, cd.y - 30 * (1 - ease_out(k)), cd.rot, cd.scale * sc, cam)
            else:
                self.draw_sprite(fr, cd.sprite, cd.x, cd.y, cd.rot, cd.scale, cam, key=cd.id)
        # carimbos (batida)
        for st in S['stamps']:
            if t < st['t']: continue
            cd = C[st['card']]; wx, wy = card_anchor(cd, st['u'], st['v'])
            k = (t - st['t']) / 0.16
            sc = 1.0 + 0.7 * (1 - ease_out(k)) if k < 1 else 1.0
            img = stamp_img(st['text'], st['size'], hash(st['text']) % 97)
            if k < 1:
                img = img.copy(); img.putalpha(img.split()[3].point(lambda v, a=clamp(k * 1.5): int(v * a)))
                self.draw_sprite(fr, img, wx, wy, cd.rot + st['rot'], sc, cam)
            else:
                self.draw_sprite(fr, img, wx, wy, cd.rot + st['rot'], 1.0, cam, key='stamp_' + st['text'])
        # vetores (2x supersample)
        self.draw_vectors(fr, t, cam)
        # etiquetas datilografadas
        for lb in S['labels']:
            if t < lb['t']: continue
            cd = C[lb['card']]
            ax, ay = card_anchor(cd, lb['u'], lb['v'])
            dx, dy = rot(lb['dx'], lb['dy'], cd.rot)
            n = int((t - lb['t']) * 26) + 1
            full = n >= len(lb['text'])
            img = label_img(lb['text'], lb['size'], None if full else n)
            self.draw_sprite(fr, add_shadow(img, 12) if full else img, ax + dx, ay + dy, cd.rot, 1.0, cam,
                             key=('lab', lb['text']) if full else None)
        # overlays de tela
        for ov in S['overlays']:
            kind, t0, dur = ov[0], ov[1], ov[2]
            if t0 <= t <= t0 + dur: self.draw_overlay(fr, ov, t - t0)
        out = fr.convert('RGB')
        if t >= S['title_t']: out = self.title_frame(out, t - S['title_t'])
        return self.finish(out, t)

    def draw_vectors(self, fr, t, cam):
        active = [v for v in self.S['vecs'] if t >= v.t_in]
        if not active: return
        SS = 2
        ov = Image.new('RGBA', (W * SS, H * SS), (0, 0, 0, 0)); d = ImageDraw.Draw(ov)
        z = cam[2]
        def sp(p): x, y = w2s(p, cam); return (x * SS, y * SS)
        pins = []
        for v in active:
            prog = clamp((t - v.t_in) / v.dur)
            if v.kind == 'string':
                pts = string_pts(v.kw['p0'], v.kw['p1'], v.kw['sag'])
                n = max(2, int(len(pts) * ease_out(prog)))
                spts = [sp(p) for p in pts[:n]]
                wd = max(2, int(5 * z * SS))
                d.line([(x + 2 * SS, y + 3 * SS) for x, y in spts], fill=(0, 0, 0, 90), width=wd, joint='curve')
                d.line(spts, fill=RED + (255,), width=wd, joint='curve')
                pins.append(v.kw['p0'])
                if prog >= 1: pins.append(v.kw['p1'])
            elif v.kind == 'circle':
                pts = [sp(p) for p in circle_pts(v, ease_out(prog))]
                if len(pts) > 1: d.line(pts, fill=RED + (235,), width=max(3, int(v.kw['width'] * z * SS)), joint='curve')
            elif v.kind == 'underline':
                (x0, y0), (x1, y1) = v.kw['p0'], v.kw['p1']
                rng = random.Random(v.kw['seed'])
                for pas in range(2):
                    pp = clamp(prog * 1.6 - pas * 0.6)
                    if pp <= 0: continue
                    pts = []
                    for k in range(25):
                        u = k / 24 * pp
                        off = (pas * 7 + 3 * math.sin(u * 9 + pas)) * 1.0
                        pts.append(sp((x0 + (x1 - x0) * u, y0 + (y1 - y0) * u + off)))
                    d.line(pts, fill=RED + (230,), width=max(3, int(6 * z * SS)), joint='curve')
            elif v.kind == 'pin':
                pins.append(v.kw['p'])
        for p in pins:
            x, y = sp(p); rr = max(5, 13 * z) * SS
            d.ellipse([x - rr + 3 * SS, y - rr + 4 * SS, x + rr + 3 * SS, y + rr + 4 * SS], fill=(0, 0, 0, 110))
            d.ellipse([x - rr, y - rr, x + rr, y + rr], fill=(176, 30, 28, 255))
            d.ellipse([x - rr * 0.45, y - rr * 0.6, x + rr * 0.05, y - rr * 0.1], fill=(240, 140, 130, 255))
        # alfinetes dos cartões
        for cd in self.cards:
            if cd.pin is None or t < cd.t_in + 0.3: continue
            x, y = sp(card_anchor(cd, *cd.pin)); rr = max(4, 12 * z) * SS
            d.ellipse([x - rr + 3 * SS, y - rr + 4 * SS, x + rr + 3 * SS, y + rr + 4 * SS], fill=(0, 0, 0, 110))
            d.ellipse([x - rr, y - rr, x + rr, y + rr], fill=(150, 26, 24, 255))
            d.ellipse([x - rr * 0.45, y - rr * 0.6, x, y - rr * 0.15], fill=(235, 130, 120, 255))
        fr.alpha_composite(ov.resize((W, H), Image.LANCZOS))

    def draw_overlay(self, fr, ov, lt):
        kind = ov[0]; dur = ov[2]
        a = smooth(lt / 0.35) * (1 - smooth((lt - dur + 0.45) / 0.45))
        if a <= 0: return
        lay = Image.new('RGBA', (W, H), (0, 0, 0, 0)); d = ImageDraw.Draw(lay)
        if kind == 'year':
            _, _, _, year, sub = ov
            d.rectangle([0, H - 300, W, H - 120], fill=(10, 8, 6, int(150 * a)))
            n = min(len(year), int(lt * 14) + 1)
            d.text((150, H - 210), year[:n], font=F(BEBAS, 150), fill=(240, 232, 214, int(255 * a)), anchor='lm')
            d.line([(150, H - 140), (150 + 330 * ease_out(lt / 0.6), H - 140)], fill=RED + (int(255 * a),), width=8)
            d.text((520, H - 205), sub, font=F(TYPE, 48), fill=(240, 232, 214, int(230 * a)), anchor='lm')
        elif kind == 'thesis':
            _, _, _, l1, l2 = ov
            d.rectangle([0, 0, W, H], fill=(8, 6, 5, int(165 * a)))
            img, _ = make_paper_tracked([(l1, PLAYB, 64, INK, 'c'), (l2, PLAYB, 64, INK, 'c')], 1280, (236, 228, 206), seed=99)
            img = img.rotate(-1.2, expand=True, resample=Image.BICUBIC)
            img.putalpha(img.split()[3].point(lambda v: int(v * a)))
            lay.alpha_composite(img, ((W - img.width) // 2, (H - img.height) // 2 - 10))
            d2 = ImageDraw.Draw(lay)
            d2.line([(W / 2 - 420, H / 2 + 115), (W / 2 - 420 + 840 * ease_out((lt - 0.8) / 1.0), H / 2 + 115)],
                    fill=RED + (int(255 * a),), width=7)
        fr.alpha_composite(lay)

    def title_frame(self, base, lt):
        """Título final com glitch."""
        dark = smooth(lt / 0.5)
        img = Image.blend(base, Image.new('RGB', (W, H), (6, 5, 4)), dark * 0.92)
        lay = Image.new('RGBA', (W, H), (0, 0, 0, 0)); d = ImageDraw.Draw(lay)
        if lt > 0.3:
            f = F(BEBAS, 230)
            d.text((W / 2, H / 2 - 30), 'A GUERRA DOS OSSOS', font=f, fill=RED + (255,), anchor='mm')
            d.text((W / 2, H / 2 + 120), 'CHARLIE DARK LAB', font=F(TYPE, 40), fill=(225, 218, 200, 255), anchor='mm')
            glitch = (lt - 0.3) < 0.9 or (int(lt * 10) % 17 == 0)
            if glitch:
                rng = random.Random(int(lt * 30))
                arr = np.array(lay)
                for _ in range(10):
                    y = rng.randrange(0, H - 40); hh = rng.randrange(6, 40); sh = rng.randrange(-60, 60)
                    arr[y:y + hh] = np.roll(arr[y:y + hh], sh, axis=1)
                lay = Image.fromarray(arr)
                r_, g_, b_, a_ = lay.split()
                cyan = Image.merge('RGBA', (Image.new('L', (W, H), 40), g_.point(lambda v: v), b_.point(lambda v: 255 if v else 0), a_.point(lambda v: v // 2)))
                img.paste(cyan, (rng.randrange(-14, 14), 0), cyan)
        img.paste(lay, (0, 0), lay)
        if lt > self.S['end'] - self.S['title_t'] - 0.8:
            k = (lt - (self.S['end'] - self.S['title_t'] - 0.8)) / 0.8
            img = Image.blend(img, Image.new('RGB', (W, H), 0), clamp(k))
        return img

    def finish(self, img, t):
        a = np.asarray(img, np.float32)
        g = self.grain[int(t * FPS) % len(self.grain)]
        g = np.repeat(np.repeat(g, 2, 0), 2, 1)[..., None]
        flick = 1 + 0.012 * math.sin(t * 37) * math.sin(t * 11)
        a = (a * self.vig * flick + g)
        if t < 1.2: a *= smooth(t / 1.2)
        return Image.fromarray(np.clip(a, 0, 255).astype(np.uint8))

# ════════════════════════════════════════════════════════════════════════════
# CLI
# ════════════════════════════════════════════════════════════════════════════
def in_insert(S, t):
    return any(a <= t < b for _, a, b in S['inserts'])

def render_range(f0, f1, out):
    R = Renderer()
    p = subprocess.Popen(['ffmpeg', '-y', '-loglevel', 'error', '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-s', f'{W}x{H}',
                          '-r', str(FPS), '-i', '-', '-c:v', 'libx264', '-preset', 'medium', '-crf', '17',
                          '-pix_fmt', 'yuv420p', out], stdin=subprocess.PIPE)
    black = bytes(W * H * 3)
    for fi in range(f0, f1):
        t = fi / FPS
        if in_insert(R.S, t): p.stdin.write(black); continue
        p.stdin.write(R.frame(t).tobytes())
        if (fi - f0) % 300 == 0: print(f'[{f0}-{f1}] {fi}', flush=True)
    p.stdin.close(); p.wait()

if __name__ == '__main__':
    cmd = sys.argv[1] if len(sys.argv) > 1 else 'sheet'
    if cmd == 'mapgrid':
        m = build_map().convert('RGB'); d = ImageDraw.Draw(m)
        for x in range(0, MAP_W, 100):
            d.line([(x, 0), (x, MAP_H)], fill=(0, 90, 200), width=1); d.text((x + 2, 2), str(x), font=F(TYPE, 18), fill=(0, 60, 160))
        for y in range(0, MAP_H, 100):
            d.line([(0, y), (MAP_W, y)], fill=(0, 90, 200), width=1); d.text((2, y + 2), str(y), font=F(TYPE, 18), fill=(0, 60, 160))
        for nm, (la, lo) in {'Filadélfia': (39.95, -75.17), 'New Haven': (41.31, -72.92), 'Nova York': (40.71, -74.0),
                             'Washington': (38.9, -77.04), 'Morrison': (39.65, -105.19), 'Cañon City': (38.44, -105.24),
                             'Como Bluff': (41.9, -106.15), 'Denver(ref)': (39.74, -104.99), 'Chicago(ref)': (41.88, -87.63),
                             'S.Francisco(ref)': (37.77, -122.42), 'Nova Orleans(ref)': (29.95, -90.07)}.items():
            x, y = map_px(la, lo); d.ellipse([x - 8, y - 8, x + 8, y + 8], outline=RED, width=4)
            d.text((x + 12, y - 12), f'{nm} ({int(x)},{int(y)})', font=F(TYPE, 22), fill=RED)
        m.save(os.path.join(BUILD, 'map_grid.jpg'), quality=88); print('build/map_grid.jpg')
    elif cmd == 'beats':
        S, C = build_scene()
        json.dump(S['beats'], open(os.path.join(BUILD, 'beats.json'), 'w'), ensure_ascii=False, indent=1)
        for b in S['beats']: print(f'{b[1]:7.2f}s  {b[0]}')
        print('inserts:', S['inserts'], ' fim:', S['end'])
    elif cmd == 'cues':
        S, C = build_scene(); cues = []
        ks = S['cam']
        for a_, b_ in zip(ks, ks[1:]):
            mv = b_[5] if len(b_) > 5 else min(1.4, b_[0] - a_[0])
            if mv >= 0.9: cues.append({'t': round(b_[0] - mv, 3), 'type': 'whoosh', 'd': round(min(mv + 0.3, 2.2), 2), 'pan': random.uniform(-0.4, 0.4)})
        for lb in S['labels']: cues.append({'t': lb['t'], 'type': 'type', 'n': len(lb['text']), 'g': 0.8})
        for ov in S['overlays']:
            if ov[0] == 'year': cues.append({'t': ov[1], 'type': 'type', 'n': 4, 'g': 1.3}); cues.append({'t': ov[1], 'type': 'stamp', 'g': 0.5})
        for st in S['stamps']: cues.append({'t': st['t'], 'type': 'stamp'})
        for v in S['vecs']:
            if v.kind == 'circle': cues.append({'t': v.t_in, 'type': 'circle', 'd': v.dur + 0.1})
            elif v.kind == 'underline': cues.append({'t': v.t_in, 'type': 'circle', 'd': v.dur, 'g': 0.8})
            elif v.kind == 'string': cues.append({'t': v.t_in, 'type': 'string', 'd': v.dur}); cues.append({'t': v.t_in + v.dur, 'type': 'pin'})
            elif v.kind == 'pin': cues.append({'t': v.t_in, 'type': 'pin'})
        for cd in S['cards']:
            if cd.t_in > 0: cues.append({'t': cd.t_in, 'type': 'pin', 'g': 0.7})
        ins = {k: (a_, b_) for k, a_, b_ in S['inserts']}
        for k, (a_, b_) in ins.items(): cues.append({'t': a_, 'type': 'projector', 't1': b_})
        a_, b_ = ins['comobluff']
        cues.append({'t': T('desviam cargas de trem') - 0.3, 'type': 'train', 't1': T('destroem os ossos') + 0.3})
        cues.append({'t': T('É ciência feita') - 0.25, 'type': 'boom'})
        cues.append({'t': T('Durante semanas') - 9.0, 'type': 'pulse', 't1': T('Durante semanas') + 4.0})
        cues.append({'t': S['title_t'] - 3.5, 'type': 'riser', 't1': S['title_t'] + 0.3})
        cues.append({'t': S['title_t'] + 0.3, 'type': 'hit'})
        cues.sort(key=lambda c: c['t'])
        json.dump({'duration': S['end'], 'cues': cues}, open(os.path.join(BUILD, 'cues.json'), 'w'), indent=0)
        print('build/cues.json', len(cues))
    elif cmd == 'stills':
        R = Renderer()
        for ts in sys.argv[2].split(','):
            t = float(ts); R.frame(t).save(os.path.join(BUILD, f'still_{t:07.2f}.jpg'), quality=90); print('still', t)
    elif cmd == 'sheet':
        R = Renderer()
        times = sorted({b[1] + 1.2 for b in R.S['beats']})
        times = [t for t in times if not in_insert(R.S, t)]
        th_w, th_h, cols = 640, 360, 4
        rows = (len(times) + cols - 1) // cols
        sheet = Image.new('RGB', (cols * th_w, rows * (th_h + 30)), (20, 20, 20)); d = ImageDraw.Draw(sheet)
        names = {round(b[1] + 1.2, 2): b[0] for b in R.S['beats']}
        for i, t in enumerate(times):
            im = R.frame(t).resize((th_w, th_h), Image.LANCZOS)
            x, y = (i % cols) * th_w, (i // cols) * (th_h + 30)
            sheet.paste(im, (x, y)); d.text((x + 6, y + th_h + 4), f'{t:.1f}s {names.get(round(t, 2), "")}'[:60], font=F(TYPE, 18), fill=(230, 230, 230))
        sheet.save(os.path.join(BUILD, 'contact_sheet.jpg'), quality=85); print('build/contact_sheet.jpg', len(times))
    elif cmd == 'render':
        workers = int(sys.argv[sys.argv.index('--workers') + 1]) if '--workers' in sys.argv else os.cpu_count()
        S, _ = build_scene()
        total = int(math.ceil(S['end'] * FPS))
        build_map(); build_board_bg()
        bounds = [total * k // workers for k in range(workers + 1)]
        procs = []
        for k in range(workers):
            out = os.path.join(BUILD, f'chunk_{k:02d}.mp4')
            procs.append(subprocess.Popen([sys.executable, __file__, 'chunk', str(bounds[k]), str(bounds[k + 1]), out]))
        for p in procs: p.wait()
        lst = os.path.join(BUILD, 'chunks.txt')
        open(lst, 'w').write(''.join(f"file 'chunk_{k:02d}.mp4'\n" for k in range(workers)))
        subprocess.run(['ffmpeg', '-y', '-loglevel', 'error', '-f', 'concat', '-safe', '0', '-i', lst, '-c', 'copy',
                        os.path.join(BUILD, 'board.mp4')], check=True)
        json.dump({'inserts': S['inserts'], 'end': S['end'], 'fps': FPS}, open(os.path.join(BUILD, 'render_meta.json'), 'w'))
        print('build/board.mp4')
    elif cmd == 'chunk':
        render_range(int(sys.argv[2]), int(sys.argv[3]), sys.argv[4])
