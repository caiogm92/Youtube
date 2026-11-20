#!/usr/bin/env python3
"""Santos FC — O Eterno Gigante: motor de renderização.

Gera os quadros do documentário (1920x1080, 30 fps) a partir de um roteiro
de planos (timeline.py) e envia para o ffmpeg. Cada plano é renderizado em
paralelo como um segmento; os segmentos são concatenados com o áudio final.

Uso:  python3 render.py [--preview]   (preview = 960x540, 15 fps)
"""
import math, os, sys, subprocess, json, random
from concurrent.futures import ProcessPoolExecutor
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageEnhance, ImageOps

ROOT = os.path.dirname(os.path.abspath(__file__))
PREVIEW = "--preview" in sys.argv
W, H = (960, 540) if PREVIEW else (1920, 1080)
FPS = 15 if PREVIEW else 30
S = W / 1920.0  # fator de escala para tamanhos em px

FONT_TITLE = os.path.join(ROOT, "fonts/Cinzel.ttf")
FONT_COND = os.path.join(ROOT, "fonts/Oswald.ttf")
FONT_BEBAS = os.path.join(ROOT, "fonts/BebasNeue.ttf")


def font(path, size, wght=None):
    f = ImageFont.truetype(path, max(8, int(size * S)))
    if wght is not None:
        try:
            f.set_variation_by_axes([wght])
        except Exception:
            pass
    return f


def ease(t):  # easeInOutSine
    t = min(max(t, 0.0), 1.0)
    return 0.5 - 0.5 * math.cos(math.pi * t)


def lerp(a, b, t):
    return a + (b - a) * t


# ---------------------------------------------------------------- texturas
_rng = np.random.default_rng(7)
GRAIN = [(_rng.standard_normal((H, W)) * 1.0).astype(np.float32) for _ in range(6)]
yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
_r = np.sqrt(((xx - W / 2) / (W / 2)) ** 2 + ((yy - H / 2) / (H / 2)) ** 2)
VIGNETTE = np.clip(1.0 - 0.55 * np.clip(_r - 0.45, 0, None) ** 1.6, 0.25, 1.0)[..., None].astype(np.float32)
del yy, xx, _r


def finish(frame, fidx, grain=7.0, vignette=True, flicker=0.0):
    """grade final: vinheta, grão de película, leve flicker"""
    f = frame.astype(np.float32)
    if vignette:
        f *= VIGNETTE
    if flicker:
        f *= 1.0 + flicker * math.sin(fidx * 1.7) * math.sin(fidx * 0.37)
    if grain:
        f += GRAIN[fidx % len(GRAIN)][..., None] * grain
    return np.clip(f, 0, 255).astype(np.uint8)


# ---------------------------------------------------------------- imagens
_cache = {}


def load(name, mode="bw", sharpen=True):
    key = (name, mode)
    if key in _cache:
        return _cache[key]
    im = Image.open(os.path.join(ROOT, name)).convert("RGB")
    # upscale de qualidade para fontes pequenas
    target = 2400 if not PREVIEW else 1200
    sc = target / max(im.size)
    if sc > 1:
        im = im.resize((int(im.width * sc), int(im.height * sc)), Image.LANCZOS)
        if sharpen:
            im = im.filter(ImageFilter.UnsharpMask(radius=2.2, percent=90, threshold=2))
    im = grade(im, mode)
    _cache[key] = im
    return im


