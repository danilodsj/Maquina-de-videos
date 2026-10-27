"""Testes da publicação em Instagram e TikTok (sem rede: respostas das APIs simuladas).

Uso: python testes/teste_publicar.py
"""
import hashlib
import json
import os
import sys
import tempfile
import time
from argparse import Namespace
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import mv  # noqa: E402
from maquina import db, instagram, publicar, tiktok  # noqa: E402
from maquina.config import CFG, gravar_json  # noqa: E402

MB = 1024 * 1024
ROTEIRO = {"titulo": "3 IAs que fazem seu conteúdo", "descricao": "Três ferramentas de IA.",
           "hashtags": ["IA", "#marketingdigital", "Shorts"] + [f"tag{i}" for i in range(40)]}


class Resp:
    def __init__(self, dados=None, status=200, texto=""):
        self.dados, self.status_code, self.text = dados, status, texto

    def json(self):
        if self.dados is None:
            raise ValueError
        return self.dados


class FalsoRequests:
    """Responde por trecho da URL, na ordem; guarda as chamadas."""
    def __init__(self, respostas):
        self.respostas, self.chamadas = respostas, []

    def _r(self, metodo, url, **kw):
        if "data" in kw and hasattr(kw["data"], "read"):
            kw["data"] = kw["data"].read()
        self.chamadas.append((metodo, url, kw))
        for i, (trecho, resp) in enumerate(self.respostas):
            if trecho in url:
                self.respostas.pop(i)
                return resp
        raise AssertionError(f"chamada inesperada: {metodo} {url}")

    def get(self, url, **kw):
        return self._r("GET", url, **kw)

    def post(self, url, **kw):
        return self._r("POST", url, **kw)

    def put(self, url, **kw):
        return self._r("PUT", url, **kw)


tmp = Path(tempfile.mkdtemp())
CFG["_dados"] = tmp
(tmp / "logs").mkdir()
(tmp / "videos").mkdir()
instagram.ARQ = tmp / "credenciais" / "instagram.json"
tiktok.ARQ = tmp / "credenciais" / "tiktok_token.json"
time.sleep = lambda s: None
video = tmp / "final.mp4"
video.write_bytes(b"x" * 3000)

# 1. Pedaços do TikTok seguem as regras (5–64 MB, último até 128 MB, contagem arredondada para baixo).
assert tiktok.partes(3000) == [(0, 2999)]
assert tiktok.partes(64 * MB) == [(0, 64 * MB - 1)]
p = tiktok.partes(100 * MB)
assert len(p) == 3 and p[0] == (0, 32 * MB - 1) and p[-1][1] == 100 * MB - 1, p
assert all(5 * MB <= f - i + 1 <= 64 * MB for i, f in p[:-1]) and p[-1][1] - p[-1][0] + 1 <= 128 * MB
assert sum(f - i + 1 for i, f in p) == 100 * MB
print("ok: pedaços do envio ao TikTok")

# 2. PKCE do TikTok: desafio em hex do SHA-256.
v, d = tiktok.pkce()
assert 43 <= len(v) <= 128 and d == hashlib.sha256(v.encode()).hexdigest() and len(d) == 64
print("ok: PKCE em hexadecimal")

# 3. Legendas: sem #Shorts, até 30 hashtags no Instagram, limite de caracteres.
leg = instagram.legenda(ROTEIRO)
assert "#Shorts" not in leg and leg.count("#") == 30 and len(leg) <= 2200 and leg.startswith("3 IAs")
assert "#Shorts" not in tiktok.legenda(ROTEIRO) and "#marketingdigital" in tiktok.legenda(ROTEIRO)
print("ok: legendas")

