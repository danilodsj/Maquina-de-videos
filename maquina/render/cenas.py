"""Biblioteca de cenas. Cada cena é um modelo fixo; o roteiro só escolhe o tipo e preenche os dados.

Para criar um tipo novo: subclasse de Cena, defina tipo/descricao/campos/exemplo e desenhar(),
e registre com @registrar. `python mv.py cenas` passa a listar o tipo novo automaticamente.
"""
import math

from .base import (COR, W, Bloco, clamp, ease_back, ease_out, entrada, fade, fonte, mix, ondas)

CENAS: dict[str, type] = {}
TOPO, BASE = 300, 1330          # área útil; abaixo ficam a legenda e a interface do Shorts
LARG = 920                      # largura útil do texto
X0 = (W - LARG) // 2


def registrar(cls):
    CENAS[cls.tipo] = cls
    return cls


class Cena:
    tipo = ""
    descricao = ""
    campos: dict[str, str] = {}      # nome -> descrição (os marcados com * são obrigatórios)
    exemplo: dict = {}

    def __init__(self, dados: dict, dur: float, avisos: list):
        self.dados, self.dur, self.avisos = dados, dur, avisos
        self.preparar()

    @classmethod
    def obrigatorios(cls) -> list[str]:
        return [k.rstrip("*") for k in cls.campos if k.endswith("*")]

    def preparar(self):
        pass

    def desenhar(self, d, t: float, alfa: float):
        raise NotImplementedError

    def _chip(self, d, texto: str, cx: float, cy: float, cor: tuple, p: float, alfa: float):
        f = fonte("bold", 38)
        larg = f.getlength(texto.upper()) + 64
        escala = ease_back(p)
        w = larg * max(0.0, escala)
        if w < 8:
            return
        d.rounded_rectangle((cx - w / 2, cy - 34, cx + w / 2, cy + 34), radius=34, fill=fade(cor, alfa * clamp(p * 2)))
        if p > 0.55:
            d.text((cx, cy), texto.upper(), font=f, fill=fade(COR["fundo"], alfa, cor), anchor="mm")


@registrar
class Gancho(Cena):
    tipo = "gancho"
    descricao = "Abertura: frase de impacto grande, revelada palavra a palavra, com selo opcional e ondas sonoras."
    campos = {"texto*": "frase curta (até ~60 caracteres); *palavra* em destaque",
              "selo": "rótulo pequeno acima (ex.: NOVO, ALERTA, GRÁTIS)"}
    exemplo = {"texto": "Essa IA *edita seus vídeos* sozinha", "selo": "novo"}

    def preparar(self):
        self.b = Bloco(self.dados["texto"], "black", 124, 70, LARG, 5, self.avisos, "gancho.texto")

    def desenhar(self, d, t, alfa):
        y = 800 - self.b.altura / 2
        if self.dados.get("selo"):
            self._chip(d, self.dados["selo"], W / 2, y - 110, COR["violeta"], (t - 0.05) / 0.5, alfa)
        self.b.desenhar(d, W / 2, y, COR["texto"], COR["menta"], alfa, revelar=clamp(t / 0.9))
        ondas(d, W / 2, y + self.b.altura + 140, t, alfa=alfa * entrada(t, 0.3))


@registrar
class Numero(Cena):
    tipo = "numero"
    descricao = "Número grande com contagem animada dentro de um anel, e legenda curta embaixo."
    campos = {"valor*": "número (ex.: 87, 1500, 3.5)", "prefixo": "ex.: R$", "sufixo": "ex.: %, x, mil",
              "rotulo*": "o que o número significa (até ~70 caracteres)"}
    exemplo = {"valor": 87, "sufixo": "%", "rotulo": "das empresas já usam *IA* no marketing"}

    def preparar(self):
        self.r = Bloco(self.dados["rotulo"], "bold", 72, 48, LARG, 3, self.avisos, "numero.rotulo")
        v = float(self.dados["valor"])
        self.v, self.decimais = v, 0 if v == int(v) else 1

    def _fmt(self, x):
        s = f"{x:,.{self.decimais}f}".replace(",", "X").replace(".", ",").replace("X", ".")
        return f"{self.dados.get('prefixo', '')}{s}{self.dados.get('sufixo', '')}"

    def desenhar(self, d, t, alfa):
        cy = 640
        p = ease_out(t / 1.3)
        raio = 300
        d.arc((W / 2 - raio, cy - raio, W / 2 + raio, cy + raio), 0, 360, fill=fade(COR["card"], alfa), width=22)
        d.arc((W / 2 - raio, cy - raio, W / 2 + raio, cy + raio), -90, -90 + 360 * p,
              fill=fade(COR["menta"], alfa), width=22)
        txt = self._fmt(self.v * p)
        tam = 230
        while fonte("black", tam).getlength(self._fmt(self.v)) > 2 * raio - 90 and tam > 90:
            tam -= 8
        d.text((W / 2, cy), txt, font=fonte("black", tam), fill=fade(COR["texto"], alfa * entrada(t)), anchor="mm")
        self.r.desenhar(d, W / 2, cy + raio + 80, COR["suave"], COR["menta"], alfa * entrada(t, 0.5))


