"""Validação do roteiro.json antes de gastar créditos com narração."""
import copy
from pathlib import Path

from .config import CFG
from .render.motor import _registro, palavras_fala

FUNDOS = ("papel", "kraft", "quadro", "papelao", "grafite")


def _imagens(dados: dict) -> list[dict]:
    """Os itens de imagem de uma cena: {"imagem": ...} em dados, ou na lista de dados.imagens."""
    itens = [dados] if dados.get("imagem") else []
    for it in dados.get("imagens") or []:
        itens.append(it if isinstance(it, dict) else {"imagem": it})
    return itens


def resolver_imagens(roteiro: dict, pasta: Path) -> dict:
    """Cópia do roteiro com os caminhos de imagem relativos à pasta do vídeo tornados absolutos."""
    r = copy.deepcopy(roteiro)
    for c in r.get("cenas", []):
        d = c.get("dados") or {}
        if d.get("imagem"):
            d["imagem"] = str((pasta / d["imagem"]).resolve())
        if d.get("imagens"):
            d["imagens"] = [
                {**it, "imagem": str((pasta / it["imagem"]).resolve())} if isinstance(it, dict)
                else str((pasta / it).resolve())
                for it in d["imagens"]
            ]
    return r


def validar(roteiro: dict, pasta: Path | None = None) -> tuple[list[str], list[str]]:
    """Devolve (erros, avisos). Erros impedem a produção; avisos só alertam."""
    cenas_disp = _registro()
    erros, avisos = [], []
    for campo in ("titulo", "descricao", "cenas"):
        if not roteiro.get(campo):
            erros.append(f"falta o campo '{campo}'")
    if len(roteiro.get("titulo", "")) > 100:
        erros.append("título com mais de 100 caracteres (limite do YouTube)")
    fiel = roteiro.get("modo") == "fiel"
    if roteiro.get("creditos") and roteiro["creditos"] not in roteiro.get("descricao", ""):
        avisos.append("a descrição não traz os créditos do vídeo original (copie 'creditos' para o fim da descrição)")
    fundo = (roteiro.get("visual") or {}).get("fundo")
    if fundo and fundo not in FUNDOS:
        erros.append(f"visual.fundo '{fundo}' não existe (use: {', '.join(FUNDOS)})")
    cenas = roteiro.get("cenas") or []
    if not 3 <= len(cenas) <= 10:
        avisos.append(f"{len(cenas)} cenas (o ideal é de 4 a 10)")
    total = 0
    for i, c in enumerate(cenas, 1):
        tipo = c.get("tipo")
        if tipo not in cenas_disp:
            erros.append(f"cena {i}: tipo '{tipo}' não existe neste estilo (use: {', '.join(cenas_disp)})")
            continue
        if not str(c.get("fala", "")).strip():
            erros.append(f"cena {i}: fala vazia")
        dados = c.get("dados") or {}
        for campo in cenas_disp[tipo].obrigatorios():
            if dados.get(campo) in (None, "", []):
                erros.append(f"cena {i} ({tipo}): falta dados.{campo}")
        if tipo == "comparacao":
            for lado in ("antes", "depois"):
                if not isinstance(dados.get(lado), dict) or not dados[lado].get("itens"):
                    erros.append(f"cena {i} (comparacao): {lado} precisa de titulo e itens")
        if tipo == "lista" and not isinstance(dados.get("itens"), list):
            erros.append(f"cena {i} (lista): itens precisa ser uma lista")
        if tipo == "numero":
            try:
                float(dados.get("valor"))
            except (TypeError, ValueError):
                erros.append(f"cena {i} (numero): valor precisa ser número")
        for it in _imagens(dados):
            caminho = Path(it["imagem"]) if Path(it["imagem"]).is_absolute() or pasta is None else pasta / it["imagem"]
            if pasta is not None and not caminho.exists():
                erros.append(f"cena {i} ({tipo}): imagem não encontrada: {it['imagem']} (rode python mv.py frames)")
            rec = it.get("recorte")
            if rec is not None and not (isinstance(rec, list) and len(rec) == 4
                                        and 0 <= rec[0] < rec[2] <= 1 and 0 <= rec[1] < rec[3] <= 1):
                erros.append(f"cena {i} ({tipo}): recorte inválido {rec} (use [x0, y0, x1, y1] entre 0 e 1)")
        total += len(palavras_fala(c.get("fala", "")))
    if cenas:
        if not fiel and cenas[0].get("tipo") not in ("gancho", "palavra", "numero", "foto", "manchete"):
            avisos.append("a 1ª cena não é um gancho (gancho, palavra, numero, foto ou manchete)")
        if cenas[-1].get("tipo") != "cta":
            avisos.append("a última cena não é cta")
        seguidas = [i for i in range(1, len(cenas)) if cenas[i].get("tipo") == cenas[i - 1].get("tipo")]
        if seguidas:
            avisos.append(f"tipo de cena repetido em seguida na cena {seguidas[0] + 1}")
    r = CFG["roteiro"]
    estimado = total / r["palavras_por_segundo"]
    if not fiel and (estimado < r["duracao_min_s"] or estimado > r["duracao_max_s"]):
        avisos.append(f"duração estimada {estimado:.0f}s (alvo {r['duracao_min_s']}–{r['duracao_max_s']}s, {total} palavras)")
    return erros, avisos