# 4. Instagram: troca de token, escolha da conta, upload resumível, espera e publicação.
os.environ |= {"INSTAGRAM_TOKEN": "curto", "META_APP_ID": "1", "META_APP_SECRET": "s"}
falso = FalsoRequests([
    ("/oauth/access_token", Resp({"access_token": "longo"})),
    ("/me/accounts", Resp({"data": [{"name": "Sem IG", "access_token": "x"},
                                    {"name": "Página", "access_token": "tok_pagina",
                                     "instagram_business_account": {"id": "17", "username": "maquina"}}]})),
    ("/17/media_publish", Resp({"id": "99"})),
    ("/17/media", Resp({"id": "c1", "uri": "https://rupload.facebook.com/x"})),
    ("rupload.facebook.com", Resp({"success": True})),
    ("/c1", Resp({"status_code": "IN_PROGRESS"})),
    ("/c1", Resp({"status_code": "FINISHED"})),
    ("/99", Resp({"permalink": "https://www.instagram.com/reel/abc/"})),
])
instagram.requests = falso
assert instagram.enviar(video, ROTEIRO) == "https://www.instagram.com/reel/abc/"
cont = next(kw for m, u, kw in falso.chamadas if u.endswith("/17/media"))
assert cont["data"]["media_type"] == "REELS" and cont["data"]["upload_type"] == "resumable"
assert cont["data"]["access_token"] == "tok_pagina"
up = next(kw for m, u, kw in falso.chamadas if "rupload" in u)
assert up["headers"]["file_size"] == "3000" and up["headers"]["Authorization"] == "OAuth tok_pagina"
assert up["data"] == b"x" * 3000
assert json.loads(instagram.ARQ.read_text(encoding="utf-8"))["ig_id"] == "17"
assert not falso.respostas, falso.respostas
# Na 2ª vez usa o token salvo, sem trocar de novo; erro da Graph vira mensagem legível.
instagram.requests = FalsoRequests([("/17/media", Resp({"error": {"message": "Sem permissão", "code": 10}}))])
try:
    instagram.enviar(video, ROTEIRO)
    raise AssertionError("devia falhar")
except RuntimeError as e:
    assert "Sem permissão" in str(e) and "código 10" in str(e), e
print("ok: Instagram (token da Página, upload, publicação, erro)")

# 5. TikTok: token renovado com o refresh, envio para rascunhos e espera do status.
os.environ |= {"TIKTOK_CLIENT_KEY": "ck", "TIKTOK_CLIENT_SECRET": "cs"}
tiktok.ARQ.parent.mkdir(exist_ok=True)
gravar_json(tiktok.ARQ, {"access_token": "velho", "refresh_token": "r1", "open_id": "u",
                         "expira": time.time() - 10, "refresh_expira": time.time() + 9999})
falso = FalsoRequests([
    ("/oauth/token/", Resp({"access_token": "novo", "refresh_token": "r2", "open_id": "u",
                            "expires_in": 86400, "refresh_expires_in": 31536000})),
    ("/inbox/video/init/", Resp({"data": {"publish_id": "p1", "upload_url": "https://up.tiktok/u"},
                                 "error": {"code": "ok"}})),
    ("https://up.tiktok/u", Resp(status=201)),
    ("/status/fetch/", Resp({"data": {"status": "PROCESSING_UPLOAD"}, "error": {"code": "ok"}})),
    ("/status/fetch/", Resp({"data": {"status": "SEND_TO_USER_INBOX"}, "error": {"code": "ok"}})),
])
tiktok.requests = falso
assert tiktok.enviar(video, ROTEIRO) == "p1"
tok = next(kw for m, u, kw in falso.chamadas if "/oauth/token/" in u)["data"]
assert tok["grant_type"] == "refresh_token" and tok["refresh_token"] == "r1" and tok["client_key"] == "ck"
ini = next(kw for m, u, kw in falso.chamadas if "/init/" in u)
assert ini["json"]["source_info"] == {"source": "FILE_UPLOAD", "video_size": 3000,
                                      "chunk_size": 3000, "total_chunk_count": 1}
