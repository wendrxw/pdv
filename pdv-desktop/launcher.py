"""Launcher para o executável (PyInstaller).

O PyInstaller não preserva o layout `src/` quando o entry point é o pacote
direto. Este arquivo na raiz ajusta o `sys.path` em desenvolvimento e importa
`pdv_desktop` normalmente — é o entry point usado no build do pdv-desktop.
"""

import os
import sys

if getattr(sys, "frozen", False):
    # PyInstaller: módulos já estão embutidos no bundle.
    from pdv_desktop.main import main  # noqa: E402
else:
    SRC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "src")
    if SRC not in sys.path:
        sys.path.insert(0, SRC)
    from pdv_desktop.main import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