@registrar
class Lista(Cena):
    tipo = "lista"
    descricao = "Título + até 5 itens em cards que entram um a um (numerados ou com check)."
    campos = {"titulo": "título acima da lista", "itens*": "lista de 2 a 5 textos curtos (até ~40 caracteres cada)",
              "numerada": "true para 1, 2, 3...; padrão: check"}
    exemplo = {"titulo": "3 IAs que *economizam horas*", "itens": ["Claude: roteiros", "ElevenLabs: narração", "CapCut: cortes"], "numerada": True}

    def preparar(self):
        itens = self.dados["itens"][:5]
        if len(self.dados["itens"]) > 5:
            self.avisos.append("lista: mais de 5 itens (só os 5 primeiros aparecem)")
        self.t = Bloco(self.dados["titulo"], "black", 84, 56, LARG, 2, self.avisos, "lista.titulo") if self.dados.get("titulo") else None
        self.itens = [Bloco(i, "bold", 64, 42, LARG - 190, 2, self.avisos, "lista.item") for i in itens]
        self.alt_card = max(150, max(b.altura for b in self.itens) + 64)
        self.passo = min(0.9, self.dur * 0.7 / max(1, len(self.itens)))
        total = len(self.itens) * (self.alt_card + 22) + (self.t.altura + 70 if self.t else 0)
        self.y0 = max(TOPO, 800 - total / 2)

    def desenhar(self, d, t, alfa):
        y = self.y0
        if self.t:
            self.t.desenhar(d, W / 2, y, COR["texto"], COR["menta"], alfa * entrada(t))
            y += self.t.altura + 70
        for i, b in enumerate(self.itens):
            p = (t - 0.25 - i * self.passo) / 0.5
            if p <= 0:
                break
            a = alfa * clamp(p * 1.6)
            dx = (1 - ease_back(p)) * 160
            top = y + i * (self.alt_card + 22)
            d.rounded_rectangle((X0 + dx, top, X0 + LARG + dx, top + self.alt_card), radius=36, fill=fade(COR["card"], a))
            cx, cy = X0 + 85 + dx, top + self.alt_card / 2
            d.ellipse((cx - 44, cy - 44, cx + 44, cy + 44), fill=fade(COR["menta"], a, COR["card"]))
            marca = str(i + 1) if self.dados.get("numerada") else "✓"
            f = fonte("black", 48) if marca != "✓" else fonte("bold", 50)
            d.text((cx, cy + 2), marca, font=f, fill=fade(COR["fundo"], a, COR["menta"]), anchor="mm")
            b.desenhar(d, X0 + 160 + dx, cy - b.altura / 2 + 4, COR["texto"], COR["menta"], a,
                       alinhar="esquerda", fundo=COR["card"])