assert ini["headers"]["Authorization"] == "Bearer novo"
put = next(kw for m, u, kw in falso.chamadas if m == "PUT")
assert put["headers"]["Content-Range"] == "bytes 0-2999/3000" and len(put["data"]) == 3000
assert json.loads(tiktok.ARQ.read_text(encoding="utf-8"))["refresh_token"] == "r2"
assert not falso.respostas
# Sem token válido e fora do modo interativo: pede para conectar, não abre navegador.
gravar_json(tiktok.ARQ, {"access_token": "a", "refresh_token": "r", "expira": 0, "refresh_expira": 0})
try:
    tiktok.token()
    raise AssertionError("devia pedir conectar")
except Exception as e:
    assert "conectar tiktok" in str(e), e
print("ok: TikTok (refresh, rascunho, status, falta de autorização)")

# 6. publicar + despachar: fila por rede, horário, reserva sem duplicar, erro por rede.
enviados = []


def falso_enviar(rede, arq, roteiro):
    if rede == "tiktok" and os.environ.get("FALHAR_TIKTOK"):
        raise RuntimeError("spam_risk_too_many_pending_share")
    enviados.append(rede)
    return f"ref-{rede}"


publicar.enviar_agora = falso_enviar
publicar.conectado = lambda rede: True
con = db.conectar()
for vid, n in (("vidA", 1), ("vidB", 2)):
    db.salvar_candidato(con, {"id": vid, "titulo": f"Vídeo {n}"})
    gravar_json(mv.pasta_video(vid) / "roteiro.json", ROTEIRO)
    db.mudar(con, vid, "produzido", saida=str(video))


def pub(ref, **kw):
    mv.cmd_publicar(Namespace(ref=ref, redes=kw.get("redes", "instagram,tiktok"),
                              quando=kw.get("quando"), agora=kw.get("agora", False)))


futuro = (datetime.now() + timedelta(days=2)).strftime("%Y-%m-%d 18:00")
pub("vidA", quando=futuro)
pubs = db.publicacoes(con, "vidA")
assert {r: p["estado"] for r, p in pubs.items()} == {"instagram": "agendado", "tiktok": "agendado"}
assert db.obter(con, "vidA")["status"] == "publicado" and db.obter(con, "vidA")["agendado_para"].startswith(futuro[:10])
mv.cmd_despachar(Namespace())  # nada venceu ainda
assert enviados == []
try:
    pub("vidA", quando=futuro)
    raise AssertionError("devia dizer que não há nada a fazer")
except SystemExit as e:
    assert "Nada a fazer" in str(e)
# O horário chega: despachar envia as duas e não envia de novo na rodada seguinte.
passado = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat(timespec="seconds")
con.execute("UPDATE publicacoes SET quando=? WHERE video_id='vidA'", (passado,))
con.commit()
mv.cmd_despachar(Namespace())
mv.cmd_despachar(Namespace())
assert sorted(enviados) == ["instagram", "tiktok"], enviados
assert {p["estado"] for p in db.publicacoes(con, "vidA").values()} == {"enviado"}
assert not db.reservar_publicacao(con, "vidA", "instagram")
# --agora com erro numa rede: a outra sai, a com erro fica marcada e pode ser refeita com --redes.
enviados.clear()
os.environ["FALHAR_TIKTOK"] = "1"
try:
    pub("vidB", agora=True)
    raise AssertionError("devia sair com erro")
except SystemExit as e:
    assert e.code == 1
pubs = db.publicacoes(con, "vidB")
assert pubs["instagram"]["estado"] == "enviado" and pubs["tiktok"]["estado"] == "erro"
assert "spam_risk" in pubs["tiktok"]["erro"]
del os.environ["FALHAR_TIKTOK"]
pub("vidB", redes="tiktok")  # horário do vídeo já passou → sai na hora
assert db.publicacoes(con, "vidB")["tiktok"]["estado"] == "enviado" and enviados == ["instagram", "tiktok"]
try:
    pub("vidB", redes="facebook")
    raise AssertionError("devia recusar rede desconhecida")
except SystemExit as e:
    assert "desconhecida" in str(e)
mv.cmd_agenda(Namespace())
print("ok: publicar/despachar (fila, horário, sem duplicar, erro por rede)")
print("Todos os testes passaram.")
