"""Estilo "colagem retrô": papel texturizado, recortes com borda de papel e sombra, meio-tom,
tipografia de carimbo/máquina de escrever, granulado de filme e movimento de stop-motion (12 fps).

As cenas têm os mesmos tipos e campos de cenas.py (o roteiro não muda); só o desenho é outro.
Cada recorte é montado uma vez em preparar() e depois apenas colado, girado e escalado por quadro.
"""
import math
import random
import zlib
from functools import lru_cache

import numpy as np
from PIL import Image, ImageChops, ImageDraw, ImageFilter

from ..config import CFG
from . import cenas as cn
from .base import COR, H, W, Bloco, clamp, ease_back, ease_out, fonte, tokens

FPS_ANIM = CFG["video"].get("fps_animacao", 12)
LEGENDA_Y = 1400
LARG = cn.LARG
TINTA, PAPEL, CARTAO = COR["texto"], COR["fundo"], COR["card"]
BRANCO = (252, 249, 241)
LARANJA, TEAL, MOSTARDA = COR["menta"], COR["violeta"], COR["ambar"]
CARMIM, MAGENTA = COR["vermelho"], COR.get("magenta", (195, 60, 122))
KRAFT = (196, 170, 128)


def tq(t: float) -> float:
    """Tempo em degraus de 12 fps: o "salto" do stop-motion."""
    return math.floor(t * FPS_ANIM) / FPS_ANIM


def _rng(*chave) -> random.Random:
    return random.Random(zlib.crc32(repr(chave).encode()))


def tremor(*chave, amp: float = 2.0) -> tuple[float, float]:
    r = _rng(*chave)
    return r.uniform(-amp, amp), r.uniform(-amp, amp)


# ---------------- texturas ----------------

