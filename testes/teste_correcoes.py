"""Testes das correções da revisão (sem rede): tokenização com marcações, legenda VTT e lista vazia.

Uso: python testes/teste_correcoes.py
"""
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.stdout.reconfigure(encoding="utf-8")

from maquina.legendas import vtt_para_texto  # noqa: E402
from maquina.narracao import sem_tags  # noqa: E402
from maquina.render.motor import montar_plano, palavras_do_alinhamento, palavras_fala  # noqa: E402

# 1. Marcação colada na palavra: narração e motor contam igual.
for fala in ["isso[sério]cuidado agora", "[animado]Você ainda", "fim. [sussurrando] segredo"]:
    assert sem_tags(fala).split() == palavras_fala(fala), fala
    chars = list(fala)
    al = palavras_do_alinhamento({"characters": chars, "character_start_times_seconds": [0.0] * len(chars),
                                  "character_end_times_seconds": [0.0] * len(chars)})
    assert [p["w"] for p in al] == palavras_fala(fala), (fala, al)
print("ok: tokenização igual em narração, alinhamento e motor")

# 2. VTT rolante: tira a repetição imediata, mantém fala repetida de verdade.
vtt = """WEBVTT

00:00:00.000 --> 00:00:01.000
Número um

00:00:01.000 --> 00:00:02.000
Número um
é o melhor

00:00:02.000 --> 00:00:03.000
é o melhor
Sim

00:00:03.000 --> 00:00:04.000
falei antes

00:00:04.000 --> 00:00:05.000
de novo

00:00:05.000 --> 00:00:06.000
outra coisa

00:00:06.000 --> 00:00:07.000
Sim
"""
with tempfile.TemporaryDirectory() as d:
    arq = Path(d) / "t.vtt"
    arq.write_text(vtt, encoding="utf-8")
    texto = vtt_para_texto(arq)
assert texto == "Número um é o melhor Sim falei antes de novo outra coisa Sim", texto
print("ok: VTT mantém o 'Sim' repetido e remove a rolagem")

# 3. Lista de palavras vazia vira erro claro, não IndexError.
try:
    montar_plano({"cenas": [{"tipo": "gancho", "fala": "[sério]", "dados": {"texto": "x"}}] * 2}, [])
except ValueError as e:
    print("ok: lista vazia →", e)
else:
    raise AssertionError("deveria falhar")
