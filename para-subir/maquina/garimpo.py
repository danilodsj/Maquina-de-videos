"""Busca Shorts recentes do nicho no YouTube, pela API oficial ou pelo yt-dlp."""
import re
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

import requests

from .config import CFG, env

API = "https://www.googleapis.com/youtube/v3"


class ErroCota(Exception):
    pass


# ---------- API oficial ----------

def _api(endpoint: str, **params) -> dict:
    params["key"] = env("YOUTUBE_API_KEY")
    for tentativa in range(3):
        try:
            r = requests.get(f"{API}/{endpoint}", params=params, timeout=30)
        except requests.RequestException:
            time.sleep(2 ** tentativa)
            continue
        if r.status_code == 403 and "quota" in r.text.lower():
            raise ErroCota("Cota diária da API do YouTube esgotada. Tente amanhã ou use --fonte ytdlp.")
        if r.status_code >= 500:
            time.sleep(2 ** tentativa)
            continue
        r.raise_for_status()
        return r.json()
    raise RuntimeError(f"API do YouTube não respondeu ({endpoint}).")


def _duracao_iso(d: str) -> float:
    m = re.fullmatch(r"P(?:(\d+)D)?T?(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", d or "")
    if not m:
        return 0
    dias, h, mi, s = (int(x or 0) for x in m.groups())
    return dias * 86400 + h * 3600 + mi * 60 + s


def _ids_busca_api(depois_de: str) -> dict[str, str]:
    n = CFG["nicho"]
    ids: dict[str, str] = {}
    buscas = 0
    for idioma in n["idiomas"]:
        for kw in n["palavras_chave"].get(idioma, []):
            if buscas >= CFG["garimpo"]["max_buscas_api"]:
                return ids
            dados = _api("search", part="id", q=kw, type="video", videoDuration="short",
                         order="viewCount", publishedAfter=depois_de, relevanceLanguage=idioma,
                         maxResults=min(CFG["garimpo"]["resultados_por_busca"], 50))
            buscas += 1
            for item in dados.get("items", []):
                ids.setdefault(item["id"]["videoId"], kw)
    return ids


def _ids_canais_api() -> dict[str, str]:
    ids: dict[str, str] = {}
    for canal in CFG["nicho"].get("canais_referencia") or []:
        filtro = {"forHandle": canal} if canal.startswith("@") else {"id": canal}
        dados = _api("channels", part="id", **filtro)
        if not dados.get("items"):
            print(f"  canal não encontrado: {canal}")
            continue
        uploads = "UU" + dados["items"][0]["id"][2:]
        lista = _api("playlistItems", part="contentDetails", playlistId=uploads, maxResults=50)
        for item in lista.get("items", []):
            ids.setdefault(item["contentDetails"]["videoId"], f"canal {canal}")
    return ids


def _detalhes_api(ids: dict[str, str]) -> list[dict]:
    lista = list(ids)
    videos, canais = [], {}
    for i in range(0, len(lista), 50):
        dados = _api("videos", part="snippet,statistics,contentDetails", id=",".join(lista[i:i + 50]))
        for it in dados.get("items", []):
            sn, st = it["snippet"], it.get("statistics", {})
            videos.append({
                "id": it["id"],
                "titulo": sn["title"],
                "canal": sn["channelTitle"],
                "canal_id": sn["channelId"],
                "url": f"https://www.youtube.com/shorts/{it['id']}",
                "publicado_em": sn["publishedAt"],
                "duracao_s": _duracao_iso(it["contentDetails"]["duration"]),
                "views": int(st.get("viewCount", 0)),
                "likes": int(st.get("likeCount", 0)),
                "comentarios": int(st.get("commentCount", 0)),
                "idioma": (sn.get("defaultAudioLanguage") or sn.get("defaultLanguage") or "")[:2] or None,
                "palavra_chave": ids[it["id"]],
            })
    canal_ids = sorted({v["canal_id"] for v in videos})
    for i in range(0, len(canal_ids), 50):
        dados = _api("channels", part="statistics", id=",".join(canal_ids[i:i + 50]))
        for it in dados.get("items", []):
            st = it.get("statistics", {})
            canais[it["id"]] = None if st.get("hiddenSubscriberCount") else int(st.get("subscriberCount", 0)) or None
    for v in videos:
        v["inscritos_canal"] = canais.get(v["canal_id"])
    return videos


def _eh_short(video_id: str) -> bool:
    """/shorts/<id> responde 200 para Shorts e redireciona os vídeos comuns."""
    try:
        r = requests.head(f"https://www.youtube.com/shorts/{video_id}", allow_redirects=False, timeout=10)
        return r.status_code == 200 or r.status_code not in (301, 302, 303, 307, 308)
    except requests.RequestException:
        return True


def via_api() -> list[dict]:
    depois_de = (datetime.now(timezone.utc) - timedelta(days=CFG["garimpo"]["max_idade_dias"]))
    ids = _ids_busca_api(depois_de.strftime("%Y-%m-%dT%H:%M:%SZ"))
    ids.update({k: v for k, v in _ids_canais_api().items() if k not in ids})
    print(f"  {len(ids)} vídeos encontrados, buscando estatísticas...")
    return _detalhes_api(ids)


# ---------- yt-dlp (sem chave) ----------

class ErroBloqueio(Exception):
    pass


