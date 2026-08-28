"""Ponto de entrada do Local Print Agent.

Comandos:
    python -m app.main run            # pareia (se preciso) e entra no loop
    python -m app.main pair           # apenas pareia e salva a credencial
    python -m app.main test           # página de teste (ESC/POS ou texto)
    python -m app.main raw-test       # teste em texto puro (printf > /dev/usb/lp0)
    python -m app.main codepage-test  # amostra em várias codificações (acentos)
    python -m app.main label-test     # etiqueta de calibração (Elgin L42 Pro)

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
from .escpos import (
    CODEPAGEM_PARA_ENCODING,
    EscPosPrinter,
    normalizar_texto,
    selecionar_codepage,
)
from .labels import gerar_epl2_calibracao
from .printer import criar_dispositivo

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


def _erro_pareamento_amigavel(exc):
    """Mensagem curta e em português para falhas no pareamento."""
    texto = str(exc)
    sugestoes = {
        "inválido": "O código está errado ou já foi usado. Gere um novo código "
        "em Impressão → Estações e tente novamente.",
        "Muitas tentativas": "Muitas tentativas. Aguarde alguns minutos e "
        "tente novamente.",
    }
    for trecho, sugestao in sugestoes.items():
        if trecho.lower() in texto.lower():
            return f"{texto}\n{sugestao}"
    if "Falha de rede" in texto:
        return (
            f"{texto}\nVerifique se o servidor está correto "
            "(ex.: https://pdv.wendrxw.online) e se há internet."
        )
    return texto


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
    try:
        credencial = _parear(config, cliente)
    except (AuthError, PrintAgentClientError) as exc:
        print("NÃO FOI POSSÍVEL PAREAR:", _erro_pareamento_amigavel(exc))
        return 1
    print(
        f"Pareado! Estação: {credencial.get('nome')} · Loja: {credencial.get('loja')}"
    )
    return 0


def _impressora(config, dispositivo=None):
    """Dispositivo da plataforma (USB no Linux, nome da impressora no
    Windows) — ou fake injetado nos testes."""
    impressora = dispositivo or criar_dispositivo(config.device)
    if not impressora.disponivel():
        raise SystemExit(
            f"Impressora indisponível: {config.device}. "
            "No Windows confira o nome em 'Painel de Controle → "
            "Dispositivos e Impressoras'; no Linux o cabo e o grupo lp."
        )
    return impressora


def montar_pagina_teste(config):
    """Bytes da página de teste (acentos + corte) no modo configurado."""
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
    if config.escpos:
        return impressora_escpos.render(
            linhas, alimentar_antes_de_cortar=config.alimentacao_final
        )
    encoding = CODEPAGEM_PARA_ENCODING.get(config.codepage, "utf-8")
    dados = "\n".join(t for t, _ in linhas) + "\n" * config.alimentacao_final
    dados = normalizar_texto(dados).encode(encoding, errors="replace")
    if config.selecionar_codepage:
        dados = selecionar_codepage(config.codepage) + dados
    return dados


def comando_test(config, dispositivo=None):
    impressora = _impressora(config, dispositivo)
    impressora.escrever(montar_pagina_teste(config))
    print("Página de teste enviada para", config.device)


def montar_pagina_codepage(config):
    """Página física com a mesma amostra em várias codificações.

    Cada linha é precedida do comando de seleção da tabela (ESC t n). O
    operador olha o papel e informa qual linha saiu correta para definir
    PRINTER_CODEPAGE.
    """
    amostra = "ÁÉÍÓÚÇ ÃÕ áéíóúç ãõ — Café 500ml"
    candidatas = [
        ("UTF-8 (padrao)", "utf8"),
        ("CP850", "cp850"),
        ("CP860 (portugues)", "cp860"),
        ("CP1252 (Windows)", "cp1252"),
    ]
    blocos = bytearray()
    blocos += b"TESTE DE CODIFICACAO\n"
    blocos += b"============================\n"
    for rotulo, codepage in candidatas:
        blocos += f"{rotulo}:\n".encode("ascii")
        encoding = CODEPAGEM_PARA_ENCODING.get(codepage, "utf-8")
        blocos += selecionar_codepage(codepage)
        blocos += normalizar_texto(amostra).encode(encoding, errors="replace")
        blocos += b"\n\n"
    blocos += b"============================\n"
    blocos += b"\n" * config.alimentacao_final
    return bytes(blocos)


def comando_codepage_test(config, dispositivo=None):
    impressora = _impressora(config, dispositivo)
    impressora.escrever(montar_pagina_codepage(config))
    print("Página de teste de codificação enviada para", config.device)
    print("Veja no papel qual linha saiu correta e defina PRINTER_CODEPAGE:")
    print("  UTF-8 -> utf8 | CP850 -> cp850 | CP860 -> cp860 | CP1252 -> cp1252")


def comando_label_test(config, dispositivo=None):
    """Imprime uma etiqueta de calibração direto na Elgin L42 Pro.

    Valida moldura, posicionamento e código de barras sem depender do
    servidor. Usa PRINTER_LABEL_DEVICE + PRINTER_LABEL_DPI (203).
    """
    if not config.label_device:
        raise SystemExit(
            "Defina PRINTER_LABEL_DEVICE (ex.: /dev/usb/lp1) para usar "
            "o teste de etiquetas."
        )
    impressora = _impressora_etiquetas(config, dispositivo)
    payload = {
        "tipo": "calibracao",
        "dimensoes": {
            "largura_etiqueta": "40",
            "altura_etiqueta": "30",
            "gap_horizontal": "2",
            "gap_vertical": "2",
            "margem_esquerda": "2",
            "margem_superior": "1",
            "offset_horizontal": "0",
            "offset_vertical": "0",
            "dpi": config.label_dpi,
        },
    }
    impressora.escrever(gerar_epl2_calibracao(payload))
    print(
        f"Etiqueta de calibração enviada para {config.label_device} "
        f"({config.label_dpi} DPI, {config.label_linguagem.upper()})"
    )


def _impressora_etiquetas(config, dispositivo=None):
    impressora = dispositivo or criar_dispositivo(config.label_device)
    if not impressora.disponivel():
        raise SystemExit(
            f"Impressora de etiquetas indisponível: {config.label_device}. "
            "No Windows confira o nome em 'Painel de Controle → "
            "Dispositivos e Impressoras'; no Linux o cabo e o grupo lp."
        )
    return impressora


def comando_raw_test(config):
    """Diagnóstico no modo mais simples possível: texto puro.

    Equivalente ao comando que valida a impressora em Linux:

        printf "TESTE SEM SUDO\\n\\n\\n" > /dev/usb/lp0

    Sem nenhum comando ESC/POS — serve para impressoras com firmware
    caprichoso (ex.: Tomate MDK-080, driver oficial só para Windows).
    """
    impressora = criar_dispositivo(config.device)
    if not impressora.disponivel():
        raise SystemExit(
            f"Impressora indisponível: {config.device}. "
            "Verifique o cabo e o nome da impressora."
        )
    impressora.escrever(b"TESTE SEM SUDO\n\n\n")
    print(f"'TESTE SEM SUDO' enviado direto para {config.device}")


# ---------------------------------------------------------------------------
# Autogestão no Windows (sem administrador)
# ---------------------------------------------------------------------------


def comando_instalar_autostart(config):
    """Registra o agente para iniciar com o Windows (HKCU, sem admin)."""
    import sys as _sys

    if _sys.platform != "win32":
        raise SystemExit("Autostart automático é suportado apenas no Windows.")
    import winreg

    comando = _comando_autostart()
    chave = winreg.CreateKey(
        winreg.HKEY_CURRENT_USER,
        r"Software\Microsoft\Windows\CurrentVersion\Run",
    )
    winreg.SetValueEx(chave, "PDV-Print-Agent", 0, winreg.REG_SZ, comando)
    winreg.CloseKey(chave)
    print("Agente configurado para iniciar com o Windows:")
    print(f"  {comando}")


def comando_remover_autostart(config):
    """Remove o registro de inicialização automática (HKCU)."""
    import sys as _sys

    if _sys.platform != "win32":
        raise SystemExit("Autostart automático é suportado apenas no Windows.")
    import winreg

    chave = winreg.CreateKey(
        winreg.HKEY_CURRENT_USER,
        r"Software\Microsoft\Windows\CurrentVersion\Run",
    )
    try:
        winreg.DeleteValue(chave, "PDV-Print-Agent")
        print("Inicialização automática removida.")
    except FileNotFoundError:
        print("Inicialização automática não estava registrada.")
    winreg.CloseKey(chave)


def _comando_autostart():
    """Linha de comando executada na inicialização do Windows."""
    import sys as _sys

    if getattr(_sys, "frozen", False):
        return f'"{_sys.executable}" run'
    return f'"{_sys.executable}" -m app.main run'


def _listar_impressoras_windows():
    """Nomes das impressoras locais (win32print) ou lista vazia."""
    import sys as _sys

    if _sys.platform != "win32":
        return []
    try:
        import win32print
    except ImportError:
        return []
    impressoras = []
    try:
        for _flags, nome, _descricao, _comentario in win32print.EnumPrinters(
            win32print.PRINTER_ENUM_LOCAL, None, 1
        ):
            impressoras.append(nome)
    except Exception:
        return []
    return impressoras


def _escolher_impressora(rotulo, config, chave, obrigatoria=True):
    """Configura interativa: escolhe a impressora da lista do Windows."""
    impressoras = _listar_impressoras_windows()
    atual = getattr(config, chave, "") or ""
    if impressoras:
        print(f"\n{rotulo}:")
        for indice, nome in enumerate(impressoras, start=1):
            marca = " (atual)" if nome == atual else ""
            print(f"  [{indice}] {nome}{marca}")
        if not obrigatoria:
            print("  [0] Nenhuma (não usar)")
        padrao = impressoras.index(atual) + 1 if atual in impressoras else None
        while True:
            entrada = input(
                f"Escolha o número"
                f"{f' [{padrao}]' if padrao else ''}: "
            ).strip()
            if not entrada and padrao:
                escolha = padrao
            elif entrada.isdigit() and 0 <= int(entrada) <= len(impressoras):
                escolha = int(entrada)
            else:
                print("Opção inválida.")
                continue
            if escolha == 0:
                setattr(config, chave, "")
            else:
                setattr(config, chave, impressoras[escolha - 1])
            break
    else:
        if obrigatoria:
            setattr(
                config,
                chave,
                input(f"{rotulo} (nome/dispositivo): ").strip() or atual,
            )
        else:
            setattr(
                config,
                chave,
                input(f"{rotulo} (vazio para desativar): ").strip() or atual,
            )


def _configuracao_interativa(config, precisa_parear=False):
    """Primeiro uso: servidor, código de pareamento e impressoras.

    Roda apenas em terminal interativo (TTY); salva tudo em
    config.json para nunca mais perguntar.
    """
    if not sys.stdin.isatty():
        return config, precisa_parear
    print("\n=== Configuração inicial do PDV Print Agent ===\n")
    config.server_url = (
        input(f"Servidor [{config.server_url}]: ").strip() or config.server_url
    ).rstrip("/")
    if precisa_parear:
        codigo = input("Código de pareamento (PDV → Impressão → Estações): ").strip()
        config.pair_code = codigo or None
    # Impressoras: escolha automática no Windows, digitação no Linux.
    if not config.device:
        _escolher_impressora("Impressora de comprovantes", config, "device")
    if not config.label_device:
        _escolher_impressora(
            "Impressora de etiquetas (Elgin L42 Pro)",
            config,
            "label_device",
            obrigatoria=False,
        )
    config.salvar_local()
    print("\nConfiguração salva em", config.caminho_config_local)
    return config, precisa_parear


def comando_run(config):
    _configurar_log(config)
    precisa_parear = carregar_credencial(config) is None and not config.pair_code
    precisa_configurar = precisa_parear or not config.device or not config.label_device
    if precisa_configurar and sys.stdin.isatty():
        config, precisa_parear = _configuracao_interativa(config, precisa_parear)
    try:
        cliente, credencial = _cliente_autenticado(config)
    except (AuthError, PrintAgentClientError) as exc:
        logger.error("NÃO FOI POSSÍVEL PAREAR: %s", _erro_pareamento_amigavel(exc))
        print("NÃO FOI POSSÍVEL PAREAR:", _erro_pareamento_amigavel(exc))
        return 1
    impressora = criar_dispositivo(config.device)
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
        choices=[
            "run",
            "pair",
            "test",
            "raw-test",
            "codepage-test",
            "label-test",
            "instalar-autostart",
            "remover-autostart",
        ],
    )
    argumentos = parser.parse_args(argv)
    config = Config.from_env()
    config = Config.carregar_local(config)
    _configurar_log(config)

    if argumentos.comando == "pair":
        return comando_pair(config)
    if argumentos.comando == "test":
        comando_test(config)
        return 0
    if argumentos.comando == "raw-test":
        comando_raw_test(config)
        return 0
    if argumentos.comando == "codepage-test":
        comando_codepage_test(config)
        return 0
    if argumentos.comando == "label-test":
        comando_label_test(config)
        return 0
    if argumentos.comando == "instalar-autostart":
        comando_instalar_autostart(config)
        return 0
    if argumentos.comando == "remover-autostart":
        comando_remover_autostart(config)
        return 0
    return comando_run(config)


if __name__ == "__main__":
    sys.exit(main())
