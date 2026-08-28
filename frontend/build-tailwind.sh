#!/usr/bin/env bash
# Compila o CSS do Tailwind (v3.4.17) para servir estaticamente.
# Remove a dependência do Play CDN (pré-requisito da migração desktop).
# Requer rede apenas na primeira execução (download do CLI standalone).
set -euo pipefail

VERSAO="v3.4.17"
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FERRAMENTAS="$DIR/.tools"
CLI="$FERRAMENTAS/tailwindcss"
CSS="$DIR/static/css"

mkdir -p "$FERRAMENTAS"
if [[ ! -x "$CLI" ]]; then
    echo "Baixando tailwindcss standalone $VERSAO..."
    curl -fsSL \
        "https://github.com/tailwindlabs/tailwindcss/releases/download/${VERSAO}/tailwindcss-linux-x64" \
        -o "$CLI"
    chmod +x "$CLI"
fi

cd "$CSS"
"$CLI" -c "$CSS/tailwind.config.js" -i "$CSS/input.css" -o "$CSS/tailwind.css" --minify
echo "OK: frontend/static/css/tailwind.css"