def grade(im, mode):
    if mode == "bw":  # preto e branco com contraste dramático
        g = ImageOps.grayscale(im)
        g = ImageOps.autocontrast(g, cutoff=1)
        a = np.asarray(g).astype(np.float32) / 255.0
        a = a * a * (3 - 2 * a)  # curva S
        a = np.clip(a * 0.94 + 0.02, 0, 1)
        rgb = np.stack([a * 247, a * 243, a * 234], -1)  # leve tom prateado
        return Image.fromarray(rgb.astype(np.uint8))
    if mode == "color":  # cor dessaturada, sombras frias, contraste alto
        im = ImageEnhance.Color(im).enhance(0.55)
        a = np.asarray(im).astype(np.float32) / 255.0
        a = a * a * (3 - 2 * a)
        lum = a.mean(-1, keepdims=True)
        shadow = np.array([0.92, 0.98, 1.06], np.float32)
        high = np.array([1.04, 1.0, 0.94], np.float32)
        a = a * (shadow * (1 - lum) + high * lum)
        return Image.fromarray(np.clip(a * 255 * 0.95, 0, 255).astype(np.uint8))
    return im


def cover_transform(src, cx, cy, zoom, out_w=None, out_h=None):
    """recorta src com centro (cx,cy em 0..1) e zoom (1 = cobre o quadro)"""
    out_w, out_h = out_w or W, out_h or H
    sw, sh = src.size
    base = max(out_w / sw, out_h / sh)
    scale = base * zoom
    vw, vh = out_w / scale, out_h / scale
    x0 = cx * sw - vw / 2
    y0 = cy * sh - vh / 2
    x0 = min(max(x0, 0), sw - vw)
    y0 = min(max(y0, 0), sh - vh)
    return src.transform((out_w, out_h), Image.AFFINE, (1 / scale, 0, x0, 0, 1 / scale, y0), resample=Image.BICUBIC)


_bg_cache = {}


def blurred_bg(name, mode):
    key = (name, mode)
    if key not in _bg_cache:
        src = load(name, mode)
        bg = cover_transform(src, 0.5, 0.5, 1.15)
        bg = bg.filter(ImageFilter.GaussianBlur(40 * S))
        bg = ImageEnhance.Brightness(bg).enhance(0.32)
        _bg_cache[key] = bg
    return _bg_cache[key]


def shot_photo(p, t, dur):
    """foto vertical em quadro 16:9: fundo desfocado + foto nítida com paralaxe"""
    name, mode = p["img"], p.get("mode", "bw")
    src = load(name, mode)
    k = ease(t / dur)
    z = lerp(p.get("z0", 1.0), p.get("z1", 1.08), k)
    bg = blurred_bg(name, mode)
    # paralaxe: fundo se move mais devagar e no sentido contrário
    dx = lerp(p.get("x0", 0.0), p.get("x1", 0.0), k)
    bgz = 1.0 + (z - 1.0) * 0.4
    bgi = cover_transform(bg, 0.5 - dx * 0.15, 0.5, bgz)
    frame = bgi.copy()
    # foto principal
    fh = int(H * p.get("h", 0.9) * z)
    fw = int(src.width * fh / src.height)
    fg = src.resize((fw, fh), Image.BICUBIC)
    side = p.get("side", 0.5)  # posição horizontal do centro (0..1)
    cx = int(W * side + dx * W) - fw // 2
    cy = (H - fh) // 2 + int(lerp(p.get("y0", 0), p.get("y1", 0), k) * H)
    # sombra suave
    sh = Image.new("L", (fw + int(160 * S), fh + int(160 * S)), 0)
    ImageDraw.Draw(sh).rectangle([int(80 * S), int(80 * S), int(80 * S) + fw, int(80 * S) + fh], fill=190)
    sh = sh.filter(ImageFilter.GaussianBlur(36 * S))
    frame.paste((0, 0, 0), (cx - int(80 * S), cy - int(70 * S)), sh)
    frame.paste(fg, (cx, cy))
    return np.asarray(frame)


def shot_crop(p, t, dur):
    """plano de detalhe em tela cheia: recorte de uma foto com movimento de câmera"""
    src = load(p["img"], p.get("mode", "bw"))
    k = ease(t / dur)
    cx = lerp(p["c0"][0], p["c1"][0], k)
    cy = lerp(p["c0"][1], p["c1"][1], k)
    z = lerp(p["z0"], p["z1"], k)
    im = cover_transform(src, cx, cy, z)
    if p.get("dim"):
        im = ImageEnhance.Brightness(im).enhance(p["dim"])
    return np.asarray(im)


