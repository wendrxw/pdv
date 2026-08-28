"""Launcher para o executável (PyInstaller).

O PyInstaller não preserva o contexto de pacote quando o entry point é
`app/main.py` (imports relativos falham com "attempt relative import").
Este arquivo na raiz importa o pacote `app` normalmente — é este o entry
point usado no build do print-agent.exe.
"""

import sys

from app.main import main

if __name__ == "__main__":
    sys.exit(main())
