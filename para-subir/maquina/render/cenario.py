"""Cenário "cidade à noite" em ilustração plana: céu roxo com estrelas, prédios com janelas acesas,
postes com brilho neon e carros passando. O cenário estático é desenhado uma vez; por quadro
só se recorta a janela (paralaxe lenta) e se desenham estrelas piscando e carros.
"""
import math
import random
from functools import lru_cache

import numpy as np
from PIL import Image, ImageChops, ImageDraw, ImageFilter

from .base import H, W, hex_rgb

MARGEM = 160                       # largura extra para a paralaxe
HORIZONTE = 1650                   # base dos prédios
RUA = 1720                         # início da rua
FAIXA_CARROS = 1840

C = {k: hex_rgb(v) for k, v in {
    "ceu_topo": "#0E0830", "ceu_meio": "#2A1A6B", "ceu_base": "#6A3FA8",
    "longe": "#3446A8", "longe2": "#2B3A93", "janela_fria": "#7FA8FF",
    "predio": "#45307F", "predio2": "#3A2770", "predio_luz": "#5A3F9C", "borda": "#2A1C58",
    "janela": "#FFC94A", "janela_off": "#2C2160", "loja": "#FFB347",
    "rua": "#2A1D5A", "calcada": "#3B2A78", "faixa": "#8C7BD6",
    "poste": "#B9A9E8", "luz_poste": "#FF9FC8", "estrela": "#FFFFFF",
}.items()}


def _gradiente(alt: int, larg: int, paradas: list[tuple[float, tuple]]) -> np.ndarray:
    y = np.linspace(0, 1, alt)
    canais = [np.interp(y, [p for p, _ in paradas], [c[i] for _, c in paradas]) for i in range(3)]
    img = np.stack(canais, axis=-1)[:, None, :]
    return np.broadcast_to(img, (alt, larg, 3)).astype(np.uint8)


def _janelas(d, x0, y0, x1, y1, rng, acesas=0.45, cor=None, tam=(26, 34), passo=(54, 64)):
    for y in range(y0, y1 - tam[1], passo[1]):
        for x in range(x0, x1 - tam[0], passo[0]):
            ligada = rng.random() < acesas
            d.rectangle((x, y, x + tam[0], y + tam[1]), fill=(cor or C["janela"]) if ligada else C["janela_off"])


@lru_cache(maxsize=1)
def cenario_base() -> tuple[Image.Image, list]:
    """Devolve a imagem estática (W+MARGEM x H) e a posição dos postes (para o brilho na rua)."""
    rng = random.Random(7)
    larg = W + MARGEM
    img = Image.fromarray(_gradiente(H, larg, [(0, C["ceu_topo"]), (0.45, C["ceu_meio"]),
                                                (HORIZONTE / H, C["ceu_base"]), (1, C["ceu_base"])]))
    d = ImageDraw.Draw(img)

    # Lua com halo
    luz = Image.new("RGB", (larg, H), (0, 0, 0))
    dl = ImageDraw.Draw(luz)
    dl.ellipse((larg - 330, 160, larg - 150, 340), fill=(120, 90, 170))

    # Skyline distante (azul, janelas frias)
    x = -20
    while x < larg:
        w, h = rng.randint(90, 170), rng.randint(300, 520)
        cor = C["longe"] if rng.random() < 0.5 else C["longe2"]
        d.rectangle((x, HORIZONTE - h, x + w, HORIZONTE), fill=cor)
        _janelas(d, x + 16, HORIZONTE - h + 24, x + w - 10, HORIZONTE - 40, rng, 0.18, C["janela_fria"],
                 tam=(10, 14), passo=(26, 30))
        x += w + rng.randint(-10, 20)

    # Prédios da frente (roxos, janelas amarelas, loja acesa embaixo)
    x = -40
    while x < larg:
        w, h = rng.randint(230, 330), rng.randint(220, 380)
        topo = HORIZONTE - h
        cor = C["predio"] if rng.random() < 0.5 else C["predio2"]
        d.rectangle((x, topo, x + w, HORIZONTE), fill=cor)
        d.rectangle((x - 8, topo - 18, x + w + 8, topo), fill=C["borda"])          # platibanda
        d.rectangle((x + w - 26, topo, x + w, HORIZONTE), fill=C["predio_luz"])    # lateral iluminada
        _janelas(d, x + 30, topo + 40, x + w - 40, HORIZONTE - 120, rng, 0.38, passo=(rng.choice((54, 62, 70)), 64))
        d.rectangle((x + 24, HORIZONTE - 90, x + w - 50, HORIZONTE - 10), fill=C["loja"])
        dl.rectangle((x + 24, HORIZONTE - 90, x + w - 50, HORIZONTE - 10), fill=(150, 90, 20))
        x += w + rng.randint(30, 90)

    # Calçada, rua e faixa de pedestres
    d.rectangle((0, HORIZONTE, larg, RUA), fill=C["calcada"])
    d.rectangle((0, RUA, larg, H), fill=C["rua"])
    for i in range(0, larg, 70):
        d.rectangle((i, RUA + 20, i + 40, RUA + 34), fill=C["faixa"])

    # Postes com brilho
    postes = []
    for px in range(120, larg, 420):
        d.rectangle((px - 6, 1240, px + 6, RUA + 10), fill=C["poste"])
        d.polygon([(px - 6, 1240), (px + 70, 1220), (px + 70, 1234), (px - 6, 1254)], fill=C["poste"])
        d.ellipse((px + 50, 1216, px + 100, 1242), fill=(255, 235, 245))
        dl.ellipse((px - 60, 1120, px + 210, 1340), fill=(255, 120, 180))
        dl.ellipse((px - 40, RUA + 30, px + 190, RUA + 110), fill=(150, 70, 120))   # reflexo na rua
        postes.append(px)

    luz = luz.filter(ImageFilter.GaussianBlur(55))
    img = ImageChops.screen(img, luz)

    estrelas = [(rng.randint(0, larg), rng.randint(0, 1300), rng.random() * 6.28, rng.choice((2, 2, 3, 4)))
                for _ in range(140)]
    return img, estrelas