@registrar
class Comparacao(Cena):
    tipo = "comparacao"
    descricao = "Dois cards empilhados (antes x depois, errado x certo), o segundo entra depois do primeiro."
    campos = {"antes*": "{titulo, itens[1-3]} do card vermelho", "depois*": "{titulo, itens[1-3]} do card verde"}
    exemplo = {"antes": {"titulo": "Sem IA", "itens": ["4h por vídeo", "1 post por dia"]},
               "depois": {"titulo": "Com IA", "itens": ["20 min por vídeo", "5 posts por dia"]}}

    def preparar(self):
        self.lados = []
        for chave, cor in (("antes", COR["vermelho"]), ("depois", COR["menta"])):
            lado = self.dados[chave]
            itens = [Bloco("• " + i, "bold", 62, 42, LARG - 110, 2, self.avisos, f"comparacao.{chave}")
                     for i in lado.get("itens", [])[:3]]
            alt = 110 + sum(b.altura + 22 for b in itens) + 30
            self.lados.append((lado.get("titulo", ""), itens, cor, alt))
        self.gap = 110
        total = sum(l[3] for l in self.lados) + self.gap
        self.topo = max(TOPO, 800 - total / 2)
        self.t2 = max(0.6, self.dur * 0.4)

    def desenhar(self, d, t, alfa):
        y0_base = self.topo
        for k, (titulo, itens, cor, alt) in enumerate(self.lados):
            atraso = 0.1 if k == 0 else self.t2
            p = (t - atraso) / 0.5
            if p > 0:
                a = alfa * clamp(p * 1.6)
                y0 = y0_base + (1 - ease_back(p)) * 120
                d.rounded_rectangle((X0, y0, X0 + LARG, y0 + alt), radius=40, fill=fade(COR["card"], a),
                                    outline=fade(cor, a), width=5)
                self._chip(d, titulo, W / 2, y0, cor, p, alfa)
                y = y0 + 80
                for b in itens:
                    b.desenhar(d, X0 + 60, y, COR["texto"], cor, a, alinhar="esquerda", fundo=COR["card"])
                    y += b.altura + 22
            y0_base += alt + self.gap
        if t > self.t2:
            p = ease_back((t - self.t2) / 0.4)
            cy, r = self.topo + self.lados[0][3] + self.gap / 2 - 17, 46 * max(0.0, p)
            cx = X0 + LARG - 90
            d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=fade(COR["violeta"], alfa))
            if p > 0.6:
                d.text((cx, cy), "VS", font=fonte("black", 36), fill=fade(COR["texto"], alfa, COR["violeta"]), anchor="mm")


@registrar
class Citacao(Cena):
    tipo = "citacao"
    descricao = "Frase em destaque com aspas grandes e autor (dado, frase de especialista, insight)."
    campos = {"texto*": "a frase (até ~120 caracteres)", "autor": "quem disse / fonte"}
    exemplo = {"texto": "Quem não usar *IA* vai competir com quem usa", "autor": "Relatório McKinsey 2026"}

    def preparar(self):
        self.b = Bloco(self.dados["texto"], "bold", 84, 52, LARG, 6, self.avisos, "citacao.texto")

    def desenhar(self, d, t, alfa):
        y = 800 - self.b.altura / 2
        d.text((X0 - 10, y - 40), "“", font=fonte("black", 300), fill=fade(COR["violeta"], alfa * entrada(t)), anchor="ls")
        self.b.desenhar(d, W / 2, y, COR["texto"], COR["menta"], alfa, revelar=clamp((t - 0.1) / 1.2))
        if self.dados.get("autor"):
            d.text((W / 2, y + self.b.altura + 70), "— " + self.dados["autor"], font=fonte("semibold", 44),
                   fill=fade(COR["suave"], alfa * entrada(t, 0.8)), anchor="mm")


