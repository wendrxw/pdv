"""Configuração do shell desktop.

Prioridade: variáveis de ambiente `PDV_DESKTOP_*` > `~/.pdv-desktop/config.json`.
O arquivo de estado é gravado com permissão 600 (pode conter URL do servidor
e preferências da loja — nunca tokens; a credencial da estação de impressão
continua no diretório do print-agent, com 0600).
"""

import json
import os
from dataclasses import asdict, dataclass, fields
from pathlib import Path

APP_NAME = "pdv-desktop"
DIR_ESTADO = Path(
    os.environ.get("PDV_DESKTOP_DIR", str(Path.home() / f".{APP_NAME}"))
)
CAMINHO_CONFIG = DIR_ESTADO / "config.json"

SERVIDOR_PADRAO = "https://pdv.wendrxw.online"


def _bool(texto):
    return texto.strip().lower() in ("1", "true", "sim", "yes", "on")


@dataclass
class Config:
    """Preferências do shell. Campos novos entram aqui com default seguro."""

    server_url: str = SERVIDOR_PADRAO
    janela_largura: int = 1280
    janela_altura: int = 800
    janela_min_largura: int = 1024
    janela_min_altura: int = 700
    lembrar_sessao: bool = False


def carregar(caminho: Path | None = None) -> Config:
    """Lê config.json (se existir) e aplica overrides de ambiente."""
    caminho = caminho or CAMINHO_CONFIG
    dados: dict = {}
    if caminho.exists():
        dados = json.loads(caminho.read_text("utf-8"))
    valores = {}
    for campo in fields(Config):
        env = os.environ.get(f"PDV_DESKTOP_{campo.name.upper()}")
        if env is not None:
            valores[campo.name] = (
                _bool(env) if campo.type is bool else campo.type(env)
            )
        elif campo.name in dados:
            valores[campo.name] = dados[campo.name]
    return Config(**valores)


def salvar(config: Config, caminho: Path | None = None) -> None:
    """Grava config.json com permissão 600."""
    caminho = caminho or CAMINHO_CONFIG
    caminho.parent.mkdir(parents=True, exist_ok=True)
    caminho.write_text(
        json.dumps(asdict(config), indent=2, ensure_ascii=False), "utf-8"
    )
    os.chmod(caminho, 0o600)
