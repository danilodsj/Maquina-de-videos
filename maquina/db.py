"""Estado do fluxo em SQLite: cada vídeo de referência e em que etapa ele está."""
import json
import sqlite3
from datetime import datetime, timezone

from .config import CFG

# Ordem das etapas. "descartado", "sem_legenda" e "erro" ficam fora da linha principal.
STATUS = [
    "candidato", "transcrito", "triado", "aprovado",
    "roteirizado", "produzido", "publicado",
    "descartado", "sem_legenda", "erro",
]

_CAMPOS = [
    "id", "titulo", "canal", "canal_id", "url", "publicado_em", "duracao_s",
    "views", "likes", "comentarios", "inscritos_canal", "idioma", "palavra_chave",
    "nota", "nota_detalhes",
]


def _agora() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def conectar() -> sqlite3.Connection:
    con = sqlite3.connect(CFG["_dados"] / "estado.db")
    con.row_factory = sqlite3.Row
    con.execute("""
        CREATE TABLE IF NOT EXISTS videos (
            n INTEGER PRIMARY KEY AUTOINCREMENT,
            id TEXT UNIQUE NOT NULL,
            titulo TEXT, canal TEXT, canal_id TEXT, url TEXT,
            publicado_em TEXT, duracao_s REAL,
            views INTEGER, likes INTEGER, comentarios INTEGER, inscritos_canal INTEGER,
            idioma TEXT, palavra_chave TEXT,
            nota REAL, nota_detalhes TEXT,
            status TEXT NOT NULL DEFAULT 'candidato',
            agendado_para TEXT, youtube_publicado TEXT, saida TEXT, erro TEXT,
            encontrado_em TEXT, atualizado_em TEXT
        )""")
    # Uma linha por rede em que o vídeo sai. quando = horário de publicação em UTC (ISO).
    # estado: agendado → enviando → enviado | erro.
    con.execute("""
        CREATE TABLE IF NOT EXISTS publicacoes (
            video_id TEXT NOT NULL, rede TEXT NOT NULL,
            quando TEXT NOT NULL, estado TEXT NOT NULL,
            ref TEXT, erro TEXT, atualizado_em TEXT,
            PRIMARY KEY (video_id, rede)
        )""")
    return con


def salvar_candidato(con, v: dict) -> bool:
    """Insere um candidato novo ou atualiza as métricas de um existente. Devolve True se é novo."""
    dados = {k: v.get(k) for k in _CAMPOS}
    if isinstance(dados["nota_detalhes"], dict):
        dados["nota_detalhes"] = json.dumps(dados["nota_detalhes"], ensure_ascii=False)
    existe = con.execute("SELECT status FROM videos WHERE id=?", (v["id"],)).fetchone()
    if existe:
        sets = ", ".join(f"{k}=?" for k in dados if k != "id")
        con.execute(f"UPDATE videos SET {sets}, atualizado_em=? WHERE id=?",
                    [dados[k] for k in dados if k != "id"] + [_agora(), v["id"]])
        con.commit()
        return False
    cols = ", ".join(dados) + ", status, encontrado_em, atualizado_em"
    marcas = ", ".join("?" for _ in dados) + ", 'candidato', ?, ?"
    con.execute(f"INSERT INTO videos ({cols}) VALUES ({marcas})", list(dados.values()) + [_agora(), _agora()])
    con.commit()
    return True


def mudar(con, video_id: str, status: str | None = None, **campos) -> None:
    if status:
        assert status in STATUS, status
        campos["status"] = status
    if status and status != "erro":
        campos.setdefault("erro", None)
    campos["atualizado_em"] = _agora()
    sets = ", ".join(f"{k}=?" for k in campos)
    con.execute(f"UPDATE videos SET {sets} WHERE id=?", list(campos.values()) + [video_id])
    con.commit()


def obter(con, ref: str) -> sqlite3.Row | None:
    """Aceita o nº da pauta (ex.: 12) ou o ID do YouTube."""
    if ref.isdigit():
        linha = con.execute("SELECT * FROM videos WHERE n=?", (int(ref),)).fetchone()
        if linha:
            return linha
    return con.execute("SELECT * FROM videos WHERE id=?", (ref,)).fetchone()


def listar(con, status: str | list | None = None, limite: int | None = None, ordem="nota DESC"):
    sql, args = "SELECT * FROM videos", []
    if status:
        lista = [status] if isinstance(status, str) else list(status)
        sql += f" WHERE status IN ({','.join('?' for _ in lista)})"
        args += lista
    sql += f" ORDER BY {ordem}"
    if limite:
        sql += f" LIMIT {int(limite)}"
    return con.execute(sql, args).fetchall()


def horarios_ocupados(con) -> set[str]:
    return {r[0] for r in con.execute("SELECT agendado_para FROM videos WHERE agendado_para IS NOT NULL")}


def publicacoes(con, video_id: str) -> dict[str, sqlite3.Row]:
    return {r["rede"]: r for r in con.execute("SELECT * FROM publicacoes WHERE video_id=?", (video_id,))}


def registrar_publicacao(con, video_id: str, rede: str, quando: str, estado: str,
                         ref: str | None = None, erro: str | None = None) -> None:
    con.execute("""INSERT INTO publicacoes (video_id, rede, quando, estado, ref, erro, atualizado_em)
                   VALUES (?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(video_id, rede) DO UPDATE SET quando=excluded.quando, estado=excluded.estado,
                   ref=excluded.ref, erro=excluded.erro, atualizado_em=excluded.atualizado_em""",
                (video_id, rede, quando, estado, ref, erro, _agora()))
    con.commit()


def reservar_publicacao(con, video_id: str, rede: str) -> bool:
    """Marca como 'enviando' só se ainda estiver agendada (evita publicar duas vezes)."""
    cur = con.execute("UPDATE publicacoes SET estado='enviando', atualizado_em=? "
                      "WHERE video_id=? AND rede=? AND estado='agendado'", (_agora(), video_id, rede))
    con.commit()
    return cur.rowcount == 1


def publicacoes_vencidas(con, ate_utc: str) -> list[sqlite3.Row]:
    """Agendadas cujo horário já chegou, com os dados do vídeo."""
    return con.execute("""SELECT p.*, v.n, v.saida FROM publicacoes p JOIN videos v ON v.id = p.video_id
                          WHERE p.estado='agendado' AND p.quando <= ? ORDER BY p.quando""", (ate_utc,)).fetchall()


def agenda(con) -> list[sqlite3.Row]:
    return con.execute("""SELECT p.*, v.n, v.titulo FROM publicacoes p JOIN videos v ON v.id = p.video_id
                          WHERE p.estado != 'enviado' OR p.quando >= ? ORDER BY p.quando""",
                       (_agora(),)).fetchall()
