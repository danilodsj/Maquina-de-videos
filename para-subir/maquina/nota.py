"""Nota de 0 a 100 de um vídeo: velocidade de views, fator outlier e engajamento."""
import math
from datetime import datetime, timezone

from .config import CFG


def _escala(x: float, alvo: float) -> float:
    if x <= 0:
        return 0.0
    return min(1.0, math.log1p(x) / math.log1p(alvo))


def idade_dias(publicado_em: str) -> float:
    dt = datetime.fromisoformat(publicado_em.replace("Z", "+00:00"))
    return max((datetime.now(timezone.utc) - dt).total_seconds() / 86400, 0.25)


def calcular(v: dict) -> tuple[float, dict]:
    c = CFG["nota"]
    views = v.get("views") or 0
    idade = idade_dias(v["publicado_em"])
    vpd = views / idade
    inscritos = v.get("inscritos_canal")
    outlier = views / inscritos if inscritos else None
    eng = ((v.get("likes") or 0) + 2 * (v.get("comentarios") or 0)) / views if views else 0.0

    s_vel = _escala(vpd, c["alvo_views_por_dia"])
    # Canal sem número de inscritos público fica neutro.
    s_out = _escala(outlier, c["alvo_outlier"]) if outlier is not None else 0.5
    s_eng = min(1.0, eng / c["alvo_engajamento"])
    p = c["pesos"]
    nota = 100 * (p["velocidade"] * s_vel + p["outlier"] * s_out + p["engajamento"] * s_eng)
    detalhes = {
        "idade_dias": round(idade, 1),
        "views_por_dia": round(vpd),
        "outlier": round(outlier, 2) if outlier is not None else None,
        "engajamento": round(eng, 4),
    }
    return round(nota, 1), detalhes
