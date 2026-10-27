"""TikTok pela API oficial (Content Posting, modo rascunho).

O vídeo vai para a caixa de entrada do app do TikTok; você abre a notificação,
cola a legenda e toca em Publicar. A publicação direta pela API exige uma auditoria
que o TikTok não concede para ferramentas de uso próprio (fica tudo privado).
"""
import hashlib
import secrets
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlparse

import requests

from .config import CFG, RAIZ, ErroConfig, env, gravar_json, ler_json

ARQ = RAIZ / "credenciais" / "tiktok_token.json"
API = "https://open.tiktokapis.com/v2"
ESCOPOS = "user.info.basic,video.upload"
MB = 1024 * 1024


def _porta() -> int:
    return int(CFG["publicacao"].get("tiktok", {}).get("porta", 8765))


def redirect_uri() -> str:
    return f"http://localhost:{_porta()}/callback/"


def conectado() -> bool:
    return ARQ.exists()


def _api(r: requests.Response) -> dict:
    try:
        dados = r.json()
    except ValueError:
        raise RuntimeError(f"TikTok respondeu algo inesperado (HTTP {r.status_code}).")
    erro = dados.get("error")
    if isinstance(erro, dict) and erro.get("code") not in (None, "ok"):
        raise RuntimeError(f"TikTok: {erro.get('message') or erro['code']} ({erro['code']})")
    if isinstance(erro, str):  # formato do endpoint de token
        raise RuntimeError(f"TikTok: {dados.get('error_description') or erro}")
    return dados


def _pedir_token(**campos) -> dict:
    campos |= {"client_key": env("TIKTOK_CLIENT_KEY"), "client_secret": env("TIKTOK_CLIENT_SECRET")}
    t = _api(requests.post(f"{API}/oauth/token/", data=campos, timeout=30))
    agora = time.time()
    return {"access_token": t["access_token"], "refresh_token": t["refresh_token"], "open_id": t.get("open_id"),
            "expira": agora + t["expires_in"], "refresh_expira": agora + t["refresh_expires_in"]}


def pkce() -> tuple[str, str]:
    """O TikTok pede o desafio em hexadecimal do SHA-256 (não base64url como no RFC 7636)."""
    verificador = secrets.token_urlsafe(48)
    return verificador, hashlib.sha256(verificador.encode()).hexdigest()


def autorizar() -> dict:
    """Abre o navegador para você autorizar a conta e recebe o código em localhost."""
    verificador, desafio = pkce()
    estado = secrets.token_urlsafe(16)
    recebido: dict = {}

    class Retorno(BaseHTTPRequestHandler):
        def do_GET(self):
            q = {k: v[0] for k, v in parse_qs(urlparse(self.path).query).items()}
            if "code" in q or "error" in q:
                recebido.update(q)
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write("<p>Pronto, pode fechar esta aba e voltar ao terminal.</p>".encode())

        def log_message(self, *_):
            pass

    servidor = HTTPServer(("localhost", _porta()), Retorno)
    servidor.timeout = 5
    url = "https://www.tiktok.com/v2/auth/authorize/?" + urlencode({
        "client_key": env("TIKTOK_CLIENT_KEY"), "response_type": "code", "scope": ESCOPOS,
        "redirect_uri": redirect_uri(), "state": estado,
        "code_challenge": desafio, "code_challenge_method": "S256"})
    print(f"Autorize a conta do TikTok no navegador (se não abrir, acesse):\n{url}")
    webbrowser.open(url)
    limite = time.monotonic() + 300
    try:
        while not recebido and time.monotonic() < limite:
            servidor.handle_request()
    finally:
        servidor.server_close()
    if not recebido:
        raise ErroConfig("Não recebi a autorização do TikTok em 5 minutos. Rode: python mv.py conectar tiktok")
    if recebido.get("state") != estado or "code" not in recebido:
        raise ErroConfig(f"Autorização do TikTok recusada: {recebido.get('error_description') or recebido.get('error')}")
    return _pedir_token(code=recebido["code"], grant_type="authorization_code",
                        redirect_uri=redirect_uri(), code_verifier=verificador)


