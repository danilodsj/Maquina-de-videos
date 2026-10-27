"""Carrega config.yaml e .env e resolve os caminhos do projeto."""
import json
import os
from pathlib import Path

import yaml
from dotenv import load_dotenv

RAIZ = Path(__file__).resolve().parent.parent
load_dotenv(RAIZ / ".env")


class ErroConfig(Exception):
    """Erro de configuração com mensagem pronta para o usuário."""


def _resolver(caminho: str) -> Path:
    p = Path(os.path.expandvars(os.path.expanduser(caminho)))
    return p if p.is_absolute() else RAIZ / p


def _carregar() -> dict:
    with open(RAIZ / "config.yaml", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    cfg["_dados"] = _resolver(cfg["caminhos"]["dados"])
    cfg["_saida"] = _resolver(cfg["caminhos"]["saida"])
    for p in (cfg["_dados"], cfg["_saida"], cfg["_dados"] / "videos", cfg["_dados"] / "logs"):
        p.mkdir(parents=True, exist_ok=True)
    return cfg


CFG = _carregar()


def env(nome: str, obrigatorio: bool = True) -> str | None:
    valor = (os.environ.get(nome) or "").strip()
    if not valor and obrigatorio:
        raise ErroConfig(
            f"Falta {nome} no arquivo .env (na pasta do projeto). "
            f"Copie .env.example para .env e preencha {nome}."
        )
    return valor or None


def pasta_video(video_id: str) -> Path:
    p = CFG["_dados"] / "videos" / video_id
    p.mkdir(parents=True, exist_ok=True)
    return p


def ler_json(caminho: Path):
    with open(caminho, encoding="utf-8") as f:
        return json.load(f)


def gravar_json(caminho: Path, dados) -> None:
    tmp = caminho.with_suffix(caminho.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(dados, f, ensure_ascii=False, indent=2)
    os.replace(tmp, caminho)
