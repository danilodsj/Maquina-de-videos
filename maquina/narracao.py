"""Narração com tempo de cada palavra, por ElevenLabs ou Google Cloud Text-to-Speech.

Os dois provedores gravam narracao.mp3 e narracao.json com a lista de palavras
[{"w", "s", "e"}], que o motor usa para sincronizar cenas e legendas.
"""
import base64
import re
import subprocess
from pathlib import Path
from xml.sax.saxutils import escape

import requests

from .config import CFG, env, gravar_json
from .render.motor import palavras_do_alinhamento, palavras_fala

_COM_TAGS = ("eleven_v3", "eleven_v4")
# Os modelos v3/v4 da ElevenLabs entendem marcações de tom em inglês; as do roteiro são em português.
_TAGS_EN = {"animado": "excited", "animada": "excited", "sério": "serious", "serio": "serious",
            "sussurrando": "whispers", "rindo": "laughs", "curioso": "curious", "surpreso": "surprised",
            "empolgado": "excited", "calmo": "calm", "dramático": "dramatic"}


def _tags_ingles(texto: str) -> str:
    """Troca [animado] por [excited] etc.; marcação desconhecida é removida para não ser lida em voz alta."""
    return re.sub(r"\[([^\]]*)\]", lambda m: f"[{_TAGS_EN[m[1].strip().lower()]}]"
                  if m[1].strip().lower() in _TAGS_EN else " ", texto)


def texto_narracao(roteiro: dict) -> str:
    return " ".join(c["fala"].replace("*", "").strip() for c in roteiro["cenas"])


def sem_tags(texto: str) -> str:
    """Texto falado sem [marcações], separado em palavras do mesmo jeito que o motor conta as cenas."""
    return " ".join(palavras_fala(texto))


def narrar(roteiro: dict, mp3: Path, saida_json: Path, provedor: str | None = None) -> str:
    """Gera a narração uma única vez (cada chamada pode ser cobrada). Devolve "provedor/voz"."""
    provedor = provedor or CFG["narracao"].get("provedor", "elevenlabs")
    if provedor == "google":
        return _google(roteiro, mp3, saida_json)
    if provedor == "elevenlabs":
        return _elevenlabs(roteiro, mp3, saida_json)
    raise ValueError(f"provedor de narração desconhecido: {provedor} (use elevenlabs ou google)")


# ---------- ElevenLabs ----------

def _elevenlabs(roteiro: dict, mp3: Path, saida_json: Path) -> str:
    n = CFG["narracao"]["elevenlabs"]
    chave = env("ELEVENLABS_API_KEY")
    voz = roteiro.get("voice_id") or n["voice_id"]
    texto = texto_narracao(roteiro)
    ultimo_erro = ""
    for modelo in n["modelos"]:
        corpo = {
            "text": _tags_ingles(texto) if modelo.startswith(_COM_TAGS) else sem_tags(texto),
            "model_id": modelo,
            "language_code": "pt",
            "voice_settings": {"stability": n["estabilidade"], "similarity_boost": n["similaridade"],
                               "style": n["estilo"], "speed": n["velocidade"]},
        }
        r = requests.post(f"https://api.elevenlabs.io/v1/text-to-speech/{voz}/with-timestamps",
                          params={"output_format": "mp3_44100_128"},
                          headers={"xi-api-key": chave}, json=corpo, timeout=300)
        if r.status_code in (400, 422) and "model" in r.text.lower():
            ultimo_erro = r.text[:300]
            continue  # modelo não aceito neste endpoint: tenta o próximo
        if r.status_code == 401:
            raise RuntimeError("ElevenLabs recusou a chave (401). Confira ELEVENLABS_API_KEY no .env.")
        if r.status_code == 402 and "library voice" in r.text.lower():
            raise RuntimeError("O plano gratuito da ElevenLabs não usa vozes da biblioteca pela API. Use uma voz "
                               "padrão (premade) da conta em narracao.elevenlabs.voice_id ou assine o plano Creator.")
        if r.status_code in (401, 402) and "quota" in r.text.lower():
            raise RuntimeError("ElevenLabs sem créditos suficientes para esta narração.")
        if r.status_code == 402:
            raise RuntimeError(f"ElevenLabs exige pagamento para este pedido: {r.text[:300]}")
        r.raise_for_status()
        dados = r.json()
        mp3.write_bytes(base64.b64decode(dados["audio_base64"]))
        al = dados.get("alignment") or dados.get("normalized_alignment")
        gravar_json(saida_json, {"provedor": "elevenlabs", "modelo": modelo, "voz": voz,
                                 "palavras": palavras_do_alinhamento(al)})
        return f"elevenlabs/{modelo}"
    raise RuntimeError(f"Nenhum modelo da lista foi aceito pela ElevenLabs. Último erro: {ultimo_erro}")