def shot_broll(p, t, dur):
    """imagem 16:9 (b-roll) em tela cheia com movimento lento"""
    path = os.path.join(ROOT, p["img"])
    if not os.path.exists(path):  # sem b-roll: usa a bandeira procedural
        return shot_flag({"dark": 0.55}, t, dur)
    return shot_crop({**p, "c0": p.get("c0", (0.5, 0.5)), "c1": p.get("c1", (0.5, 0.5)),
                      "z0": p.get("z0", 1.0), "z1": p.get("z1", 1.1)}, t, dur)


def shot_flag(p, t, dur):
    """bandeira alvinegra tremulando (listras), procedural"""
    key = ("flaggrid",)
    if key not in _cache:
        y, x = np.mgrid[0:H, 0:W].astype(np.float32)
        _cache[key] = (x, y)
    x, y = _cache[key]
    ph = t * 2.2
    wave = np.sin(x / W * 9.0 - ph * 2.0 + y / H * 2.0) * 0.6 + np.sin(x / W * 4.0 - ph * 1.3) * 0.4
    xs = x + wave * 38 * S + y * 0.18
    stripes = (np.sin(xs / (W / 7.0) * math.pi) > 0).astype(np.float32)
    # suaviza as bordas das listras
    stripes = np.clip((np.sin(xs / (W / 7.0) * math.pi)) * 6 + 0.5, 0, 1)
    shade = 0.62 + 0.38 * np.cos(np.sin(x / W * 9.0 - ph * 2.0 + y / H * 2.0) * 1.2)
    v = (0.06 + 0.84 * stripes) * shade * p.get("dark", 0.75)
    v = np.clip(v, 0, 1) * 255
    return np.repeat(v[..., None], 3, -1).astype(np.uint8)


def shot_black(p, t, dur):
    return np.zeros((H, W, 3), np.uint8)


# ---------------------------------------------------------------- tipografia
def draw_spaced(draw, xy, text, fnt, fill, spacing, anchor_center=True):
    widths = [draw.textlength(ch, font=fnt) for ch in text]
    total = sum(widths) + spacing * (len(text) - 1)
    x, y = xy
    if anchor_center:
        x -= total / 2
    for ch, w in zip(text, widths):
        draw.text((x, y), ch, font=fnt, fill=fill, anchor="lm")
        x += w + spacing
    return total


def text_layer(lines, t, dur):
    """lines: list of dict(text, font, size, y, spacing, delay, color, wght)"""
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    for ln in lines:
        delay = ln.get("delay", 0.3)
        fin, fout = ln.get("fade", 1.2), ln.get("fadeout", 1.0)
        end = ln.get("end", dur)
        a = ease((t - delay) / fin) * (1 - ease((t - (end - fout)) / fout))
        if a <= 0:
            continue
        fnt = font(FONTS.get(ln.get("font", "title"), FONT_TITLE), ln["size"], ln.get("wght", 600 if ln.get("font", "title") == "title" else None))
        col = ln.get("color", (242, 238, 228))
        drift = (1 - ease((t - delay) / (fin * 2.5))) * 14 * S
        sp = ln.get("spacing", 12) * S * (1 + 0.15 * ease(t / dur))
        draw_spaced(d, (W / 2 + ln.get("x", 0) * W, H * ln["y"] + drift), ln["text"], fnt,
                    col + (int(255 * a),), sp)
        if ln.get("rule"):
            rw = ln["rule"] * W * ease((t - delay) / (fin * 1.5))
            ry = H * ln["y"] + ln.get("rule_dy", 60) * S
            d.line([(W / 2 - rw / 2, ry), (W / 2 + rw / 2, ry)], fill=(196, 160, 90, int(200 * a)), width=max(1, int(2 * S)))
    return layer


