"""Reels no Instagram pela API oficial (Graph API com login do Facebook).

Caminho do login do Facebook porque é o único que aceita enviar o arquivo local
(upload resumível); o login só do Instagram exige o vídeo num link público.
Exige conta profissional do Instagram ligada a uma Página do Facebook.
"""
import hashlib
import time
from pathlib import Path

import requests

from .config import CFG, RAIZ, ErroConfig, env, gravar_json, ler_json

ARQ = RAIZ / "credenciais" / "instagram.json"
MAX_LEGENDA, MAX_HASHTAGS = 2200, 30


def _versao() -> str:
    return CFG["publicacao"].get("instagram", {}).get("versao_api", "v26.0")


def _graph() -> str:
    return f"https://graph.facebook.com/{_versao()}"


def _resposta(r: requests.Response) -> dict:
    try:
        dados = r.json()
    except ValueError:  # sem raise_for_status: a mensagem dele traz a URL com o token
        raise RuntimeError(f"Instagram respondeu algo inesperado (HTTP {r.status_code}).")
    if "error" in dados:
        e = dados["error"]
        raise RuntimeError(f"Instagram: {e.get('message')} (código {e.get('code')}"
                           f"{', ' + str(e['error_subcode']) if e.get('error_subcode') else ''})")
    return dados


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()[:16]


def conectado() -> bool:
    return ARQ.exists() or bool(env("INSTAGRAM_TOKEN", False))


def credencial() -> dict:
    """Conta do Instagram e token da Página (não expira). Troca o INSTAGRAM_TOKEN do .env na 1ª vez."""
    token = env("INSTAGRAM_TOKEN", False)
    salvo = ler_json(ARQ) if ARQ.exists() else None
    if salvo and (not token or salvo.get("origem") == _hash(token)):
        return salvo
    if not token:
        raise ErroConfig("Instagram não conectado: falta INSTAGRAM_TOKEN no .env (CLAUDE.md > Conexões).")
    # Token curto do Explorador da Graph API → token longo do usuário → token da Página (sem validade).
    longo = _resposta(requests.get(f"{_graph()}/oauth/access_token", params={
        "grant_type": "fb_exchange_token", "client_id": env("META_APP_ID"),
        "client_secret": env("META_APP_SECRET"), "fb_exchange_token": token}, timeout=30))["access_token"]
    contas = _resposta(requests.get(f"{_graph()}/me/accounts", params={
        "fields": "name,access_token,instagram_business_account{id,username}",
        "access_token": longo, "limit": 100}, timeout=30)).get("data", [])
    contas = [c for c in contas if c.get("instagram_business_account")]
    if not contas:
        raise ErroConfig("Nenhuma Página do Facebook com Instagram profissional ligado foi encontrada nesse token. "
                         "Ligue o Instagram à Página e gere o token marcando a Página (CLAUDE.md > Conexões).")
    pagina = CFG["publicacao"].get("instagram", {}).get("pagina") or ""
    if pagina:
        contas = [c for c in contas if pagina.lower() in
                  (c["name"].lower(), c["instagram_business_account"]["username"].lower())]
    if len(contas) != 1:
        nomes = ", ".join(f"{c['name']} (@{c['instagram_business_account']['username']})" for c in contas) or "nenhuma"
        raise ErroConfig(f"Escolha a conta em config.yaml > publicacao.instagram.pagina. Encontradas: {nomes}.")
    c = contas[0]
    salvo = {"ig_id": c["instagram_business_account"]["id"], "usuario": c["instagram_business_account"]["username"],
             "pagina": c["name"], "token": c["access_token"], "origem": _hash(token)}
    ARQ.parent.mkdir(exist_ok=True)
    gravar_json(ARQ, salvo)
    return salvo


def legenda(roteiro: dict) -> str:
    tags = [h.lstrip("#") for h in roteiro.get("hashtags", []) if h.lstrip("#").lower() != "shorts"]
    hashtags = " ".join(f"#{t}" for t in tags[:MAX_HASHTAGS])
    texto = f"{roteiro['titulo'].strip()}\n\n{roteiro['descricao'].strip()}"
    return f"{texto[:MAX_LEGENDA - len(hashtags) - 2]}\n\n{hashtags}".strip()


def enviar(video: Path, roteiro: dict, espera_max_s: int = 600) -> str:
    """Publica o Reel agora. Devolve o link do post."""
    c = credencial()
    tamanho = video.stat().st_size
    cont = _resposta(requests.post(f"{_graph()}/{c['ig_id']}/media", data={
        "media_type": "REELS", "upload_type": "resumable", "caption": legenda(roteiro),
        "share_to_feed": "true", "access_token": c["token"]}, timeout=60))
    with open(video, "rb") as f:
        r = requests.post(f"https://rupload.facebook.com/ig-api-upload/{_versao()}/{cont['id']}",
                          headers={"Authorization": f"OAuth {c['token']}", "offset": "0",
                                   "file_size": str(tamanho)}, data=f, timeout=600)
    if not _resposta(r).get("success"):
        raise RuntimeError(f"Instagram recusou o envio do arquivo: {r.text[:200]}")
    # O Instagram processa o vídeo antes de deixar publicar.
    limite = time.monotonic() + espera_max_s
    while True:
        st = _resposta(requests.get(f"{_graph()}/{cont['id']}", params={
            "fields": "status_code,status", "access_token": c["token"]}, timeout=30))
        if st.get("status_code") == "FINISHED":
            break
        if st.get("status_code") in ("ERROR", "EXPIRED"):
            raise RuntimeError(f"Instagram não processou o vídeo: {st.get('status') or st['status_code']}")
        if time.monotonic() > limite:
            raise RuntimeError("Instagram ainda processando depois de 10 min; tente de novo mais tarde.")
        time.sleep(15)
    pub = _resposta(requests.post(f"{_graph()}/{c['ig_id']}/media_publish", data={
        "creation_id": cont["id"], "access_token": c["token"]}, timeout=60))
    link = _resposta(requests.get(f"{_graph()}/{pub['id']}", params={
        "fields": "permalink", "access_token": c["token"]}, timeout=30)).get("permalink")
    return link or pub["id"]
