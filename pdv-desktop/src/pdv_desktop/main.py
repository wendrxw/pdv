"""Bootstrap do shell desktop.

Fase 1 implementa a janela PyWebview e o carregamento do app. Nesta fase o
entry point responde `--version`/`--help` e prepara o diretório de estado.
"""

import argparse
import sys

from pdv_desktop import __version__
from pdv_desktop.config import DIR_ESTADO, carregar


def montar_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="pdv-desktop",
        description="Shell desktop do PDV (cliente rico do sistema Django).",
    )
    parser.add_argument(
        "--version", action="version", version=f"%(prog)s {__version__}"
    )
    return parser


def main(argv=None) -> int:
    args = montar_parser().parse_args(argv)
    del args
    DIR_ESTADO.mkdir(parents=True, exist_ok=True)
    config = carregar()
    # Fase 1: criar a janela PyWebview apontando para config.server_url.
    print(f"pdv-desktop {__version__} — servidor: {config.server_url}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
