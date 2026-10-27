"""Publicação: YouTube (envio com agendamento nativo), Instagram e TikTok (saem na hora,
pelo `despachar`, porque as APIs deles não agendam)."""
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from .config import CFG, RAIZ, ErroConfig

CRED = RAIZ / "credenciais"
ESCOPOS = ["https://www.googleapis.com/auth/youtube.upload"]
REDES = ("youtube", "instagram", "tiktok")
NOMES = {"youtube": "YouTube", "instagram": "Instagram", "tiktok": "TikTok"}


def _servico():
    from google.auth.exceptions import RefreshError
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build

    segredo, token = CRED / "client_secret.json", CRED / "token.json"
    if not segredo.exists() and not token.exists():
        raise ErroConfig("Falta credenciais/client_secret.json (OAuth do Google Cloud). Veja CLAUDE.md > Conexões.")
    cred = Credentials.from_authorized_user_file(str(token), ESCOPOS) if token.exists() else None
    if cred and cred.expired and cred.refresh_token:
        try:
            cred.refresh(Request())
        except RefreshError:
            cred = None  # autorização revogada ou expirada: precisa autorizar de novo
    if not cred or not cred.valid:
        if not segredo.exists():
            raise ErroConfig("A autorização do YouTube expirou e falta credenciais/client_secret.json para "
                             "autorizar de novo. Baixe o JSON do OAuth (CLAUDE.md > Conexões).")
        # Abre o navegador uma única vez para você autorizar o canal.
        cred = InstalledAppFlow.from_client_secrets_file(str(segredo), ESCOPOS).run_local_server(port=0)
    token.write_text(cred.to_json(), encoding="utf-8")
    return build("youtube", "v3", credentials=cred)


def proximo_horario(ocupados: set[str]) -> datetime:
    p = CFG["publicacao"]
    fuso = ZoneInfo(p["fuso"])
    minimo = datetime.now(fuso) + timedelta(hours=p["antecedencia_min_h"])
    dia = minimo.date()
    for _ in range(60):
        no_dia = [o for o in ocupados if o.startswith(dia.isoformat())]
        if len(no_dia) < p["max_por_dia"]:
            for h in p["horarios"]:
                hh, mm = map(int, h.split(":"))
                quando = datetime(dia.year, dia.month, dia.day, hh, mm, tzinfo=fuso)
                if quando >= minimo and quando.isoformat(timespec="minutes") not in ocupados:
                    return quando
        dia += timedelta(days=1)
    raise RuntimeError("Nenhum horário livre nos próximos 60 dias.")


def enviar(video: Path, roteiro: dict, quando: datetime) -> str:
    from googleapiclient.http import MediaFileUpload

    p = CFG["publicacao"]
    tags = [h.lstrip("#") for h in roteiro.get("hashtags", [])]
    descricao = roteiro["descricao"].strip()
    hashtags = " ".join(f"#{t}" for t in tags)
    if "#shorts" not in hashtags.lower():
        hashtags = (hashtags + " #Shorts").strip()
    agora = datetime.now(ZoneInfo("UTC"))
    corpo = {
        "snippet": {
            "title": roteiro["titulo"][:100],
            "description": f"{descricao}\n\n{hashtags}"[:5000],
            "tags": tags[:15],
            "categoryId": p["categoria_id"],
            "defaultLanguage": p["idioma"],
            "defaultAudioLanguage": p["idioma"],
        },
        "status": {
            "privacyStatus": "private",
            "publishAt": quando.astimezone(ZoneInfo("UTC")).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "selfDeclaredMadeForKids": False,
            "containsSyntheticMedia": bool(p.get("declarar_ia")),
        },
    }
    if quando <= agora:  # horário já passou: sai público na hora (o YouTube recusa publishAt no passado)
        corpo["status"]["privacyStatus"] = "public"
        del corpo["status"]["publishAt"]
    req = _servico().videos().insert(part="snippet,status", body=corpo,
                                     media_body=MediaFileUpload(str(video), chunksize=-1, resumable=True))
    resposta = None
    while resposta is None:
        _, resposta = req.next_chunk()
    return resposta["id"]


def conectado(rede: str) -> bool:
    """Confere só se há credencial no disco (sem rede), para avisar antes de agendar."""
    if rede == "youtube":
        return (CRED / "client_secret.json").exists() or (CRED / "token.json").exists()
    from . import instagram, tiktok
    return {"instagram": instagram, "tiktok": tiktok}[rede].conectado()


def enviar_agora(rede: str, video: Path, roteiro: dict) -> str:
    """Instagram publica o Reel; TikTok manda para os rascunhos e grava a legenda ao lado do MP4."""
    if rede == "instagram":
        from . import instagram
        return instagram.enviar(video, roteiro)
    if rede == "tiktok":
        from . import tiktok
        ref = tiktok.enviar(video, roteiro)
        video.with_suffix(".tiktok.txt").write_text(tiktok.legenda(roteiro) + "\n", encoding="utf-8")
        return ref
    raise ValueError(rede)
