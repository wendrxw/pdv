"""Ponto de entrada do Local Print Agent.

Comandos:
    python -m app.main run       # pareia (se preciso) e entra no loop
    python -m app.main pair      # apenas pareia e salva a credencial
    python -m app.main test      # página de teste na impressora (ESC/POS)
    python -m app.main raw-test  # teste em texto puro (printf > /dev/usb/lp0)

Variáveis de ambiente: veja app/config.py e README.md.
"""

import argparse
import logging
import signal
import sys
import time

from .agent import (
    PrintAgent,
    carregar_credencial,
    salvar_credencial,
)
from .client import AuthError, PrintAgentClient, PrintAgentClientError
from .config import Config
from .escpos import EscPosPrinter
from .printer import UsbPrinterDevice

logger = logging.getLogger("print-agent")


def _configurar_log(config):
    logging.basicConfig(
        level=getattr(logging, config.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


def _parear(config, cliente):
    """Pareia usando o código de instalação e salva a credencial."""
    credencial = cliente.pair(config.pair_code)
    salvar_credencial(config, credencial)
    logger.info(
        "Estação '%s' pareada com a loja '%s'.",
        credencial.get("nome"),
        credencial.get("loja"),
    )
    return credencial


def _cliente_autenticado(config):
    """Retorna (cliente, credencial) já autenticados."""
    cliente = PrintAgentClient(config.server_url, timeout=config.http_timeout)
    credencial = carregar_credencial(config)
    if credencial is None:
        if not config.pair_code:
            raise SystemExit(
                "Agente não pareado. Defina PRINT_AGENT_PAIR_CODE e rode "
                "'python -m app.main pair' na primeira instalação."
            )
        credencial = _parear(config, cliente)
    return (
        PrintAgentClient(
            config.server_url,
            estacao_uuid=credencial["estacao"],
            token=credencial["token"],
            timeout=config.http_timeout,
        ),
        credencial,
    )


def comando_pair(config):
    cliente = PrintAgentClient(config.server_url, timeout=config.http_timeout)
    if not config.pair_code:
        raise SystemExit(
            "Informe o código: PRINT_AGENT_PAIR_CODE=ABC123 python -m app.main pair"
        )
    credencial = _parear(config, cliente)
    print(
        f"Pareado! Estação: {credencial.get('nome')} · Loja: {credencial.get('loja')}"
    )


def comando_test(config):
    impressora = UsbPrinterDevice(config.device)
    if not impressora.disponivel():
        raise SystemExit(
            f"Impressora indisponível em {config.device}. "
            "Verifique o cabo e a permissão (grupo lp)."
        )
    linhas = [
        ("=" * 32, "normal"),
        ("PDV — PÁGINA DE TESTE", "central_negrito"),
        ("ÁÉÍÓÚÇ áéíóúç ãõ", "central"),
        ("1234567890 R$ 1.234,56", "central"),
        ("=" * 32, "normal"),
        ("", "normal"),
    ]
    impressora_escpos = EscPosPrinter(
        codepage=config.codepage, cortar_parcial=config.cortar_parcial
    )
    dados = (
        impressora_escpos.render(
            linhas, alimentar_antes_de_cortar=config.alimentacao_final
        )
        if config.escpos
        else ("\n".join(t for t, _ in linhas) + "\n" * config.alimentacao_final).encode(
            "utf-8"
        )
    )
    impressora.escrever(dados)
    print("Página de teste enviada para", config.device)


def comando_raw_test(config):
    """Diagnóstico no modo mais simples possível: texto puro.

    Equivalente ao comando que valida a impressora em Linux:

        printf "TESTE SEM SUDO\\n\\n\\n" > /dev/usb/lp0

    Sem nenhum comando ESC/POS — serve para impressoras com firmware
    caprichoso (ex.: Tomate MDK-080, driver oficial só para Windows).
    """
    impressora = UsbPrinterDevice(config.device)
    if not impressora.disponivel():
        raise SystemExit(
            f"Impressora indisponível em {config.device}. "
            "Verifique o cabo e a permissão (grupo lp)."
        )
    impressora.escrever(b"TESTE SEM SUDO\n\n\n")
    print(f"'TESTE SEM SUDO' enviado direto para {config.device}")


def comando_run(config):
    _configurar_log(config)
    cliente, credencial = _cliente_autenticado(config)
    impressora = UsbPrinterDevice(config.device)
    agente = PrintAgent(config, cliente, impressora, logger=logger)
    logger.info(
        "Agente iniciado: estação '%s' · loja '%s' · impressora %s",
        credencial.get("nome"),
        credencial.get("loja"),
        config.device,
    )

    parando = {"ativo": False}

    def _parar(signum, _frame):
        logger.info("Sinal %s recebido; encerrando.", signum)
        parando["ativo"] = True

    signal.signal(signal.SIGTERM, _parar)
    signal.signal(signal.SIGINT, _parar)

    while not parando["ativo"]:
        try:
            agente.ciclo()
            falhas = 0
        except AuthError as exc:
            logger.error("Credencial recusada pelo servidor: %s", exc)
            logger.error(
                "Rode 'python -m app.main pair' com um novo código de pareamento."
            )
            return 1
        except PrintAgentClientError as exc:
            falhas += 1
            espera = min(60, 5 * (2 ** min(falhas, 4)))
            logger.warning("Servidor indisponível: %s; tentando em %ss.", exc, espera)
            time.sleep(espera)
            continue
        time.sleep(config.poll_interval)
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(prog="print-agent")
    parser.add_argument(
        "comando",
        nargs="?",
        default="run",
        choices=["run", "pair", "test", "raw-test"],
    )
    argumentos = parser.parse_args(argv)
    config = Config.from_env()
    _configurar_log(config)

    if argumentos.comando == "pair":
        comando_pair(config)
        return 0
    if argumentos.comando == "test":
        comando_test(config)
        return 0
    if argumentos.comando == "raw-test":
        comando_raw_test(config)
        return 0
    return comando_run(config)


if __name__ == "__main__":
    sys.exit(main())