def composite_text(frame, lines, t, dur, shade=0.0):
    if not lines:
        return frame
    im = Image.fromarray(frame)
    if shade:
        im = Image.blend(im, Image.new("RGB", im.size, (0, 0, 0)), shade)
    im = im.convert("RGBA")
    im.alpha_composite(text_layer(lines, t, dur))
    return np.asarray(im.convert("RGB"))


# ---------------------------------------------------------------- mapa
def map_base():
    if "map" in _cache:
        return _cache["map"]
    from global_land_mask import globe
    im = Image.new("RGB", (W, H), (6, 6, 7))
    d = ImageDraw.Draw(im)
    step = 1.25
    lats = np.arange(-58, 76, step)
    lons = np.arange(-170, 180, step)
    LON, LAT = np.meshgrid(lons, lats)
    land = globe.is_land(LAT, LON)
    pts = []
    for la, lo, l in zip(LAT.ravel(), LON.ravel(), land.ravel()):
        if l:
            x, y = proj(lo, la)
            pts.append((x, y))
    r = max(1.2, 2.6 * S)
    for x, y in pts:
        d.ellipse([x - r, y - r, x + r, y + r], fill=(118, 116, 112))
    _cache["map"] = im
    return im


MAP_BOX = (-95, 58, 35, -55)  # lon0, lat0, lon1, lat1 (Américas + Europa)


def proj(lon, lat):
    lon0, lat0, lon1, lat1 = MAP_BOX
    x = (lon - lon0) / (lon1 - lon0) * W
    y = (lat0 - lat) / (lat0 - lat1) * H
    return x, y


CITIES = {
    "SANTOS": (-46.33, -23.96),
    "MONTEVIDÉU": (-56.16, -34.90),
    "BUENOS AIRES": (-58.38, -34.60),
    "LISBOA": (-9.14, 38.72),
    "MILÃO": (9.19, 45.46),
    "RIO DE JANEIRO": (-43.17, -22.91),
}


def shot_map(p, t, dur):
    base = map_base()
    k = ease(t / dur)
    z = lerp(1.0, 1.12, k)
    im = cover_transform(base, 0.5, 0.5, z).convert("RGBA")
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)

    def zp(x, y):  # aplica o mesmo zoom do mapa base
        sw, sh = W, H
        scale = z
        vw, vh = W / scale, H / scale
        x0 = min(max(0.5 * sw - vw / 2, 0), sw - vw)
        y0 = min(max(0.5 * sh - vh / 2, 0), sh - vh)
        return (x - x0) * scale, (y - y0) * scale

    fnt = font(FONT_COND, 34, 500)
    sx, sy = zp(*proj(*CITIES["SANTOS"]))
    routes = p["routes"]
    for i, (city, label) in enumerate(routes):
        sp = 0.6 if p.get("fast") else 1.6
        st = 0.6 + i * (dur - sp - 1.0) / max(1, len(routes))
        a = ease((t - st) / sp)
        if a <= 0:
            continue
        ex, ey = zp(*proj(*CITIES[city]))
        # arco
        mx, my = (sx + ex) / 2, min(sy, ey) - abs(ex - sx) * 0.28 - 60 * S
        n = 80
        pts = []
        for j in range(int(n * a) + 1):
            u = j / n
            bx = (1 - u) ** 2 * sx + 2 * (1 - u) * u * mx + u * u * ex
            by = (1 - u) ** 2 * sy + 2 * (1 - u) * u * my + u * u * ey
            pts.append((bx, by))
        if len(pts) > 1:
            d.line(pts, fill=(214, 178, 104, 230), width=max(1, int(3 * S)))
        if a >= 1:
            al = int(255 * ease((t - st - sp) / 0.6))
            r = 7 * S
            d.ellipse([ex - r, ey - r, ex + r, ey + r], fill=(240, 236, 226, al))
            d.text((ex + 14 * S, ey - 4 * S), city, font=fnt, fill=(240, 236, 226, al), anchor="ls")
            d.text((ex + 14 * S, ey + 30 * S), label, font=font(FONT_COND, 24, 400), fill=(214, 178, 104, al), anchor="ls")
    r = 10 * S
    d.ellipse([sx - r, sy - r, sx + r, sy + r], fill=(255, 255, 255, 255))
    d.text((sx - 18 * S, sy + 6 * S), "SANTOS", font=font(FONT_COND, 30, 600), fill=(255, 255, 255, 255), anchor="rm")
    im.alpha_composite(layer)
    return np.asarray(im.convert("RGB"))


