"""Tema visual, fontes, curvas de animação e texto com destaque (*palavra*)."""
import math
import os
from functools import lru_cache
from pathlib import Path

import numpy as np
from PIL import Image, ImageFont

from ..config import CFG, RAIZ, ErroConfig

W = CFG["video"]["largura"]
H = CFG["video"]["altura"]


def hex_rgb(h: str) -> tuple:
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


COR = {k: hex_rgb(v) for k, v in CFG["marca"]["cores"].items()}


def mix(a: tuple, b: tuple, t: float) -> tuple:
    t = max(0.0, min(1.0, t))
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


def fade(cor: tuple, alfa: float, fundo: tuple | None = None) -> tuple:
    """Simula transparência misturando com a cor de fundo (muito mais rápido que RGBA)."""
    return mix(fundo or COR["fundo"], cor, alfa)


# ---------- curvas ----------

def clamp(t: float) -> float:
    return max(0.0, min(1.0, t))


def ease_out(t: float) -> float:
    t = clamp(t)
    return 1 - (1 - t) ** 3


def ease_back(t: float, s: float = 1.70158) -> float:
    t = clamp(t) - 1
    return 1 + (s + 1) * t ** 3 + s * t ** 2


def entrada(t: float, atraso: float = 0.0, dur: float = 0.45) -> float:
    return ease_out((t - atraso) / dur)


# ---------- fontes ----------

_PASTAS_FONTE = [RAIZ / "assets" / "fontes", Path("C:/Windows/Fonts"),
                 Path(os.environ.get("LOCALAPPDATA", "")) / "Microsoft" / "Windows" / "Fonts"]


@lru_cache(maxsize=None)
def _arquivo_fonte(peso: str) -> str:
    """Primeiro arquivo da lista que existir. "Arquivo.ttf@ExtraBold" escolhe a variação de uma fonte variável."""
    for nome in CFG["marca"]["fontes"][peso]:
        arquivo, _, variacao = nome.partition("@")
        for pasta in _PASTAS_FONTE:
            if (pasta / arquivo).exists():
                return str(pasta / arquivo) + (f"@{variacao}" if variacao else "")
    raise ErroConfig(f"Nenhuma fonte '{peso}' encontrada. Coloque um .ttf em assets/fontes e ajuste config.yaml.")


@lru_cache(maxsize=512)
def fonte(peso: str, tamanho: int) -> ImageFont.FreeTypeFont:
    arquivo, _, variacao = _arquivo_fonte(peso).partition("@")
    f = ImageFont.truetype(arquivo, max(8, int(tamanho)))
    if variacao:
        f.set_variation_by_name(variacao)
    return f


# ---------- texto com destaque ----------

def tokens(texto: str) -> list[tuple[str, bool]]:
    """'Essa IA *edita sozinha*.' -> [('Essa',F),('IA',F),('edita',T),('sozinha.',T)]"""
    saida, destaque = [], False
    for bruto in str(texto).split():
        limpo, tem = "", False
        for ch in bruto:
            if ch == "*":
                destaque = not destaque
                continue
            limpo += ch
            tem = tem or destaque
        if limpo:
            saida.append((limpo, tem))
    return saida


def quebrar(toks: list, f: ImageFont.FreeTypeFont, largura: int) -> list[list]:
    espaco = f.getlength(" ")
    linhas, atual, w = [], [], 0.0
    for tok in toks:
        lw = f.getlength(tok[0])
        if atual and w + espaco + lw > largura:
            linhas.append(atual)
            atual, w = [], 0.0
        w = w + (espaco if atual else 0) + lw
        atual.append(tok)
    if atual:
        linhas.append(atual)
    return linhas


class Bloco:
    """Texto já quebrado em linhas com a fonte que coube."""

    def __init__(self, texto: str, peso: str, tam_max: int, tam_min: int, largura: int,
                 max_linhas: int, avisos: list | None = None, rotulo: str = ""):
        self.toks = tokens(texto)
        self.largura = largura
        tam = tam_max
        while True:
            self.f = fonte(peso, tam)
            self.linhas = quebrar(self.toks, self.f, largura)
            larga = any(self.f.getlength(t[0]) > largura for t in self.toks)
            if (len(self.linhas) <= max_linhas and not larga) or tam <= tam_min:
                break
            tam -= 4
        self.excedeu = len(self.linhas) > max_linhas or any(self.f.getlength(t[0]) > largura for t in self.toks)
        if self.excedeu and avisos is not None:
            avisos.append(f"{rotulo or 'texto'} não coube: \"{texto[:50]}\" (encurte)")
        self.entrelinha = int(self.f.size * 1.18)
        self.altura = self.entrelinha * len(self.linhas)
        self.n_palavras = len(self.toks)

    def desenhar(self, d, cx: float, y: float, cor: tuple, cor_dest: tuple, alfa: float = 1.0,
                 alinhar: str = "centro", revelar: float | None = None, fundo: tuple | None = None):
        """revelar: fração de palavras visíveis (0–1) para efeito palavra a palavra."""
        espaco = self.f.getlength(" ")
        visiveis = self.n_palavras if revelar is None else revelar * self.n_palavras
        k = 0
        for i, linha in enumerate(self.linhas):
            larg = sum(self.f.getlength(t[0]) for t in linha) + espaco * (len(linha) - 1)
            x = cx - larg / 2 if alinhar == "centro" else cx
            yy = y + i * self.entrelinha
            for palavra, dest in linha:
                a = alfa * clamp(visiveis - k)
                if a > 0.01:
                    d.text((x, yy), palavra, font=self.f, fill=fade(cor_dest if dest else cor, a, fundo))
                x += self.f.getlength(palavra) + espaco
                k += 1


def texto_simples(d, txt: str, f, cx: float, cy: float, cor: tuple):
    d.text((cx, cy), txt, font=f, fill=cor, anchor="mm")


# ---------- fundo ----------

@lru_cache(maxsize=1)
def fundo_base() -> Image.Image:
    y = np.linspace(0, 1, H)[:, None, None]
    a, b = np.array(COR["fundo2"], float), np.array(COR["fundo"], float)
    img = a * (1 - y) + b * y
    img = np.broadcast_to(img, (H, W, 3)).copy()
    yy, xx = np.mgrid[0:H, 0:W]
    for (cx, cy, raio, cor, forca) in [(150, 300, 700, COR["violeta"], 0.22),
                                       (W - 100, H - 350, 800, COR["menta"], 0.12)]:
        dist = np.sqrt((xx - cx) ** 2 + (yy - cy) ** 2) / raio
        peso = (np.clip(1 - dist, 0, 1) ** 2 * forca)[..., None]
        img = img * (1 - peso) + np.array(cor, float) * peso
    return Image.fromarray(img.astype(np.uint8), "RGB")


def ondas(d, cx: float, cy: float, t: float, largura: int = 520, n: int = 26, alt: int = 90, alfa: float = 1.0):
    passo = largura / n
    for i in range(n):
        h = alt * (0.25 + 0.75 * abs(math.sin(t * 5.5 + i * 0.55) * math.sin(t * 2.1 + i * 0.27)))
        x = cx - largura / 2 + i * passo
        cor = fade(mix(COR["violeta"], COR["menta"], i / n), alfa)
        d.rounded_rectangle((x, cy - h / 2, x + passo * 0.55, cy + h / 2), radius=int(passo * 0.27), fill=cor)