def _ruido(w: int, h: int, escala: int, seed: int) -> np.ndarray:
    g = np.random.default_rng(seed)
    peq = (g.random((max(2, h // escala + 2), max(2, w // escala + 2))) * 255).astype(np.uint8)
    return np.asarray(Image.fromarray(peq).resize((w, h), Image.BICUBIC), np.float32) / 255


def papel(w: int, h: int, cor: tuple, seed: int = 0, forca: float = 1.0) -> Image.Image:
    """Papel envelhecido: variação de tom, manchas sépia e fibras."""
    base = np.ones((h, w, 3), np.float32) * np.array(cor, np.float32)
    var = ((_ruido(w, h, 160, seed) - 0.5) * 26 + (_ruido(w, h, 24, seed + 1) - 0.5) * 12
           + (np.random.default_rng(seed + 2).random((h, w), np.float32) - 0.5) * 10) * forca
    base += var[..., None]
    mancha = np.clip((_ruido(w, h, 220, seed + 3) - 0.6) * 3, 0, 1)[..., None] * 0.16 * forca
    base = base * (1 - mancha) + np.array((140, 100, 55), np.float32) * mancha
    img = Image.fromarray(np.clip(base, 0, 255).astype(np.uint8))
    d, r = ImageDraw.Draw(img), random.Random(seed)
    for _ in range(int(w * h / 7000 * forca)):
        x, y, comp, ang = r.randrange(w), r.randrange(h), r.randint(6, 24), r.uniform(0, math.pi)
        c = tuple(max(0, v - r.randint(10, 28)) for v in cor)
        d.line((x, y, x + comp * math.cos(ang), y + comp * math.sin(ang)), fill=c, width=1)
    return img


def meio_tom(w: int, h: int, cor: tuple, passo: int = 20, raio: float = 7, forma: str = "radial") -> Image.Image:
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    cx, cy = w / 2, h / 2
    for y in range(0, h, passo):
        desloc = passo / 2 if (y // passo) % 2 else 0
        for x in range(int(desloc), w, passo):
            f = 1 - math.hypot(x - cx, y - cy) / min(cx, cy) if forma == "radial" else 1 - y / h
            r = raio * max(0.0, f)
            if r > 0.7:
                d.ellipse((x - r, y - r, x + r, y + r), fill=cor + (255,))
    return img


def _mascara(w: int, h: int, forma: str, seed: int) -> Image.Image:
    m = Image.new("L", (w, h), 0)
    d = ImageDraw.Draw(m)
    if forma == "pilula":
        d.rounded_rectangle((0, 0, w - 1, h - 1), radius=h // 2, fill=255)
    elif forma == "bandeira":
        k = min(34, h // 2)
        d.polygon([(0, 0), (w, 0), (w - k, h / 2), (w, h), (0, h), (k, h / 2)], fill=255)
    elif forma == "circulo":
        d.ellipse((0, 0, w - 1, h - 1), fill=255)
    elif forma == "rasgado":
        r = _rng("rasgo", seed)
        topo = [(x, r.randint(0, 16)) for x in range(0, w + 18, 18)]
        base = [(x, h - r.randint(0, 16)) for x in range(w + 18, -18, -18)]
        d.polygon(topo + base, fill=255)
    else:
        d.rectangle((0, 0, w, h), fill=255)
    return m


def recorte(conteudo: Image.Image, borda: int = 12, sombra: tuple = (9, 13), seed: int = 0,
            cor_borda: tuple = BRANCO) -> Image.Image:
    """Borda de papel recortado à mão (irregular) e sombra suave de camada sobreposta."""
    w, h = conteudo.size
    pad = borda + max(sombra) + 18
    W2, H2 = w + 2 * pad, h + 2 * pad
    a = Image.new("L", (W2, H2), 0)
    a.paste(conteudo.getchannel("A"), (pad, pad))
    b = np.asarray(a.filter(ImageFilter.GaussianBlur(max(1, borda / 2))), np.float32) / 255
    contorno = Image.fromarray(((b > 0.04 + 0.12 * _ruido(W2, H2, 5, seed)) * 255).astype(np.uint8))
    som = Image.new("L", (W2, H2), 0)
    som.paste(contorno.filter(ImageFilter.GaussianBlur(7)).point(lambda v: int(v * 0.45)), sombra)
    out = Image.new("RGBA", (W2, H2), (45, 32, 20, 0))
    out.putalpha(som)
    camada = Image.new("RGBA", (W2, H2), cor_borda + (0,))
    camada.putalpha(contorno)
    out.alpha_composite(camada)
    out.alpha_composite(conteudo, dest=(pad, pad))
    return out


class Adesivo:
    """Recorte pronto para colar: guarda as versões giradas/escaladas já calculadas."""

    def __init__(self, conteudo: Image.Image, seed: int = 0, borda: int = 12):
        self.img = recorte(conteudo, borda=borda, seed=seed)
        self._cache: dict = {}

    def colar(self, base: Image.Image, cx: float, cy: float, ang: float = 0.0, esc: float = 1.0):
        chave = (round(ang * 2) / 2, round(max(esc, 0.05) * 20) / 20)
        r = self._cache.get(chave)
        if r is None:
            r = self.img
            if chave[1] != 1:
                r = r.resize((max(1, int(r.width * chave[1])), max(1, int(r.height * chave[1]))), Image.BICUBIC)
            if chave[0]:
                r = r.rotate(chave[0], resample=Image.BICUBIC, expand=True)
            if len(self._cache) > 60:
                self._cache.clear()
            self._cache[chave] = r
        base.paste(r, (int(cx - r.width / 2), int(cy - r.height / 2)), r)


def impresso(texto: str, peso: str, tam_max: int, tam_min: int, largura: int, max_linhas: int,
             fundo: tuple, cor: tuple, cor_dest: tuple, pad=(44, 28), forma="ret", seed=0,
             avisos=None, rotulo="", alinhar="centro", extra_esq=0, desgaste=True) -> Image.Image:
    """Papel com texto impresso: linha de base irregular e tinta levemente falhada."""
    bl = Bloco(texto, peso, tam_max, tam_min, largura - 2 * pad[0] - extra_esq, max_linhas, avisos, rotulo)
    esp = bl.f.getlength(" ")
    larg = [sum(bl.f.getlength(t[0]) for t in l) + esp * (len(l) - 1) for l in bl.linhas] or [10]
    cw, ch = int(max(larg) + 2 * pad[0] + extra_esq), int(bl.altura + 2 * pad[1])
    img = papel(cw, ch, fundo, seed, 0.6).convert("RGBA")
    m_txt, m_dest = Image.new("L", (cw, ch), 0), Image.new("L", (cw, ch), 0)
    dt, dd = ImageDraw.Draw(m_txt), ImageDraw.Draw(m_dest)
    r = _rng("impresso", texto, seed)
    for i, linha in enumerate(bl.linhas):
        x = pad[0] + extra_esq + ((max(larg) - larg[i]) / 2 if alinhar == "centro" else 0)
        y = pad[1] + i * bl.entrelinha
        for palavra, dest in linha:
            (dd if dest else dt).text((x, y + r.randint(-3, 3)), palavra, font=bl.f, fill=255)
            x += bl.f.getlength(palavra) + esp
    if desgaste:
        falha = Image.fromarray(((np.random.default_rng(seed + 9).random((ch, cw)) > 0.07) * 255).astype(np.uint8))
        m_txt = Image.fromarray(np.minimum(np.asarray(m_txt), np.asarray(falha)))
        m_dest = Image.fromarray(np.minimum(np.asarray(m_dest), np.asarray(falha)))
    img.paste(cor + (255,), (0, 0), m_txt)
    img.paste(cor_dest + (255,), (0, 0), m_dest)
    img.putalpha(_mascara(cw, ch, forma, seed))
    return img


def fichas(texto: str, tam_max: int, tam_min: int, max_linhas: int, cy: float, avisos: list, rotulo: str):
    """Título em palavras recortadas (estilo letras de revista), cada uma num pedaço de papel."""
    toks = tokens(texto)
    padx, gap = 22, 12
    for tam in range(tam_max, tam_min - 1, -6):
        f = fonte("titulo", tam)
        larguras = [f.getlength(w) + 2 * padx + 2 * 30 for w, _ in toks]   # + borda do recorte
        linhas, atual, acum = [], [], 0.0
        for i, lw in enumerate(larguras):
            if atual and acum + gap + lw > LARG + 60:
                linhas.append(atual)
                atual, acum = [], 0.0
            atual.append(i)
            acum += lw + (gap if len(atual) > 1 else 0)
        if atual:
            linhas.append(atual)
        if len(linhas) <= max_linhas:
            break
    else:
        avisos.append(f"{rotulo} não coube: \"{texto[:50]}\" (encurte)")
    alt_linha = tam * 1.18 + 2 * 14 + 30
    y0 = cy - alt_linha * len(linhas) / 2 + alt_linha / 2
    r = _rng("fichas", texto)
    saida, k = [], 0
    for li, linha in enumerate(linhas):
        total = sum(larguras[i] for i in linha) + gap * (len(linha) - 1)
        x = W / 2 - total / 2
        for i in linha:
            w, dest = toks[i]
            fundo, cor = (LARANJA, BRANCO) if dest else (CARTAO, TINTA)
            img = impresso(w, "titulo", tam, tam, 5000, 1, fundo, cor, cor, pad=(padx, 14), seed=k, desgaste=False)
            saida.append((Adesivo(img, seed=k), x + larguras[i] / 2, y0 + li * alt_linha + r.uniform(-6, 6),
                          r.uniform(-3.5, 3.5)))
            x += larguras[i] + gap
            k += 1
    return saida


# ---------------- fundo ----------------

# ---------------- marca (Odisys) ----------------

GRAD = [(0.0, (74, 37, 214)), (0.55, (124, 92, 248)), (1.0, (167, 139, 255))]  # --gradient-odisys


def gradiente(w: int, h: int) -> Image.Image:
    """Gradiente da marca a 135° (de baixo-esquerda para cima-direita)."""
    yy, xx = np.mgrid[0:h, 0:w]
    t = np.clip((xx / max(1, w - 1) + (1 - yy / max(1, h - 1))) / 2, 0, 1)
    canais = [np.interp(t, [p for p, _ in GRAD], [c[i] for _, c in GRAD]) for i in range(3)]
    return Image.fromarray(np.stack(canais, -1).astype(np.uint8)).convert("RGBA")


@lru_cache(maxsize=4)
def isotipo(tam: int) -> Image.Image:
    """Isotipo "Sequência": arco de 134u, vão, arco de 40u, vão, ponto (r=34u, traço 13u, pontas redondas)."""
    s = tam * 4 / 100  # desenha 4x maior e reduz, para bordas suaves
    m = Image.new("L", (tam * 4, tam * 4), 0)
    d = ImageDraw.Draw(m)
    r, w = 34 * s, 13 * s
    c = 50 * s
    grau = 360 / (2 * math.pi * 34)

    def ponta(a):
        x, y = c + r * math.cos(math.radians(a)), c + r * math.sin(math.radians(a))
        d.ellipse((x - w / 2, y - w / 2, x + w / 2, y + w / 2), fill=255)

    a = -90.0
    for comp in (134, 40, 0.1):
        fim = a + comp * grau
        if comp > 1:
            d.arc((c - r - w / 2, c - r - w / 2, c + r + w / 2, c + r + w / 2), a, fim, fill=255, width=int(w))
        ponta(a)
        ponta(fim)
        a = fim + 13 * grau + w / (2 * r) * 57.3 * 2  # vão igual à espessura, já contando as pontas
    img = gradiente(tam * 4, tam * 4)
    img.putalpha(m)
    return img.resize((tam, tam), Image.LANCZOS)


# Variações de base: (cor do papel, cor da faixa de baixo, cores do meio-tom, extra)
FUNDOS = {
    "papel": (PAPEL, KRAFT, (TEAL, LARANJA), None),
    "kraft": (KRAFT, CARTAO, (LARANJA, TEAL), None),
    "quadro": ((44, 56, 50), KRAFT, (MOSTARDA, (230, 230, 220)), "giz"),
    "papelao": ((176, 138, 92), (52, 46, 40), (LARANJA, (250, 240, 220)), "ondulado"),
    "grafite": ((22, 21, 28), (44, 42, 52), (LARANJA, MAGENTA), None),  # escuro nativo da Odisys
}


@lru_cache(maxsize=8)
def fundo_colagem(variante: str = "papel") -> Image.Image:
    base, cor_faixa, (mt1, mt2), extra = FUNDOS.get(variante, FUNDOS["papel"])
    img = papel(W, H, base, seed=11, forca=0.7 if extra == "giz" else 1.0)
    arr = np.asarray(img, np.float32)
    yy, xx = np.mgrid[0:H, 0:W]
    if extra == "giz":  # manchas de giz apagado
        borrao = np.clip((_ruido(W, H, 90, 31) - 0.45) * 2.2, 0, 1)[..., None] * 0.22
        arr = arr * (1 - borrao) + 235 * borrao
    if extra == "ondulado":  # caneluras do papelão
        arr *= (1 - 0.07 * (0.5 + 0.5 * np.sin(xx / 7.0)))[..., None]
    vin = np.clip(np.hypot((xx - W / 2) / (W * 0.62), (yy - H / 2) / (H * 0.62)), 0, 1) ** 2.2
    img = Image.fromarray(np.clip(arr * (1 - 0.22 * vin[..., None]), 0, 255).astype(np.uint8)).convert("RGBA")
    # Pontos de meio-tom nos cantos, como impressão antiga.
    img.alpha_composite(meio_tom(520, 520, mt1, 22, 8), dest=(W - 330, 40))
    img.alpha_composite(meio_tom(460, 460, mt2, 20, 7), dest=(-160, 900))
    # Faixa de papel rasgado na base (onde fica a interface do Shorts).
    faixa = papel(W + 80, 460, cor_faixa, seed=5).convert("RGBA")
    faixa.putalpha(_mascara(W + 80, 460, "rasgado", 5))
    faixa = recorte(faixa, borda=0, sombra=(0, -10), seed=5)
    img.alpha_composite(faixa, dest=(-60 - 40, 1520 - 40))
    # Fita adesiva no canto.
    fita = Image.new("RGBA", (230, 64), (236, 226, 190, 200))
    fita = fita.rotate(-28, expand=True, resample=Image.BICUBIC)
    img.alpha_composite(fita, dest=(-30, 60))
    if CFG["marca"].get("logo"):  # assinatura Odisys: isotipo em gradiente, sem contorno nem sombra
        img.alpha_composite(isotipo(84), dest=(W - 84 - 60, 150))
    return img.convert("RGB")


@lru_cache(maxsize=1)
def _graos() -> list:
    """3 pares (clarear, escurecer) de granulado; somar/subtrair imagens é rápido no PIL."""
    g = np.random.default_rng(3)
    pares = []
    for _ in range(3):
        n = np.repeat(g.normal(0, 7, (H, W, 1)), 3, axis=2)
        pares.append((Image.fromarray(np.clip(n, 0, 255).astype(np.uint8)),
                      Image.fromarray(np.clip(-n, 0, 255).astype(np.uint8))))
    return pares


def granular(img: Image.Image, passo: int) -> Image.Image:
    clarear, escurecer = _graos()[passo % 3]
    return ImageChops.subtract(ImageChops.add(img, clarear), escurecer)


# ---------------- cenas ----------------

def _entra(t, atraso, dur=0.3):
    return (t - atraso) / dur


class Gancho(cn.Gancho):
    def preparar(self):
        self.fichas = fichas(self.dados["texto"], 112, 64, 4, 780, self.avisos, "gancho.texto")
        self.selo = None
        if self.dados.get("selo"):
            img = impresso(self.dados["selo"].upper(), "carimbo", 46, 36, 700, 1, LARANJA, BRANCO, BRANCO,
                           pad=(56, 14), forma="bandeira", seed=3)
            self.selo = Adesivo(img, seed=3)
        topo = min(c[2] for c in self.fichas)
        self.y_selo = topo - 130
        self.mt = meio_tom(760, 760, TEAL, 24, 9)

    def compor(self, img, t):
        dx, dy = tremor("mt", int(t * 6), amp=3)
        img.paste(self.mt, (int(W / 2 - 380 + dx), int(780 - 380 + dy)), self.mt)
        if self.selo:
            p = _entra(t, 0.0, 0.25)
            if p > 0:
                self.selo.colar(img, W / 2 - 180, self.y_selo, -6 + math.sin(t * 1.5), ease_back(p))
        for i, (ad, x, y, ang) in enumerate(self.fichas):
            p = _entra(t, 0.08 + i * 0.07, 0.25)
            if p <= 0:
                continue
            jx, jy = tremor("f", i, int(t * 6))
            ad.colar(img, x + jx, y + jy, ang + 0.8 * math.sin(t * 1.7 + i), ease_back(p))


class Numero(cn.Numero):
    def preparar(self):
        # Não chama super().preparar(): o rótulo do estilo base mediria a fonte errada e duplicaria avisos.
        self.v = float(self.dados["valor"])
        self.decimais = 0 if self.v == int(self.v) else 1
        dia = 600
        disco = papel(dia, dia, MOSTARDA, seed=21).convert("RGBA")
        disco.alpha_composite(meio_tom(dia, dia, (190, 120, 30), 18, 6))
        cobre = papel(dia - 120, dia - 120, MOSTARDA, seed=22).convert("RGBA")
        cobre.putalpha(_mascara(dia - 120, dia - 120, "circulo", 0))
        disco.alpha_composite(cobre, dest=(60, 60))
        disco.putalpha(_mascara(dia, dia, "circulo", 0))
        self.disco = Adesivo(disco, seed=21, borda=14)
        self.dia = dia
        self.tam = 220
        while fonte("titulo", self.tam).getlength(self._fmt(self.v)) > dia - 150 and self.tam > 80:
            self.tam -= 8
        self.rot = Adesivo(impresso(self.dados["rotulo"], "maquina", 66, 44, LARG, 3, CARTAO, TINTA, LARANJA,
                                    pad=(40, 26), seed=23, avisos=self.avisos, rotulo="numero.rotulo"), seed=23)

    def compor(self, img, t):
        cy = 600 + 6 * math.sin(t * 2)
        p = _entra(t, 0.0, 0.3)
        if p <= 0:
            return
        self.disco.colar(img, W / 2, cy, 0, ease_back(p))
        if p >= 1:
            d = ImageDraw.Draw(img)
            txt = self._fmt(self.v * ease_out((t - 0.2) / 1.1))
            f = fonte("titulo", self.tam)
            d.text((W / 2 + 6, cy + 8), txt, font=f, fill=(150, 98, 30), anchor="mm")
            d.text((W / 2, cy), txt, font=f, fill=TINTA, anchor="mm")
        q = _entra(t, 0.45, 0.35)
        if q > 0:
            self.rot.colar(img, W / 2 - (1 - ease_back(q)) * 1000, cy + self.dia / 2 + 150, -2 + 0.6 * math.sin(t * 1.4))


class Lista(cn.Lista):
    def preparar(self):
        self.tit = None
        if self.dados.get("titulo"):
            self.tit = Adesivo(impresso(self.dados["titulo"], "titulo", 78, 50, LARG, 2, TEAL, BRANCO, MOSTARDA,
                                        pad=(70, 22), forma="bandeira", seed=31, avisos=self.avisos,
                                        rotulo="lista.titulo"), seed=31)
        itens = self.dados["itens"][:5]
        if len(self.dados["itens"]) > 5:
            self.avisos.append("lista: mais de 5 itens (só os 5 primeiros aparecem)")
        self.itens = []
        for i, txt in enumerate(itens):
            img = impresso(txt, "maquina", 66, 44, LARG - 20, 2, CARTAO, TINTA, LARANJA, pad=(36, 30),
                           seed=40 + i, avisos=self.avisos, rotulo="lista.item", alinhar="esquerda", extra_esq=100)
            d = ImageDraw.Draw(img)
            cy = img.height / 2
            d.ellipse((30, cy - 38, 106, cy + 38), fill=LARANJA + (255,))
            if self.dados.get("numerada"):
                d.text((68, cy + 2), str(i + 1), font=fonte("bloco", 44), fill=BRANCO, anchor="mm")
            else:  # check desenhado (as fontes retrô não têm o símbolo ✓)
                d.line([(50, cy + 2), (63, cy + 16), (88, cy - 14)], fill=BRANCO, width=10, joint="curve")
            self.itens.append(Adesivo(img, seed=40 + i))
        alturas = [a.img.height - 50 for a in self.itens]
        total = sum(alturas) + 10 * len(alturas) + (self.tit.img.height if self.tit else 0)
        y = 800 - total / 2
        self.pos = []
        if self.tit:
            self.y_tit = y + self.tit.img.height / 2 - 20
            y += self.tit.img.height
        for h in alturas:
            self.pos.append(y + h / 2)
            y += h + 10
        self.passo = min(0.9, self.dur * 0.7 / max(1, len(self.itens)))

    def compor(self, img, t):
        if self.tit:
            p = _entra(t, 0.0, 0.3)
            if p > 0:
                self.tit.colar(img, W / 2 + (1 - ease_back(p)) * -900, self.y_tit, -1.5)
        for i, (ad, y) in enumerate(zip(self.itens, self.pos)):
            p = _entra(t, 0.25 + i * self.passo, 0.3)
            if p <= 0:
                break
            jx, jy = tremor("l", i, int(t * 6), amp=1.5)
            ang = (1.4 if i % 2 else -1.4) + 0.5 * math.sin(t * 1.6 + i)
            ad.colar(img, W / 2 + (1 - ease_back(p)) * 1100 + jx, y + jy, ang)


def _cartao_itens(itens, fundo, largura, seed, avisos, rotulo):
    blocos = [Bloco("• " + i, "maquina", 64, 44, largura - 100, 2, avisos, rotulo) for i in itens[:3]]
    ch = int(sum(b.altura + 18 for b in blocos) + 110)
    img = papel(largura, ch, fundo, seed, 0.6).convert("RGBA")
    d = ImageDraw.Draw(img)
    y = 70
    for b in blocos:
        b.desenhar(d, 50, y, TINTA, LARANJA, alinhar="esquerda", fundo=fundo)
        y += b.altura + 18
    return img


class Comparacao(cn.Comparacao):
    def preparar(self):
        self.cards = []
        for k, (chave, cor) in enumerate((("antes", CARMIM), ("depois", TEAL))):
            lado = self.dados[chave]
            card = Adesivo(_cartao_itens(lado.get("itens", []), CARTAO, LARG - 40, 50 + k, self.avisos,
                                         f"comparacao.{chave}"), seed=50 + k)
            rot = Adesivo(impresso(lado.get("titulo", "").upper(), "carimbo", 42, 32, 600, 1, cor, BRANCO, BRANCO,
                                   pad=(40, 12), forma="pilula", seed=60 + k), seed=60 + k)
            self.cards.append((card, rot))
        self.vs = Adesivo(impresso("VS", "carimbo", 54, 54, 400, 1, MAGENTA, BRANCO, BRANCO, pad=(34, 30),
                                   forma="circulo", seed=70), seed=70)
        alts = [c.img.height - 50 for c, _ in self.cards]
        gap = 120
        y = 800 - (sum(alts) + gap) / 2
        self.ys = [y + alts[0] / 2, y + alts[0] + gap + alts[1] / 2]
        self.alts = alts
        self.t2 = max(0.6, self.dur * 0.4)

    def compor(self, img, t):
        for k, ((card, rot), y) in enumerate(zip(self.cards, self.ys)):
            atraso = 0.05 if k == 0 else self.t2
            p = _entra(t, atraso, 0.32)
            if p <= 0:
                continue
            lado = -1 if k == 0 else 1
            ang = (-1.5 if k == 0 else 1.2) + 0.4 * math.sin(t * 1.5 + k)
            card.colar(img, W / 2 + lado * (1 - ease_back(p)) * 1100, y, ang)
            q = _entra(t, atraso + 0.2, 0.25)
            if q > 0:
                rot.colar(img, W / 2 - 230, y - self.alts[k] / 2 + 6, -4 if k == 0 else 3, ease_back(q))
        q = _entra(t, self.t2 + 0.3, 0.25)
        if q > 0:
            self.vs.colar(img, W / 2 + LARG / 2 - 70, (self.ys[0] + self.ys[1]) / 2, 8, ease_back(q))


class Citacao(cn.Citacao):
    def preparar(self):
        self.nota = Adesivo(impresso(self.dados["texto"], "titulo", 72, 46, LARG, 6, CARTAO, TINTA, LARANJA,
                                     pad=(64, 80), forma="rasgado", seed=81, avisos=self.avisos,
                                     rotulo="citacao.texto"), seed=81)
        self.autor = None
        if self.dados.get("autor"):
            self.autor = Adesivo(impresso("— " + self.dados["autor"], "maquina", 44, 32, LARG - 100, 1, MOSTARDA,
                                          TINTA, TINTA, pad=(36, 16), seed=82), seed=82)

    def compor(self, img, t):
        p = _entra(t, 0.0, 0.35)
        if p <= 0:
            return
        y = 760 + (1 - ease_back(p)) * 900
        self.nota.colar(img, W / 2, y, -2 + 0.6 * math.sin(t * 1.3))
        d = ImageDraw.Draw(img)
        topo = y - self.nota.img.height / 2
        f = fonte("titulo", 260)
        d.text((cn.X0 + 26, topo + 150), "“", font=f, fill=(120, 40, 70), anchor="ls")
        d.text((cn.X0 + 20, topo + 142), "“", font=f, fill=MAGENTA, anchor="ls")
        if self.autor:
            q = _entra(t, 0.7, 0.25)
            if q > 0:
                self.autor.colar(img, W / 2 + 140, y + self.nota.img.height / 2 + 10, 3, ease_back(q))


class Alerta(cn.Alerta):
    def preparar(self):
        ti = Bloco(self.dados["titulo"].upper(), "carimbo", 78, 54, LARG - 140, 1, self.avisos, "alerta.titulo")
        tx = Bloco(self.dados["texto"], "maquina", 62, 42, LARG - 140, 5, self.avisos, "alerta.texto")
        cw, ch = LARG - 20, int(ti.altura + tx.altura + 290)
        img = papel(cw, ch, MOSTARDA, seed=91).convert("RGBA")
        d = ImageDraw.Draw(img)
        d.ellipse((cw / 2 - 62, 36, cw / 2 + 62, 160), fill=CARMIM + (255,))
        d.text((cw / 2, 100), "!", font=fonte("bloco", 86), fill=BRANCO, anchor="mm")
        ti.desenhar(d, cw / 2, 190, CARMIM, CARMIM, fundo=MOSTARDA)
        tx.desenhar(d, cw / 2, 210 + ti.altura, TINTA, CARMIM, fundo=MOSTARDA)
        self.card = Adesivo(img, seed=91)
        fita = Image.new("RGBA", (W + 300, 74), MOSTARDA + (255,))
        df = ImageDraw.Draw(fita)
        for x in range(-80, W + 300, 90):
            df.polygon([(x, 0), (x + 45, 0), (x + 90, 74), (x + 45, 74)], fill=TINTA + (255,))
        self.fita = Adesivo(fita, seed=92, borda=4)
        self.ch = ch

    def compor(self, img, t):
        p = _entra(t, 0.0, 0.3)
        if p > 0:
            self.fita.colar(img, W / 2 + (1 - ease_out(p)) * -1400, 800 - self.ch / 2 - 70, 6)
            self.fita.colar(img, W / 2 + (1 - ease_out(p)) * 1400, 800 + self.ch / 2 + 70, -5)
        q = _entra(t, 0.12, 0.3)
        if q > 0:
            balanco = 1.2 * math.sin(t * 7) if t < 1.2 else 0.5 * math.sin(t * 1.5)
            self.card.colar(img, W / 2, 800, balanco, ease_back(q))


class Palavra(cn.Palavra):
    def preparar(self):
        self.pal = str(self.dados["palavra"]).upper()
        self.ad = Adesivo(impresso(self.pal, "bloco", 210, 70, LARG + 40, 1, LARANJA, BRANCO, BRANCO,
                                   pad=(50, 30), seed=101, avisos=self.avisos, rotulo="palavra"), seed=101)
        self.sub = None
        if self.dados.get("texto"):
            self.sub = Adesivo(impresso(self.dados["texto"], "maquina", 62, 42, LARG, 3, CARTAO, TINTA, LARANJA,
                                        pad=(40, 24), seed=102, avisos=self.avisos, rotulo="palavra.texto"), seed=102)

    def compor(self, img, t):
        p = _entra(t, 0.0, 0.35)
        if p <= 0:
            return
        self.ad.colar(img, W / 2, 720, -3 + 1.5 * math.sin(t * 2.2), ease_back(p))
        if self.sub:
            q = _entra(t, 0.4, 0.3)
            if q > 0:
                self.sub.colar(img, W / 2 + (1 - ease_back(q)) * 1000, 720 + self.ad.img.height / 2 + 110, 2)


class Cta(cn.Cta):
    def preparar(self):
        self.fichas = fichas(self.dados["texto"], 100, 60, 3, 600, self.avisos, "cta.texto")
        # Botão primário da marca: gradiente Odisys, cantos de 8px (escala 1080p ≈ 26px), texto branco.
        rotulo = str(self.dados.get("botao") or "Siga para mais")
        f = fonte("bloco", 60)
        bw, bh = int(f.getlength(rotulo) + 140), 140
        bt = gradiente(bw, bh)
        ImageDraw.Draw(bt).text((bw / 2, bh / 2), rotulo, font=f, fill=BRANCO, anchor="mm")
        mascara = Image.new("L", (bw, bh), 0)
        ImageDraw.Draw(mascara).rounded_rectangle((0, 0, bw - 1, bh - 1), radius=26, fill=255)
        bt.putalpha(mascara)
        self.bt = Adesivo(bt, seed=111)
        self.y_bt = max(c[2] for c in self.fichas) + 260

    def compor(self, img, t):
        for i, (ad, x, y, ang) in enumerate(self.fichas):
            p = _entra(t, i * 0.06, 0.25)
            if p > 0:
                jx, jy = tremor("c", i, int(t * 6))
                ad.colar(img, x + jx, y + jy, ang + 0.6 * math.sin(t * 1.7 + i), ease_back(p))
        q = _entra(t, 0.35, 0.3)
        if q > 0:
            pulso = 1.0 + 0.05 * (int(t * 4) % 2)
            self.bt.colar(img, W / 2, self.y_bt, -2, ease_back(q) * pulso)
            d = ImageDraw.Draw(img)
            jx, jy = tremor("seta", int(t * 6), amp=3)
            x0, y0 = 150 + jx, self.y_bt + 210 + jy
            pts = [(x0 + k * 30, y0 - 90 * math.sin(k / 9 * math.pi / 2)) for k in range(10)]
            d.line(pts, fill=TINTA, width=12, joint="curve")
            fx, fy = pts[-1]
            d.polygon([(fx + 40, fy - 20), (fx - 10, fy - 50), (fx - 4, fy + 14)], fill=TINTA)


# ---------------- cenas com imagem (prints do vídeo original) ----------------

def carregar(imagem: str, recorte_frac=None) -> Image.Image:
    """Abre a imagem (caminho já resolvido pelo roteiro) e corta pela fração [x0, y0, x1, y1]."""
    im = Image.open(imagem).convert("RGB")
    if recorte_frac:
        x0, y0, x1, y1 = recorte_frac
        im = im.crop((int(x0 * im.width), int(y0 * im.height), int(x1 * im.width), int(y1 * im.height)))
    return im


def _caber(im: Image.Image, larg: int, alt: int) -> Image.Image:
    esc = min(larg / im.width, alt / im.height)
    return im.resize((max(1, int(im.width * esc)), max(1, int(im.height * esc))), Image.LANCZOS)


def _fita(larg=170, alt=54, seed=0) -> Image.Image:
    f = papel(larg, alt, (236, 226, 190), seed, 0.4).convert("RGBA")
    f.putalpha(_mascara(larg, alt, "rasgado", seed).point(lambda v: int(v * 0.82)))
    return f


def polaroid(im: Image.Image, legenda: str, larg_foto: int, alt_max: int, seed: int, moldura: str) -> Image.Image:
    foto = _caber(im, larg_foto, alt_max)
    if moldura == "adesivo":  # recorte com borda branca (bom para logos e produtos)
        return foto.convert("RGBA")
    m, base = (26, 150) if moldura == "polaroid" else (14, 14)
    cw, ch = foto.width + 2 * m, foto.height + m + (base if moldura == "polaroid" and legenda else m)
    card = papel(cw, ch, (248, 245, 236), seed, 0.35).convert("RGBA")
    card.paste(foto, (m, m))
    if moldura == "polaroid" and legenda:
        bl = Bloco(legenda, "mao", 54, 34, cw - 2 * m, 2)
        bl.desenhar(ImageDraw.Draw(card), cw / 2, foto.height + m + (base - bl.altura) / 2 - 6, (40, 46, 120), (40, 46, 120),
                    fundo=(248, 245, 236))
    if moldura == "fita":  # pedaços de fita crepe nos cantos
        tela = Image.new("RGBA", (cw + 80, ch + 80), (0, 0, 0, 0))
        tela.alpha_composite(card, dest=(40, 40))
        for i, (x, y, a) in enumerate(((0, 10, 35), (cw - 90, ch - 10, 35))):
            pedaco = _fita(seed=seed + i).rotate(a, expand=True, resample=Image.BICUBIC)
            tela.alpha_composite(pedaco, dest=(max(0, x), max(0, min(y, tela.height - pedaco.height))))
        return tela
    return card


class Foto(cn.Cena):
    tipo = "foto"
    descricao = ("Print/foto do vídeo original em moldura polaroid, com fita crepe ou recortada como adesivo "
                 "(logos e produtos). Cai na mesa e balança. Legenda escrita à mão (polaroid) ou etiqueta datilografada.")
    campos = {"imagem*": "caminho relativo à pasta do vídeo (ex.: frames/f_0008.jpg)",
              "recorte": "[x0, y0, x1, y1] em frações 0–1 para cortar o print",
              "moldura": "polaroid (padrão) | fita | adesivo",
              "legenda": "texto curto (até ~40 caracteres)",
              "tamanho": "fração da largura útil, 0.5 a 1 (padrão 0.75)"}
    exemplo = {"imagem": "frames/f_0008.jpg", "recorte": [0.1, 0.25, 0.9, 0.65], "moldura": "polaroid",
               "legenda": "areia entre os dedos"}

    def preparar(self):
        moldura = self.dados.get("moldura", "polaroid")
        larg = int(LARG * min(1.0, max(0.5, float(self.dados.get("tamanho", 0.75)))))
        im = carregar(self.dados["imagem"], self.dados.get("recorte"))
        leg = self.dados.get("legenda") or ""
        conteudo = polaroid(im, leg if moldura == "polaroid" else "", larg, 820, 120, moldura)
        self.ad = Adesivo(conteudo, seed=121, borda=14 if moldura == "adesivo" else 6)
        self.etq = None
        if leg and moldura != "polaroid":
            self.etq = Adesivo(impresso(leg, "maquina", 56, 40, LARG, 2, CARTAO, TINTA, LARANJA, pad=(36, 20), seed=122,
                                        avisos=self.avisos, rotulo="foto.legenda"), seed=122)
        r = _rng("foto", self.dados["imagem"])
        self.ang = r.choice((-5, -3, 3, 5))
        self.cy = 760 if not self.etq else 700

    def compor(self, img, t):
        p = _entra(t, 0.0, 0.4)
        if p <= 0:
            return
        queda = 1 - ease_back(p)  # cai de cima, maior e mais torta, e assenta
        jx, jy = tremor("foto", int(t * 6), amp=1.5)
        self.ad.colar(img, W / 2 + jx, self.cy - queda * 120 + jy, self.ang + queda * 10 + 0.6 * math.sin(t * 1.4),
                      1 + 0.18 * queda)
        if self.etq:
            q = _entra(t, 0.45, 0.3)
            if q > 0:
                self.etq.colar(img, W / 2 + 120, self.cy + self.ad.img.height / 2 - 10, -3, ease_back(q))


_ARRANJOS = {  # (cx, cy, ângulo) de cada foto, por quantidade
    2: [(380, 620, -6), (700, 980, 5)],
    3: [(340, 560, -7), (740, 760, 6), (430, 1110, -3)],
    4: [(330, 540, -6), (750, 600, 5), (360, 1040, 4), (740, 1110, -5)],
}


class Fotos(cn.Cena):
    tipo = "fotos"
    descricao = "Mural de 2 a 4 prints/fotos espalhados na mesa, entrando um a um (exemplos, provas, antes/depois)."
    campos = {"imagens*": "lista de 2–4 itens: caminho ou {imagem, recorte, legenda}",
              "titulo": "etiqueta curta no topo"}
    exemplo = {"imagens": [{"imagem": "frames/f_0031.jpg", "recorte": [0, 0.3, 1, 0.7], "legenda": "vinil"},
                           "frames/f_0032.jpg"], "titulo": "a volta do *analógico*"}

    def preparar(self):
        itens = [i if isinstance(i, dict) else {"imagem": i} for i in self.dados["imagens"][:4]]
        if len(itens) < 2:
            self.avisos.append("fotos: use pelo menos 2 imagens (para uma só, use a cena foto)")
        n = max(2, len(itens))
        larg = {2: 560, 3: 470, 4: 420}[n]
        self.fotos = []
        for k, it in enumerate(itens):
            im = carregar(it["imagem"], it.get("recorte"))
            self.fotos.append(Adesivo(polaroid(im, it.get("legenda", ""), larg, 560, 130 + k, "polaroid"),
                                      seed=130 + k, borda=6))
        self.pos = _ARRANJOS[n]
        self.tit = None
        if self.dados.get("titulo"):
            self.tit = Adesivo(impresso(self.dados["titulo"], "titulo", 64, 44, LARG, 2, TEAL, BRANCO, MOSTARDA,
                                        pad=(54, 18), forma="bandeira", seed=139, avisos=self.avisos,
                                        rotulo="fotos.titulo"), seed=139)
        self.passo = min(0.7, self.dur * 0.6 / max(1, len(self.fotos)))

    def compor(self, img, t):
        for k, (ad, (x, y, a)) in enumerate(zip(self.fotos, self.pos)):
            p = _entra(t, k * self.passo, 0.35)
            if p <= 0:
                break
            queda = 1 - ease_back(p)
            ad.colar(img, x, y - queda * 90, a + queda * 12 + 0.5 * math.sin(t * 1.3 + k), 1 + 0.2 * queda)
        if self.tit:
            q = _entra(t, 0.1, 0.3)
            if q > 0:
                self.tit.colar(img, W / 2, 330, -2, ease_back(q))


class Manchete(cn.Cena):
    tipo = "manchete"
    descricao = "Recorte de jornal: nome do veículo, manchete grande e foto em meio-tom de jornal (notícias, fatos, cases)."
    campos = {"titulo*": "a manchete (até ~70 caracteres)", "veiculo": "nome do jornal/site no topo",
              "imagem": "print opcional para a foto da matéria", "recorte": "[x0, y0, x1, y1] em frações"}
    exemplo = {"titulo": "Polaroid espalha outdoors contra a era da IA", "veiculo": "Diário do Marketing",
               "imagem": "frames/f_0050.jpg", "recorte": [0, 0.2, 1, 0.6]}

    def preparar(self):
        cw = LARG - 20
        jornal = (232, 227, 212)
        mast = str(self.dados.get("veiculo") or "The Daily Brand")
        ti = Bloco(self.dados["titulo"], "jornal", 82, 52, cw - 80, 4, self.avisos, "manchete.titulo")
        foto = None
        if self.dados.get("imagem"):
            im = carregar(self.dados["imagem"], self.dados.get("recorte")).convert("L")
            im = _caber(im, cw - 80, 520)
            # Meio-tom de jornal: reduz, pontilha e amplia de volta.
            pont = im.resize((im.width // 3, im.height // 3)).convert("1").resize(im.size, Image.NEAREST)
            foto = Image.blend(im.convert("RGB"), pont.convert("RGB"), 0.55)
            foto = Image.fromarray((np.asarray(foto, np.float32) * np.array(jornal) / 255).astype(np.uint8))
        ch = 70 + 90 + 30 + ti.altura + 40 + (foto.height + 40 if foto else 0) + 60
        img = papel(cw, int(ch), jornal, 141, 0.5).convert("RGBA")
        d = ImageDraw.Draw(img)
        d.text((cw / 2, 95), mast, font=fonte("masthead", 72), fill=TINTA, anchor="mm")
        d.line((40, 150, cw - 40, 150), fill=TINTA, width=3)
        d.line((40, 158, cw - 40, 158), fill=TINTA, width=1)
        y = 190
        ti.desenhar(d, cw / 2, y, TINTA, CARMIM, fundo=jornal)
        y += ti.altura + 40
        if foto:
            img.paste(foto, (int((cw - foto.width) / 2), int(y)))
        img.putalpha(_mascara(cw, int(ch), "rasgado", 141))
        self.ad = Adesivo(img, seed=141, borda=4)

    def compor(self, img, t):
        p = _entra(t, 0.0, 0.35)
        if p <= 0:
            return
        gira = (1 - ease_out(p)) * 180  # chega girando, como jornal jogado na mesa
        self.ad.colar(img, W / 2, 780, -2 + gira * 0.1 + 0.4 * math.sin(t * 1.2), 0.6 + 0.4 * ease_back(p))


CENAS_COLAGEM = {c.tipo: c for c in (Gancho, Numero, Lista, Comparacao, Citacao, Alerta, Palavra, Cta,
                                     Foto, Fotos, Manchete)}


# ---------------- quadro ----------------

def _legenda(d, plano, t):
    for g in plano["legendas"]:
        if g["s"] <= t < g["e"]:
            texto = " ".join(p["w"] for p in g["palavras"])
            tam = 62
            while fonte("maquina", tam).getlength(texto) > W - 200 and tam > 36:
                tam -= 4
            f = fonte("maquina", tam)
            esp, lw = f.getlength(" "), f.getlength(texto)
            x = W / 2 - lw / 2
            caixa = (x - 36, LEGENDA_Y - 24, x + lw + 36, LEGENDA_Y + tam + 30)
            d.rectangle(tuple(v + o for v, o in zip(caixa, (8, 10, 8, 10))), fill=(150, 130, 100))
            d.rectangle(caixa, fill=CARTAO)
            for p in g["palavras"]:
                wl = f.getlength(p["w"])
                falando = p["s"] <= t < p["e"] + 0.05
                if falando:
                    d.rectangle((x - 6, LEGENDA_Y + tam * 0.3, x + wl + 6, LEGENDA_Y + tam + 8), fill=MOSTARDA)
                d.text((x, LEGENDA_Y), p["w"], font=f, fill=TINTA if falando or t >= p["s"] else COR["suave"])
                x += wl + esp
            return


def quadro_colagem(plano: dict, t: float) -> Image.Image:
    t = tq(t)
    img = fundo_colagem(plano.get("visual", {}).get("fundo", "papel")).copy()
    for item in plano["cenas"]:
        if item["ini"] <= t < item["fim"] or (item["ultima"] and t >= item["ini"]):
            item["cena"].compor(img, t - item["ini"])
            break
    d = ImageDraw.Draw(img)
    nome = CFG["marca"].get("nome")
    if nome:
        d.text((W / 2, 170), nome.upper(), font=fonte("carimbo", 40), fill=LARANJA, anchor="mm")
    _legenda(d, plano, t)
    d.rectangle((0, H - 16, W * min(1.0, t / plano["duracao"]), H), fill=LARANJA)
    return granular(img, int(t * FPS_ANIM))