# ---------------------------------------------------------------- planos procedurais extras
def shot_sea(p, t, dur):
    """mar ao amanhecer (ou entardecer), P&B, procedural"""
    key = ("seagrid",)
    if key not in _cache:
        y, x = np.mgrid[0:H, 0:W].astype(np.float32)
        _cache[key] = (x / W, y / H)
    x, y = _cache[key]
    hz = 0.46 + 0.02 * ease(t / dur)  # horizonte desce levemente (tilt)
    sunx = 0.62
    sky = 0.18 + 0.55 * np.exp(-(((x - sunx) / 0.22) ** 2 + ((y - hz) / 0.10) ** 2)) + 0.12 * (1 - y / hz)
    sky += 0.6 * np.exp(-(((x - sunx) ** 2 + ((y - hz + 0.02) * 1.3) ** 2) / 0.0012))
    d = np.clip(y - hz, 1e-3, None)
    depth = 0.02 / d
    ph = t * 0.6
    w1 = np.sin((x - 0.5) * 28 * depth * 0.25 + depth * 9 + ph * 2.0)
    w2 = np.sin((x - 0.5) * 61 * depth * 0.18 - depth * 13 + ph * 2.7)
    wave = (w1 * 0.6 + w2 * 0.4)
    glitter = np.exp(-((x - sunx) / (0.05 + 0.25 * d)) ** 2) * np.clip(wave, 0, 1) ** 3 * 1.1
    sea = 0.10 + 0.10 * (1 - np.clip(d * 3, 0, 1)) + 0.06 * wave * np.clip(d * 4, 0, 1) + glitter
    # costa/cidade: silhueta baixa à esquerda
    hill = 0.05 * np.exp(-((x - 0.08) / 0.16) ** 2) + 0.028 * np.exp(-((x - 0.3) / 0.09) ** 2) \
        + 0.006 * np.sin(x * 37) * (x < 0.4)
    land = (y < hz) & (y > hz - hill)
    img = np.where(y < hz, sky, sea * 1.25)
    img = np.where(land, sky * 0.28, img)
    img = np.clip(img, 0, 1)
    if p.get("dusk"):
        img = img ** 1.35
    v = img * 255
    return np.stack([v * 1.0, v * 0.985, v * 0.95], -1).astype(np.uint8)


_rain = None