def _ytdlp_info(alvo: str, plano: bool) -> dict | None:
    import yt_dlp
    opts = {"quiet": True, "no_warnings": True, "skip_download": True, "logger": _Silencio()}
    if plano:
        opts["extract_flat"] = "in_playlist"
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            return ydl.extract_info(alvo, download=False)
    except yt_dlp.utils.DownloadError as e:
        if "not a bot" in str(e):
            raise ErroBloqueio(str(e)) from None
        return None  # vídeo removido, privado, live etc.


class _Silencio:
    def debug(self, msg): pass
    def info(self, msg): pass
    def warning(self, msg): pass
    def error(self, msg): pass


def via_ytdlp() -> list[dict]:
    g, n = CFG["garimpo"], CFG["nicho"]
    alvos: dict[str, str] = {}
    views_lista: dict[str, int] = {}

    def anotar(entradas, origem, limite):
        for e in (entradas or [])[:limite]:
            # Só vídeos (ID de 11 caracteres); a listagem também traz canais e playlists.
            if not e or e.get("ie_key") not in (None, "Youtube") or len(e.get("id") or "") != 11:
                continue
            # Pré-filtro com o que a busca já informa, para não abrir vídeos que nunca passariam.
            if e.get("view_count") is not None and e["view_count"] < g["min_views"]:
                continue
            if e.get("duration") and e["duration"] > g["max_duracao_s"]:
                continue
            alvos.setdefault(e["id"], origem)
            views_lista[e["id"]] = e.get("view_count") or 0

    # A busca por palavra-chave do yt-dlp não filtra Shorts; as páginas de hashtag sim.
    for tag in n.get("hashtags") or []:
        tag = tag.lstrip("#")
        info = _ytdlp_info(f"https://www.youtube.com/hashtag/{tag}/shorts", plano=True) or {}
        anotar(info.get("entries"), f"#{tag}", g["resultados_por_hashtag"])
    for canal in n.get("canais_referencia") or []:
        url = f"https://www.youtube.com/{canal}/shorts" if canal.startswith("@") else f"https://www.youtube.com/channel/{canal}/shorts"
        info = _ytdlp_info(url, plano=True) or {}
        anotar(info.get("entries"), f"canal {canal}", 30)
    # Abrir cada vídeo é o que o YouTube limita: só os mais vistos, devagar.
    escolhidos = sorted(alvos, key=lambda k: -views_lista.get(k, 0))[:g["max_detalhes_ytdlp"]]
    print(f"  {len(alvos)} Shorts listados; abrindo os {len(escolhidos)} mais vistos...")

    def detalhe(vid: str) -> dict | None:
        i = _ytdlp_info(f"https://www.youtube.com/shorts/{vid}", plano=False)
        if not i or not i.get("timestamp"):
            return None
        if i.get("width") and i.get("height") and i["width"] > i["height"]:
            return None  # horizontal: não é Short
        return {
            "id": vid,
            "titulo": i.get("title"),
            "canal": i.get("channel") or i.get("uploader"),
            "canal_id": i.get("channel_id"),
            "url": f"https://www.youtube.com/shorts/{vid}",
            "publicado_em": datetime.fromtimestamp(i["timestamp"], timezone.utc).isoformat(),
            "duracao_s": i.get("duration") or 0,
            "views": i.get("view_count") or 0,
            "likes": i.get("like_count") or 0,
            "comentarios": i.get("comment_count") or 0,
            "inscritos_canal": i.get("channel_follower_count"),
            "idioma": (i.get("language") or "")[:2] or None,
            "palavra_chave": alvos[vid],
        }

    saida = []
    for vid in escolhidos:
        try:
            v = detalhe(vid)
        except ErroBloqueio:
            print("  O YouTube pediu verificação anti-robô e pausou as consultas deste IP.\n"
                  "  Guardando o que já foi lido. Espere algumas horas ou configure YOUTUBE_API_KEY.")
            break
        if v:
            saida.append(v)
        time.sleep(g["pausa_ytdlp_s"])
    return saida


def filtrar(videos: list[dict]) -> list[dict]:
    g = CFG["garimpo"]
    limite = datetime.now(timezone.utc) - timedelta(days=g["max_idade_dias"])
    saida = []
    for v in videos:
        publicado = datetime.fromisoformat(v["publicado_em"].replace("Z", "+00:00"))
        if publicado < limite or not v["duracao_s"] or v["duracao_s"] > g["max_duracao_s"]:
            continue
        if (v["views"] or 0) < g["min_views"]:
            continue
        # A API só "prefere" o idioma pedido; descarta os que declaram outro idioma.
        if v.get("idioma") and v["idioma"] not in CFG["nicho"]["idiomas"]:
            continue
        saida.append(v)
    return saida


def garimpar(fonte: str = "auto") -> list[dict]:
    if fonte == "auto":
        fonte = "api" if env("YOUTUBE_API_KEY", obrigatorio=False) else "ytdlp"
    print(f"Garimpo via {fonte}...")
    videos = via_api() if fonte == "api" else via_ytdlp()
    videos = filtrar(videos)
    if fonte == "api":
        with ThreadPoolExecutor(max_workers=8) as ex:
            videos = [v for v, ok in zip(videos, ex.map(_eh_short, [v["id"] for v in videos])) if ok]
    return videos
