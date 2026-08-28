"""Configuração do Local Print Agent via variáveis de ambiente e
configuração local persistente.

Nada de segredo no código: URL do servidor, dispositivo da impressora e
credenciais vêm do ambiente ou da configuração local (estado do usuário).
A configuração local (state_dir/config.json) é criada pela configuração
interativa do primeiro uso e tem PRIORIDADE sobre os padrões do ambiente
— permite operação sem mexer em variáveis de sistema.
"""

import json
import os
from pathlib import Path


def _env(key, default=None):
    return os.environ.get(key, default)


def _env_int(key, default):
    try:
        return int(_env(key, str(default)))
    except (TypeError, ValueError):
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
        label_device="",
        label_dpi=203,
        label_linguagem="epl2",
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
        # Impressora de ETIQUETAS (Elgin L42 Pro Full, EPL2). Vazio
        # desativa o suporte a etiquetas nesta estação.
        self.label_device = label_device
        self.label_dpi = label_dpi
        self.label_linguagem = label_linguagem
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
            label_device=_env("PRINTER_LABEL_DEVICE") or "",
            label_dpi=_env_int("PRINTER_LABEL_DPI", 203),
            label_linguagem=_env("PRINTER_LABEL_LINGUAGEM", "epl2"),
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

    @property
    def caminho_config_local(self):
        return self.state_dir / "config.json"

    def aplicar(self, dados: dict):
        """Aplica valores da configuração local (somente os presentes)."""
        for chave in (
            "server_url",
            "device",
            "label_device",
            "largura_padrao",
            "codepage",
            "escpos",
            "cortar_parcial",
            "selecionar_codepage",
            "alimentacao_final",
            "label_dpi",
            "label_linguagem",
            "poll_interval",
            "http_timeout",
            "log_level",
            "estacao_nome",
        ):
            if chave in dados and dados[chave] not in (None, ""):
                setattr(self, chave, dados[chave])

    def salvar_local(self):
        """Persiste a configuração interativa (sem credenciais)."""
        self.state_dir.mkdir(parents=True, exist_ok=True)
        dados = {
            "server_url": self.server_url,
            "device": self.device,
            "label_device": self.label_device,
            "largura_padrao": self.largura_padrao,
            "codepage": self.codepage,
            "escpos": self.escpos,
            "cortar_parcial": self.cortar_parcial,
            "selecionar_codepage": self.selecionar_codepage,
            "alimentacao_final": self.alimentacao_final,
            "label_dpi": self.label_dpi,
            "label_linguagem": self.label_linguagem,
            "poll_interval": self.poll_interval,
            "http_timeout": self.http_timeout,
            "log_level": self.log_level,
            "estacao_nome": self.estacao_nome,
        }
        self.caminho_config_local.write_text(
            json.dumps(dados, ensure_ascii=False, indent=2), "utf-8"
        )

    @classmethod
    def carregar_local(cls, config):
        """Sobrepõe a configuração local salva (se existir)."""
        try:
            dados = json.loads(config.caminho_config_local.read_text("utf-8"))
        except (OSError, ValueError, json.JSONDecodeError):
            return config
        config.aplicar(dados)
        return config
