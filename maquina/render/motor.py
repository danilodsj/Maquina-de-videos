"""Transforma roteiro + tempos das palavras em plano de cenas e renderiza o MP4 (frames por pipe no ffmpeg)."""
import math
import re
import subprocess
from pathlib import Path

from PIL import Image, ImageDraw

from ..config import CFG
from .base import COR, H, W, fade, fonte, fundo_base
from .cenas import CENAS

FPS = CFG["video"]["fps"]
LEGENDA_Y = 1400
_TAG = re.compile(r"\[[^\]]*\]")


# ---------- palavras e tempos ----------

def palavras_fala(fala: str) -> list[str]:
    """Palavras faladas, sem marcações de tom como [animado]."""
    return _TAG.sub(" ", fala.replace("*", "")).split()


def palavras_do_alinhamento(al: dict) -> list[dict]:
    """Agrupa o alinhamento por caractere da ElevenLabs em palavras com início e fim."""
    palavras, atual, ini, fim, tag = [], "", 0.0, 0.0, False

    def fechar():
        nonlocal atual
        if atual:
            palavras.append({"w": atual, "s": ini, "e": fim})
        atual = ""

    for ch, a, b in zip(al["characters"], al["character_start_times_seconds"], al["character_end_times_seconds"]):
        if ch == "[":
            fechar()
            tag = True
        elif tag:
            tag = ch != "]"
        elif ch.isspace():
            fechar()
        else:
            if not atual:
                ini = a
            atual += ch
            fim = b
    fechar()
    return palavras


def palavras_estimadas(cenas: list[dict]) -> list[dict]:
    """Tempos aproximados (para prévia sem narração)."""
    wps = CFG["roteiro"]["palavras_por_segundo"]
    t, saida = 0.2, []
    for c in cenas:
        for w in palavras_fala(c["fala"]):
            dur = (0.55 + 0.06 * len(w)) / wps
            saida.append({"w": w, "s": t, "e": t + dur})
            t += dur + (0.22 if w[-1] in ".!?" else 0.08 if w[-1] in ",;:" else 0)
        t += 0.15
    return saida


def montar_plano(roteiro: dict, palavras: list[dict], duracao: float | None = None) -> dict:
    """Define início e fim de cada cena contando as palavras de cada fala."""
    cenas = roteiro["cenas"]
    if not palavras:
        raise ValueError("A narração não tem palavras faladas (falas vazias ou só com [marcações]).")
    if duracao is None:
        duracao = palavras[-1]["e"] + CFG["video"]["cauda_s"]
    inicios, k = [], 0
    for c in cenas:
        idx = min(k, len(palavras) - 1)
        inicios.append(0.0 if not inicios else max(0.0, palavras[idx]["s"] - 0.12))
        k += len(palavras_fala(c["fala"]))
    avisos: list[str] = []
    plano = []
    for i, c in enumerate(cenas):
        fim = inicios[i + 1] if i + 1 < len(cenas) else duracao
        cls = _registro()[c["tipo"]]
        antes = len(avisos)
        obj = cls(c.get("dados", {}), fim - inicios[i], avisos)
        for j in range(antes, len(avisos)):
            avisos[j] = f"cena {i + 1} ({c['tipo']}): {avisos[j]}"
        plano.append({"ini": inicios[i], "fim": fim, "cena": obj, "ultima": i == len(cenas) - 1})
    return {"duracao": duracao, "cenas": plano, "legendas": grupos_legenda(palavras), "avisos": avisos,
            "visual": roteiro.get("visual") or {}}


def _registro() -> dict:
    """Cenas do estilo atual (mesmos tipos e campos; muda só o desenho)."""
    if CFG["video"].get("estilo") == "colagem":
        from .colagem import CENAS_COLAGEM
        return CENAS_COLAGEM
    return CENAS


def grupos_legenda(palavras: list[dict], maximo: int = 3) -> list[dict]:
    grupos, atual = [], []
    for p in palavras:
        atual.append(p)
        if len(atual) >= maximo or p["w"][-1] in ".,!?;:":
            grupos.append(atual)
            atual = []
    if atual:
        grupos.append(atual)
    saida = []
    for i, g in enumerate(grupos):
        fim = grupos[i + 1][0]["s"] if i + 1 < len(grupos) else g[-1]["e"] + 0.5
        saida.append({"s": g[0]["s"], "e": fim, "palavras": g})
    return saida


# ---------- desenho de um quadro ----------