def shot_rain(p, t, dur):
    """estádio vazio à noite, refletores na chuva (procedural)"""
    global _rain
    rng = np.random.default_rng(3)
    if _rain is None:
        _rain = rng.random((420, 4)).astype(np.float32)
    close = p.get("close", False)
    light = p.get("light", False)
    base = Image.new("RGB", (W, H), (4, 5, 7))
    d = ImageDraw.Draw(base)
    k = ease(t / dur)
    # arquibancada vazia: linhas horizontais em perspectiva
    for i in range(26):
        yy = H * (0.52 + (i / 26) ** 1.6 * 0.48)
        c = int(14 + 10 * (i % 2))
        d.line([(0, yy), (W, yy)], fill=(c, c, c + 2), width=max(1, int(3 * S)))
    for i in range(40):
        xx = W * i / 40
        d.line([(xx, H * 0.52), (xx + (xx - W / 2) * 0.3, H)], fill=(9, 9, 11), width=max(1, int(2 * S)))
    glow = Image.new("RGB", (W, H), (0, 0, 0))
    gd = ImageDraw.Draw(glow)
    lights = [(0.18, 0.16), (0.5, 0.10), (0.82, 0.16)] if not close else [(0.35, 0.22), (0.7, 0.18)]
    on = 1.0 if light else 0.75
    for j, (lx, ly) in enumerate(lights):
        flick = on * (0.85 + 0.15 * math.sin(t * 7 + j * 2))
        cx, cy = lx * W + (k - 0.5) * 40 * S, ly * H
        for rr, a in ((160, 40), (90, 90), (45, 190), (18, 255)):
            r = rr * S * (1.4 if close else 1)
            v = int(a * flick)
            gd.ellipse([cx - r * 1.6, cy - r, cx + r * 1.6, cy + r], fill=(v, v, int(v * 1.05)))
    glow = glow.filter(ImageFilter.GaussianBlur(30 * S))
    im = Image.fromarray(np.clip(np.asarray(base, np.int16) + np.asarray(glow, np.int16), 0, 255).astype(np.uint8))
    d = ImageDraw.Draw(im)
    spd = 1.6 if close else 1.1
    for rx, ry, rl, rb in _rain:
        x0 = rx * W + t * 60 * S
        y0 = ((ry + t * spd * (0.8 + rb)) % 1.0) * H * 1.1 - 0.05 * H
        L = (30 + 50 * rl) * S * (1.5 if close else 1)
        b = int(60 + 120 * rb)
        d.line([(x0 % W, y0), ((x0 + L * 0.15) % W, y0 + L)], fill=(b, b, b + 8), width=1)
    return np.asarray(im)


_crest = None