# ---------- Google Cloud Text-to-Speech ----------

TTS = "https://texttospeech.googleapis.com/v1beta1"


def _chave_google() -> str:
    chave = env("GOOGLE_API_KEY", obrigatorio=False) or env("YOUTUBE_API_KEY", obrigatorio=False)
    return chave or env("GOOGLE_API_KEY")  # sem nenhuma: dispara a mensagem de configuração


def vozes_google(idioma: str = "pt-BR") -> list[dict]:
    r = requests.get(f"{TTS}/voices", params={"key": _chave_google(), "languageCode": idioma}, timeout=60)
    if r.status_code != 200:
        raise RuntimeError(f"Google não listou as vozes ({r.status_code}): {r.text[:300]}")
    return sorted(r.json().get("voices", []), key=lambda v: v["name"])


def _sintetizar(entrada: dict, voz: str, extra: dict | None = None, modelo: str | None = None) -> dict:
    g = CFG["narracao"]["google"]
    audio = {"audioEncoding": "MP3", "sampleRateHertz": 44100, "speakingRate": g["velocidade"]}
    voice = {"languageCode": voz[:5], "name": voz}
    if modelo:  # Gemini TTS: voz pelo nome curto + modelo + instrução de estilo
        voice = {"languageCode": voz[:5], "name": voz.split("-")[-1], "modelName": modelo}
        if g.get("estilo_fala"):
            entrada = {**entrada, "prompt": g["estilo_fala"]}
    elif "Chirp" not in voz:
        audio["pitch"] = g["tom"]  # as vozes Chirp não aceitam ajuste de tom
    corpo = {"input": entrada, "voice": voice, "audioConfig": audio, **(extra or {})}
    r = requests.post(f"{TTS}/text:synthesize", params={"key": _chave_google()}, json=corpo, timeout=300)
    if r.status_code == 400 and "speaking" in r.text.lower():
        corpo["audioConfig"].pop("speakingRate")  # voz sem controle de velocidade
        r = requests.post(f"{TTS}/text:synthesize", params={"key": _chave_google()}, json=corpo, timeout=300)
    if r.status_code == 403:
        raise RuntimeError("Google recusou (403). Ative a 'Cloud Text-to-Speech API' no projeto da chave "
                           "e confira se a chave não está restrita a outras APIs. Detalhe: " + r.text[:300])
    if r.status_code == 400:
        raise RuntimeError(f"Google rejeitou o pedido (400): {r.text[:400]}")
    r.raise_for_status()
    return r.json()


def _duracao(mp3: Path) -> float:
    return float(subprocess.check_output(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                                          "-of", "csv=p=0", str(mp3)]).strip())


def _google(roteiro: dict, mp3: Path, saida_json: Path) -> str:
    voz = roteiro.get("voz_google") or CFG["narracao"]["google"]["voz"]
    modelo = CFG["narracao"]["google"].get("modelo") or None
    if modelo or "Chirp" in voz:  # nenhum dos dois devolve o tempo das palavras
        return _google_por_cena(roteiro, mp3, saida_json, voz, modelo)
    return _google_marcas(roteiro, mp3, saida_json, voz)