def token(interativo: bool = False) -> str:
    """Token válido; renova sozinho com o refresh token (vale 1 ano)."""
    t = ler_json(ARQ) if ARQ.exists() else None
    agora = time.time()
    if t and t["expira"] > agora + 300:
        return t["access_token"]
    novo = None
    if t and t["refresh_expira"] > agora + 300:
        try:
            novo = _pedir_token(grant_type="refresh_token", refresh_token=t["refresh_token"])
        except RuntimeError:
            novo = None  # autorização revogada: precisa autorizar de novo
    if not novo:
        if not interativo:
            raise ErroConfig("TikTok sem autorização válida. Rode: python mv.py conectar tiktok")
        novo = autorizar()
    ARQ.parent.mkdir(exist_ok=True)
    gravar_json(ARQ, novo)
    return novo["access_token"]


def _cabecalho(tok: str) -> dict:
    return {"Authorization": f"Bearer {tok}", "Content-Type": "application/json; charset=UTF-8"}


def usuario(interativo: bool = False) -> str:
    dados = _api(requests.get(f"{API}/user/info/", params={"fields": "display_name"},
                              headers=_cabecalho(token(interativo)), timeout=30))
    return dados["data"]["user"]["display_name"]


def partes(tamanho: int) -> list[tuple[int, int]]:
    """Pedaços (início, fim) do envio: até 64 MB vai inteiro; acima, pedaços de 32 MB e o
    último absorve o resto (regras do TikTok: 5–64 MB por pedaço, último até 128 MB)."""
    if tamanho <= 64 * MB:
        return [(0, tamanho - 1)]
    pedaco = 32 * MB
    n = tamanho // pedaco
    return [(i * pedaco, (i + 1) * pedaco - 1 if i < n - 1 else tamanho - 1) for i in range(n)]


def legenda(roteiro: dict) -> str:
    tags = [h.lstrip("#") for h in roteiro.get("hashtags", []) if h.lstrip("#").lower() != "shorts"]
    return f"{roteiro['titulo'].strip()} {' '.join(f'#{t}' for t in tags)}".strip()[:2200]


def enviar(video: Path, roteiro: dict, espera_max_s: int = 180) -> str:
    """Manda o vídeo para a caixa de rascunhos do TikTok. Devolve o publish_id."""
    tok = token()
    tamanho = video.stat().st_size
    blocos = partes(tamanho)
    ini = _api(requests.post(f"{API}/post/publish/inbox/video/init/", headers=_cabecalho(tok), json={
        "source_info": {"source": "FILE_UPLOAD", "video_size": tamanho,
                        "chunk_size": blocos[0][1] + 1, "total_chunk_count": len(blocos)}}, timeout=60))["data"]
    with open(video, "rb") as f:
        for inicio, fim in blocos:
            f.seek(inicio)
            r = requests.put(ini["upload_url"], data=f.read(fim - inicio + 1), timeout=600, headers={
                "Content-Type": "video/mp4", "Content-Range": f"bytes {inicio}-{fim}/{tamanho}"})
            if r.status_code not in (201, 206):
                raise RuntimeError(f"TikTok recusou o envio (HTTP {r.status_code}): {r.text[:200]}")
    limite = time.monotonic() + espera_max_s
    while time.monotonic() < limite:
        st = _api(requests.post(f"{API}/post/publish/status/fetch/", headers=_cabecalho(tok),
                                json={"publish_id": ini["publish_id"]}, timeout=30))["data"]
        if st.get("status") == "FAILED":
            raise RuntimeError(f"TikTok não processou o vídeo: {st.get('fail_reason')}")
        if st.get("status") in ("SEND_TO_USER_INBOX", "PUBLISH_COMPLETE"):
            break
        time.sleep(5)
    return ini["publish_id"]
