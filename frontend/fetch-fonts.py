"""Baixa a fonte Inter (Google Fonts) e gera fonts.css local.

Remove a dependência de Google Fonts (pré-requisito da migração desktop).
Uso: uv run python frontend/fetch-fonts.py
"""

import re
import urllib.request
from pathlib import Path

CSS2_URL = (
    "https://fonts.googleapis.com/css2"
    "?family=Inter:wght@400;500;600;700;800&display=swap"
)
USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
)

RAIZ = Path(__file__).resolve().parent
DIR_FONTES = RAIZ / "static" / "fonts" / "inter"
ARQUIVO_CSS = RAIZ / "static" / "css" / "fonts.css"

BLOCO = re.compile(
    r"@font-face\s*\{[^}]*\}", re.DOTALL
)
URL = re.compile(r"src:\s*url\(([^)]+)\)")


def buscar(url: str) -> str:
    return buscar_bytes(url).decode("utf-8")


def buscar_bytes(url: str) -> bytes:
    requisicao = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(requisicao, timeout=30) as resposta:
        return resposta.read()


def principal():
    css_remoto = buscar(CSS2_URL)
    DIR_FONTES.mkdir(parents=True, exist_ok=True)
    baixadas = 0
    blocos = []
    for bloco in BLOCO.findall(css_remoto):
        url_fonte = URL.search(bloco)
        if not url_fonte:
            continue
        url = url_fonte.group(1)
        nome = url.rsplit("/", 1)[-1].split("?")[0]
        destino = DIR_FONTES / nome
        if not destino.exists():
            destino.write_bytes(buscar_bytes(url))
            baixadas += 1
        blocos.append(bloco.replace(url, f"../fonts/inter/{nome}"))
    ARQUIVO_CSS.write_text(
        "/* Gerado por frontend/fetch-fonts.py — não editar manualmente. */\n\n"
        + "\n\n".join(blocos)
        + "\n",
        "utf-8",
    )
    print(f"OK: {baixadas} fontes novas, {len(blocos)} blocos em fonts.css")


if __name__ == "__main__":
    principal()