@registrar
class Alerta(Cena):
    tipo = "alerta"
    descricao = "Card âmbar de atenção com ícone: ressalvas, riscos, erros comuns."
    campos = {"titulo*": "ex.: Cuidado, Atenção, Erro comum", "texto*": "explicação curta (até ~100 caracteres)"}
    exemplo = {"titulo": "Cuidado", "texto": "A versão grátis tem *limite* de 10 vídeos por mês"}

    def preparar(self):
        self.ti = Bloco(self.dados["titulo"], "black", 80, 56, LARG - 120, 1, self.avisos, "alerta.titulo")
        self.tx = Bloco(self.dados["texto"], "semibold", 66, 44, LARG - 120, 5, self.avisos, "alerta.texto")

    def desenhar(self, d, t, alfa):
        alt = self.ti.altura + self.tx.altura + 330
        y0 = 800 - alt / 2
        p = ease_back(t / 0.5)
        a = alfa * clamp(t / 0.25)
        borda = 6 + 3 * math.sin(t * 6)
        dx = (1 - p) * 40
        d.rounded_rectangle((X0 - dx, y0 - dx, X0 + LARG + dx, y0 + alt + dx), radius=44,
                            fill=fade(COR["card"], a), outline=fade(COR["ambar"], a), width=int(borda))
        cx, cy = W / 2, y0 + 110
        d.polygon([(cx, cy - 62), (cx + 70, cy + 52), (cx - 70, cy + 52)], fill=fade(COR["ambar"], a, COR["card"]))
        d.text((cx, cy + 14), "!", font=fonte("black", 76), fill=fade(COR["card"], a, COR["ambar"]), anchor="mm")
        self.ti.desenhar(d, W / 2, y0 + 200, COR["ambar"], COR["ambar"], a, fundo=COR["card"])
        self.tx.desenhar(d, W / 2, y0 + 220 + self.ti.altura + 10, COR["texto"], COR["ambar"],
                         alfa * entrada(t, 0.3), fundo=COR["card"])


@registrar
class Palavra(Cena):
    tipo = "palavra"
    descricao = "Uma palavra ou termo gigante que cresce com efeito elástico, com subtítulo opcional."
    campos = {"palavra*": "1 a 2 palavras (ex.: AUTOMAÇÃO)", "texto": "subtítulo curto"}
    exemplo = {"palavra": "AUTOMAÇÃO", "texto": "é o que separa quem escala de quem *cansa*"}

    def preparar(self):
        self.pal = str(self.dados["palavra"]).upper()
        tam = 260
        while fonte("black", tam).getlength(self.pal) > LARG + 40 and tam > 80:
            tam -= 8
        if fonte("black", tam).getlength(self.pal) > LARG + 40:
            self.avisos.append(f"palavra não coube: {self.pal}")
        self.tam = tam
        self.sub = Bloco(self.dados["texto"], "semibold", 62, 44, LARG, 3, self.avisos, "palavra.texto") if self.dados.get("texto") else None

    def desenhar(self, d, t, alfa):
        p = ease_back(t / 0.55)
        tam = max(20, int(self.tam * (0.55 + 0.45 * p) / 4) * 4)
        cor = mix(COR["violeta"], COR["menta"], 0.5 + 0.5 * math.sin(t * 2))
        d.text((W / 2, 760), self.pal, font=fonte("black", tam), fill=fade(cor, alfa * clamp(t / 0.2)), anchor="mm")
        if self.sub:
            self.sub.desenhar(d, W / 2, 760 + self.tam * 0.75, COR["texto"], COR["menta"], alfa * entrada(t, 0.45))


@registrar
class Cta(Cena):
    tipo = "cta"
    descricao = "Fechamento: chamada para ação com botão pulsante. Use sempre como última cena."
    campos = {"texto*": "frase da chamada (até ~60 caracteres)", "botao": "texto do botão (ex.: Siga @perfil)"}
    exemplo = {"texto": "Quer mais *atalhos de IA*?", "botao": "Siga para mais"}

    def preparar(self):
        self.b = Bloco(self.dados["texto"], "black", 104, 64, LARG, 4, self.avisos, "cta.texto")
        self.bt = str(self.dados.get("botao") or "Siga para mais")

    def desenhar(self, d, t, alfa):
        y = 680 - self.b.altura / 2
        self.b.desenhar(d, W / 2, y, COR["texto"], COR["menta"], alfa * entrada(t))
        p = ease_back((t - 0.35) / 0.5)
        if p > 0:
            pulso = 1 + 0.035 * math.sin(t * 7)
            f = fonte("black", 58)
            w = (f.getlength(self.bt) + 140) * p * pulso
            h = 150 * min(1.0, p) * pulso
            cy = y + self.b.altura + 220
            d.rounded_rectangle((W / 2 - w / 2, cy - h / 2, W / 2 + w / 2, cy + h / 2), radius=int(h / 2),
                                fill=fade(COR["menta"], alfa))
            if p > 0.6:
                d.text((W / 2, cy), self.bt, font=f, fill=fade(COR["fundo"], alfa, COR["menta"]), anchor="mm")
        ondas(d, W / 2, 1230, t, largura=420, n=20, alt=70, alfa=alfa * entrada(t, 0.5))