def crest_cutout():
    """escudo recortado do fundo creme (flood-fill a partir das bordas)"""
    global _crest
    if _crest is not None:
        return _crest
    im = Image.open(os.path.join(ROOT, "assets/escudo.jpg")).convert("RGB")
    sc = (2000 if not PREVIEW else 1000) / im.height
    im = im.resize((int(im.width * sc), int(im.height * sc)), Image.LANCZOS)
    mask_src = im.copy()
    for seed in [(2, 2), (im.width - 3, 2), (2, im.height - 3), (im.width - 3, im.height - 3)]:
        ImageDraw.floodfill(mask_src, seed, (255, 0, 255), thresh=38)
    a = np.asarray(mask_src)
    m = ~((a[..., 0] == 255) & (a[..., 1] == 0) & (a[..., 2] == 255))
    alpha = Image.fromarray((m * 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(1.2))
    rgba = im.convert("RGBA")
    rgba.putalpha(alpha)
    _crest = rgba.crop(alpha.getbbox())
    return _crest


def shot_crest(p, t, dur):
    k = ease(t / dur)
    if p.get("black"):
        bg = Image.new("RGB", (W, H), (0, 0, 0))
    else:
        bg = Image.fromarray(shot_flag({"dark": 0.18}, t, dur))
    cr = crest_cutout()
    z = lerp(p.get("z0", 0.9), p.get("z1", 1.0), k)
    h = int(H * 0.8 * z)
    w = int(cr.width * h / cr.height)
    c = cr.resize((w, h), Image.LANCZOS)
    # brilho: escudo "acende" lentamente
    glow_a = 0.0 if p.get("black") else 0.0
    out = bg.convert("RGBA")
    out.alpha_composite(c, ((W - w) // 2, (H - h) // 2 + int(p.get("y", 0) * H)))
    return np.asarray(out.convert("RGB"))


def shot_map_any(p, t, dur):
    return shot_map(p, t, dur)


SHOTS = {"photo": shot_photo, "crop": shot_crop, "broll": shot_broll, "flag": shot_flag,
         "black": shot_black, "map": shot_map, "sea": shot_sea, "rain": shot_rain, "crest": shot_crest}

FONTS = {"cond": FONT_COND, "bebas": FONT_BEBAS, "title": FONT_TITLE}


# ---------------------------------------------------------------- render global
XF = 0.7  # duração das fusões entre planos


def shot_frame(s, tg):
    """quadro do plano s no tempo global tg (o plano é estendido XF/2 em cada lado)"""
    t = tg - s["start"] + XF / 2
    dur = s["dur"] + XF
    fr = SHOTS[s["type"]](s, t, dur)
    fr = composite_text(fr, s.get("text"), t, dur, s.get("shade", 0.0))
    g = 1.0
    if s.get("fade_in"):
        g *= ease((t - XF / 2) / s["fade_in"])
    if s.get("fade_out"):
        g *= ease((dur - XF / 2 - t) / s["fade_out"])
    if g < 1:
        fr = (fr.astype(np.float32) * g).astype(np.uint8)
    return fr


def frame_at(shots, tg, fidx):
    i = 0
    while i + 1 < len(shots) and shots[i + 1]["start"] <= tg:
        i += 1
    s = shots[i]
    fr = shot_frame(s, tg)
    # fusão com o próximo plano (cortes "suaves")
    if i + 1 < len(shots):
        nxt = shots[i + 1]
        u = (tg - (nxt["start"] - XF / 2)) / XF
        if 0 < u < 1 and not nxt.get("hard"):
            fr = (fr.astype(np.float32) * (1 - u) + shot_frame(nxt, tg).astype(np.float32) * u).astype(np.uint8)
    if i > 0:
        prv = shots[i - 1]
        u = (tg - (s["start"] - XF / 2)) / XF
        if 0 < u < 1 and not s.get("hard"):
            fr = (shot_frame(prv, tg).astype(np.float32) * (1 - u) + fr.astype(np.float32) * u).astype(np.uint8)
    blk = s["type"] == "black"
    return finish(fr, fidx, grain=3.0 if blk else s.get("grain", 7.0), vignette=not blk)


def render_chunk(args):
    ci, f0, f1, out = args
    sys.path.insert(0, ROOT)
    from timeline import build
    shots, _ = build()
    cmd = ["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}",
           "-r", str(FPS), "-i", "-", "-c:v", "libx264", "-preset", "veryfast" if PREVIEW else "medium",
           "-crf", "26" if PREVIEW else "17", "-pix_fmt", "yuv420p", "-tune", "grain", out]
    pr = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    for f in range(f0, f1):
        pr.stdin.write(frame_at(shots, f / FPS, f).tobytes())
    pr.stdin.close()
    pr.wait()
    return out


def main():
    sys.path.insert(0, ROOT)
    from timeline import build
    shots, meta = build()
    total = meta["total"]
    nf = int(round(total * FPS))
    tag = "preview" if PREVIEW else "full"
    d = os.path.join(ROOT, f"build/chunks_{tag}")
    os.makedirs(d, exist_ok=True)
    stills = [a for a in sys.argv[1:] if a.startswith("--still=")]
    if stills:  # quadros de verificação: --still=12.5,40,...
        for ts in stills[0].split("=")[1].split(","):
            tg = float(ts)
            Image.fromarray(frame_at(shots, tg, int(tg * FPS))).save(os.path.join(ROOT, f"build/still_{tg:07.2f}.jpg"), quality=88)
        return
    step = int(8 * FPS)
    jobs = [(i, f0, min(nf, f0 + step), os.path.join(d, f"{i:03d}.mp4")) for i, f0 in enumerate(range(0, nf, step))]
    with ProcessPoolExecutor(max_workers=os.cpu_count()) as ex:
        for out in ex.map(render_chunk, jobs):
            print("ok", os.path.basename(out), flush=True)
    with open(os.path.join(d, "list.txt"), "w") as fh:
        for j in jobs:
            fh.write(f"file '{j[3]}'\n")
    print("frames:", nf, "total:", round(total, 2))


if __name__ == "__main__":
    main()