def _carro(d, x, y, cor, sentido, t, policia=False):
    w, h = 230, 70
    d.rounded_rectangle((x, y - h, x + w, y), radius=22, fill=cor)
    d.rounded_rectangle((x + 40, y - h - 46, x + w - 50, y - h + 6), radius=20, fill=cor)
    d.rounded_rectangle((x + 56, y - h - 34, x + w - 66, y - h), radius=10, fill=(40, 30, 90))
    for rx in (x + 50, x + w - 50):
        d.ellipse((rx - 26, y - 22, rx + 26, y + 30), fill=(20, 14, 40))
    frente = x + w if sentido > 0 else x
    traseira = x if sentido > 0 else x + w
    d.polygon([(frente, y - 50), (frente + 320 * sentido, y - 90), (frente + 320 * sentido, y + 6), (frente, y - 30)],
              fill=(255, 225, 150))
    a, b = sorted((traseira - 6 * sentido, traseira))
    d.rectangle((a, y - 52, b, y - 34), fill=(255, 70, 90))
    if policia:
        azul = int(t * 6) % 2 == 0
        d.rounded_rectangle((x + 90, y - h - 62, x + 140, y - h - 46), radius=6,
                            fill=(80, 160, 255) if azul else (255, 70, 90))


_CARROS = [  # (velocidade px/s, sentido, cor, fase, policia, faixa)
    (420, 1, (110, 80, 200), 0.0, False, 0),
    (520, -1, (80, 190, 230), 0.4, False, 40),
    (600, 1, (235, 235, 255), 0.75, True, 0),
]


def quadro_cenario(t: float) -> Image.Image:
    base, estrelas = cenario_base()
    dx = int(MARGEM / 2 + (MARGEM / 2 - 10) * math.sin(t * 0.12))
    img = base.crop((dx, 0, dx + W, H))
    d = ImageDraw.Draw(img)
    for sx, sy, fase, r in estrelas:
        x = sx - dx
        if 0 <= x < W:
            brilho = 0.35 + 0.65 * (0.5 + 0.5 * math.sin(t * 2.2 + fase))
            c = tuple(int(v * brilho) for v in C["estrela"])
            d.ellipse((x - r / 2, sy - r / 2, x + r / 2, sy + r / 2), fill=c)
    ciclo = W + 900
    for vel, sentido, cor, fase, pol, faixa in _CARROS:
        pos = (t * vel + fase * ciclo) % ciclo - 450
        x = pos if sentido > 0 else W - pos
        _carro(d, x, FAIXA_CARROS + faixa, cor, sentido, t, pol)
    return img
