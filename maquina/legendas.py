"""Transcrição dos vídeos de referência: legenda do YouTube, com ElevenLabs como plano B."""
import re
import time
from collections import deque
from pathlib import Path

import requests

from .config import env
from .garimpo import ErroBloqueio


def vtt_para_texto(caminho: Path) -> str:
    """Converte VTT em texto corrido. A legenda automática é "rolante": cada bloco repete a linha
    anterior, então só se descarta o que acabou de aparecer (falas repetidas de verdade ficam)."""
    linhas, recentes = [], deque(maxlen=3)
    for bloco in re.split(r"\n\n+", caminho.read_text(encoding="utf-8")):
        if "-->" not in bloco:
            continue
        for linha in bloco.split("\n")[1:]:
            limpa = re.sub(r"<[^>]+>", "", linha).replace("&gt;", ">").replace("&amp;", "&").strip()
            if limpa and limpa not in recentes:
                linhas.append(limpa)
                recentes.append(limpa)
    return " ".join(linhas)


def baixar_legenda(url: str, pasta: Path, idioma: str | None) -> Path | None:
    """Devolve o .vtt ou None se o vídeo não tem legenda. Bloqueio do YouTube vira ErroBloqueio,
    para o vídeo não ser marcado como "sem legenda" por engano."""
    import yt_dlp
    idiomas = [f"{idioma}-orig", idioma] if idioma else ["pt-orig", "pt", "pt-BR", "en-orig", "en"]
    limitado = False
    for lang in idiomas:
        opts = {
            "quiet": True, "no_warnings": True, "skip_download": True,
            "writesubtitles": True, "writeautomaticsub": True,
            "subtitleslangs": [lang], "subtitlesformat": "vtt",
            "outtmpl": str(pasta / "legenda.%(ext)s"),
        }
        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                ydl.download([url])
        except yt_dlp.utils.DownloadError as e:
            msg = str(e)
            if "not a bot" in msg:
                raise ErroBloqueio(msg) from None
            limitado = limitado or "429" in msg
            if not limitado:
                raise  # vídeo removido, privado etc.: vira status "erro" com a mensagem
        achados = sorted(pasta.glob("legenda*.vtt"))
        if achados:
            return achados[0]
        time.sleep(1.5)  # evita o HTTP 429 do YouTube
    if limitado:
        raise ErroBloqueio("HTTP 429 em todas as tentativas de legenda")
    return None


def transcrever_audio_elevenlabs(url: str, pasta: Path) -> str | None:
    chave = env("ELEVENLABS_API_KEY", obrigatorio=False)
    if not chave:
        return None
    import yt_dlp
    opts = {"quiet": True, "no_warnings": True, "format": "bestaudio[ext=m4a]/bestaudio",
            "outtmpl": str(pasta / "ref_audio.%(ext)s")}
    with yt_dlp.YoutubeDL(opts) as ydl:
        ydl.download([url])
    audio = next(iter(pasta.glob("ref_audio.*")), None)
    if not audio:
        return None
    with open(audio, "rb") as f:
        r = requests.post("https://api.elevenlabs.io/v1/speech-to-text",
                          headers={"xi-api-key": chave},
                          data={"model_id": "scribe_v1"},
                          files={"file": (audio.name, f)}, timeout=300)
    r.raise_for_status()
    return r.json().get("text")


def transcrever(url: str, pasta: Path, idioma: str | None) -> str | None:
    destino = pasta / "transcricao.txt"
    if destino.exists():
        return destino.read_text(encoding="utf-8")
    vtt = baixar_legenda(url, pasta, idioma)
    texto = vtt_para_texto(vtt) if vtt else transcrever_audio_elevenlabs(url, pasta)
    if texto:
        destino.write_text(texto, encoding="utf-8")
    return texto