def _legenda(d, plano, t):
    for g in plano["legendas"]:
        if g["s"] <= t < g["e"]:
            tam = 74
            texto = " ".join(p["w"] for p in g["palavras"])
            while fonte("black", tam).getlength(texto) > W - 140 and tam > 40:
                tam -= 4
            f = fonte("black", tam)
            esp = f.getlength(" ")
            x = W / 2 - f.getlength(texto) / 2
            d.rounded_rectangle((x - 34, LEGENDA_Y - 26, x + f.getlength(texto) + 34, LEGENDA_Y + tam + 30),
                                radius=30, fill=COR["card"])
            for p in g["palavras"]:
                lw = f.getlength(p["w"])
                falando = p["s"] <= t < p["e"] + 0.05
                if falando:
                    d.rounded_rectangle((x - 14, LEGENDA_Y - 12, x + lw + 14, LEGENDA_Y + tam + 14), radius=18, fill=COR["violeta"])
                d.text((x, LEGENDA_Y), p["w"], font=f, fill=COR["texto"] if falando or t >= p["s"] else COR["suave"])
                x += lw + esp
            return


def quadro(plano: dict, t: float) -> Image.Image:
    if CFG["video"].get("estilo") == "colagem":
        from .colagem import quadro_colagem
        return quadro_colagem(plano, t)
    if CFG["video"].get("estilo") == "cidade_noturna":
        from .cenario import quadro_cenario
        img = quadro_cenario(t)
    else:
        img = fundo_base().copy()
    d = ImageDraw.Draw(img)
    for item in plano["cenas"]:
        if item["ini"] <= t < item["fim"] or (item["ultima"] and t >= item["ini"]):
            local = t - item["ini"]
            dur = item["fim"] - item["ini"]
            alfa = 1.0 if item["ultima"] else max(0.0, min(1.0, (dur - local) / 0.18))
            item["cena"].desenhar(d, local, alfa)
            break
    nome = CFG["marca"].get("nome")
    if nome:
        d.text((W / 2, 170), nome, font=fonte("semibold", 40), fill=fade(COR["suave"], 0.9), anchor="mm")
    _legenda(d, plano, t)
    d.rectangle((0, H - 14, W * min(1.0, t / plano["duracao"]), H), fill=COR["menta"])
    return img


# ---------- saída ----------

def renderizar(plano: dict, saida: Path, audio: Path | None = None) -> Path:
    v = CFG["video"]
    n = math.ceil(plano["duracao"] * FPS)
    cmd = ["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24",
           "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-"]
    if audio:
        cmd += ["-i", str(audio), "-map", "0:v", "-map", "1:a", "-c:a", "aac", "-b:a", "192k", "-af", "apad", "-shortest"]
    cmd += ["-c:v", "libx264", "-preset", v["preset"], "-crf", str(v["crf"]), "-pix_fmt", "yuv420p",
            "-movflags", "+faststart", str(saida)]
    tmp = saida.with_name(saida.stem + ".parcial" + saida.suffix)
    cmd[-1] = str(tmp)
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=subprocess.PIPE)
    # No stop-motion a imagem só muda a cada 1/12 s: repete o quadro anterior em vez de redesenhar.
    passo_anim = CFG["video"].get("fps_animacao", 12) if v.get("estilo") == "colagem" else None
    try:
        chave_ant, dados = None, b""
        for i in range(n):
            chave = math.floor(i / FPS * passo_anim) if passo_anim else i
            if chave != chave_ant:
                dados, chave_ant = quadro(plano, i / FPS).tobytes(), chave
            proc.stdin.write(dados)
        proc.stdin.close()
    except BrokenPipeError:
        pass
    erro = proc.stderr.read().decode(errors="ignore")
    if proc.wait() != 0:
        raise RuntimeError(f"ffmpeg falhou: {erro.strip()[-500:]}")
    tmp.replace(saida)
    return saida


def folha_contato(plano: dict, saida: Path, colunas: int = 4) -> Path:
    """Um quadro do meio e um do fim de cada cena, em miniatura, para revisão visual."""
    tempos = []
    for item in plano["cenas"]:
        dur = item["fim"] - item["ini"]
        tempos += [item["ini"] + min(1.2, dur * 0.5), item["ini"] + max(0.0, dur - 0.25)]
    esc = 0.25
    w, h = int(W * esc), int(H * esc)
    linhas = math.ceil(len(tempos) / colunas)
    folha = Image.new("RGB", (w * colunas, h * linhas), COR["fundo"])
    for i, t in enumerate(tempos):
        folha.paste(quadro(plano, t).resize((w, h)), ((i % colunas) * w, (i // colunas) * h))
    folha.save(saida)
    return saida
