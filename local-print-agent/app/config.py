"""Configuração do Local Print Agent via variáveis de ambiente.

Nada de segredo no código: URL do servidor, dispositivo da impressora e
credenciais vêm do ambiente (ou do arquivo de estado local, para o token).
"""

import os
from pathlib import Path


def _env(key, default=None):
    return os.environ.get(key, default)


def _env_int(key, default):
    try:
        return int(_env(key, str(default)))
    except TypeError, ValueError:
        return default


class Config:
    """Parâmetros do agente (todos com padrões seguros)."""

    def __init__(
        self,
        server_url,
        device="/dev/usb/lp0",
        pair_code=None,
        largura_padrao="58",
        codepage="utf8",
        escpos=True,
        cortar_parcial=True,
        selecionar_codepage=True,
        alimentacao_final=8,
        poll_interval=3,
        http_timeout=30,
        state_dir=None,
        log_level="INFO",
        estacao_nome=None,
    ):
        self.server_url = server_url.rstrip("/")
        self.device = device
        self.pair_code = pair_code
        self.largura_padrao = largura_padrao
        self.codepage = codepage
        self.escpos = escpos
        self.cortar_parcial = cortar_parcial
        # Envia ESC t n no início (mesmo em modo texto) para o firmware
        # interpretar os acentos na tabela escolhida.
        self.selecionar_codepage = selecionar_codepage
        # Linhas em branco no fim do comprovante: o corte (guilhotina ou
        # rasgo manual) precisa de folga para não cair sobre o conteúdo.
        self.alimentacao_final = alimentacao_final
        self.poll_interval = poll_interval
        self.http_timeout = http_timeout
        self.state_dir = Path(state_dir or "~/.print-agent").expanduser()
        self.log_level = log_level
        self.estacao_nome = estacao_nome

    @classmethod
    def from_env(cls):
        """Lê as variáveis de ambiente (PRINT_AGENT_*)."""
        return cls(
            server_url=_env("PRINT_AGENT_SERVER_URL", "http://127.0.0.1:8000"),
            device=_env("PRINTER_DEVICE", "/dev/usb/lp0"),
            pair_code=_env("PRINT_AGENT_PAIR_CODE") or None,
            largura_padrao=_env("PRINT_AGENT_LARGURA_PADRAO", "58"),
            codepage=_env("PRINTER_CODEPAGE", "utf8"),
            escpos=_env("PRINTER_ESCPOS", "1").lower()
            not in {"0", "false", "no", "off"},
            cortar_parcial=_env("PRINTER_CORTE_PARCIAL", "1").lower()
            not in {"0", "false", "no", "off"},
            selecionar_codepage=_env("PRINTER_SELECIONAR_CODEPAGE", "1").lower()
            not in {"0", "false", "no", "off"},
            alimentacao_final=_env_int("PRINTER_ALIMENTACAO_FINAL", 8),
            poll_interval=_env_int("PRINT_AGENT_POLL_INTERVAL", 3),
            http_timeout=_env_int("PRINT_AGENT_HTTP_TIMEOUT", 30),
            state_dir=_env("PRINT_AGENT_STATE_DIR"),
            log_level=_env("PRINT_AGENT_LOG_LEVEL", "INFO"),
            estacao_nome=_env("PRINT_AGENT_ESTACAO_NOME"),
        )

    @property
    def caminho_credencial(self):
        return self.state_dir / "credencial.json"

    @property
    def caminho_processados(self):
        return self.state_dir / "processados.jsonl"
