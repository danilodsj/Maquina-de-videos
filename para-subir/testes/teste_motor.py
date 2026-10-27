"""Teste rápido sem credenciais: alinhamento simulado → plano de cenas, e cálculo de horário.

Uso: python testes/teste_motor.py
"""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.stdout.reconfigure(encoding="utf-8")

from maquina.config import RAIZ, ler_json  # noqa: E402
from maquina.narracao import texto_narracao  # noqa: E402
from maquina.publicar import proximo_horario  # noqa: E402
from maquina.render.motor import montar_plano, palavras_do_alinhamento, palavras_estimadas  # noqa: E402

r = ler_json(RAIZ / "modelos" / "roteiro_exemplo.json")
est = palavras_estimadas(r["cenas"])

# Alinhamento falso no formato da ElevenLabs: cada caractere recebe o tempo da sua palavra.
chars, ini, fim, i = [], [], [], 0
for tok in re.split(r"(\s+|\[[^\]]*\])", texto_narracao(r)):
    if not tok:
        continue
    falado = not tok.isspace() and not tok.startswith("[")
    for ch in tok:
        chars.append(ch)
        ini.append(est[i]["s"] if falado else 0.0)
        fim.append(est[i]["e"] if falado else 0.0)
    i += falado

palavras = palavras_do_alinhamento({"characters": chars, "character_start_times_seconds": ini,
                                    "character_end_times_seconds": fim})
assert [p["w"] for p in palavras] == [p["w"] for p in est], "palavras do alinhamento diferentes das estimadas"
plano = montar_plano(r, palavras)
assert len(plano["cenas"]) == len(r["cenas"])
assert all(a["ini"] < b["ini"] for a, b in zip(plano["cenas"], plano["cenas"][1:])), "cenas fora de ordem"
print(f"ok: {len(palavras)} palavras, {len(plano['cenas'])} cenas, {plano['duracao']:.1f}s, avisos={plano['avisos']}")
print("cenas:", ", ".join(f"{c['cena'].tipo}@{c['ini']:.1f}s" for c in plano["cenas"]))
print("próximo horário livre:", proximo_horario(set()).strftime("%d/%m %H:%M"))