def _google_por_cena(roteiro: dict, mp3: Path, saida_json: Path, voz: str, modelo: str | None = None) -> str:
    """Vozes Chirp e Gemini (as mais naturais) não devolvem o tempo das palavras. Gera um áudio por cena:
    a troca de cena fica exata pela duração de cada trecho; dentro da cena, cada palavra recebe
    um tempo proporcional ao seu tamanho (boa aproximação para a legenda)."""
    pasta = mp3.parent / "narracao_partes"
    pasta.mkdir(exist_ok=True)
    pausa = 0.25
    partes, palavras, t = [], [], 0.0
    for i, cena in enumerate(roteiro["cenas"]):
        ws = palavras_fala(cena["fala"])
        if not ws:
            raise RuntimeError(f"A cena {i + 1} não tem texto falado (só marcações?).")
        parte = pasta / f"{i:02d}.mp3"
        parte.write_bytes(base64.b64decode(_sintetizar({"text": " ".join(ws)}, voz, modelo=modelo)["audioContent"]))
        dur = _duracao(parte)
        pesos = [len(w) + 2 for w in ws]
        ini, util = t + 0.08, max(0.2, dur - 0.2)
        for w, p in zip(ws, pesos):
            d = util * p / sum(pesos)
            palavras.append({"w": w, "s": ini, "e": ini + d * 0.92})
            ini += d
        partes.append(parte)
        t += dur + pausa
    _concatenar_com_pausas(partes, mp3, pausa)
    gravar_json(saida_json, {"provedor": "google", "voz": voz, "modelo": modelo, "tempos": "estimados_por_cena",
                             "palavras": palavras})
    return f"google/{voz}" + (f" ({modelo})" if modelo else "")


def _concatenar_com_pausas(partes: list[Path], saida: Path, pausa: float):
    entradas, filtros = [], []
    for i, p in enumerate(partes):
        entradas += ["-i", str(p)]
        filtros.append(f"[{i}:a]aresample=44100,apad=pad_dur={pausa}[a{i}]")
    junta = "".join(f"[a{i}]" for i in range(len(partes)))
    filtro = ";".join(filtros) + f";{junta}concat=n={len(partes)}:v=0:a=1[out]"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", *entradas, "-filter_complex", filtro,
                    "-map", "[out]", "-c:a", "libmp3lame", "-b:a", "192k", str(saida)], check=True)


def _google_marcas(roteiro: dict, mp3: Path, saida_json: Path, voz: str) -> str:
    """Neural2/Wavenet/Standard: SSML com uma <mark> antes de cada palavra; a API devolve o instante de cada marca."""
    palavras = palavras_fala(texto_narracao(roteiro))
    ssml = "<speak>" + " ".join(f'<mark name="{i}"/>{escape(w)}' for i, w in enumerate(palavras)) \
           + f'<mark name="{len(palavras)}"/></speak>'
    dados = _sintetizar({"ssml": ssml}, voz, {"enableTimePointing": ["SSML_MARK"]})
    mp3.write_bytes(base64.b64decode(dados["audioContent"]))
    marcas = {int(p["markName"]): float(p.get("timeSeconds", 0.0)) for p in dados.get("timepoints", [])}
    if len(marcas) < len(palavras):
        raise RuntimeError(f"A voz {voz} não devolveu os tempos das palavras (use uma voz Neural2, Wavenet "
                           "ou Standard; as vozes Chirp não aceitam marcações).")
    fim_audio = marcas.get(len(palavras)) or (marcas[len(palavras) - 1] + 0.5)
    saida = []
    for i, w in enumerate(palavras):
        ini = marcas[i]
        fim = marcas.get(i + 1, fim_audio)
        saida.append({"w": w, "s": ini, "e": max(ini + 0.05, fim - 0.02)})
    gravar_json(saida_json, {"provedor": "google", "voz": voz, "palavras": saida})
    return f"google/{voz}"
