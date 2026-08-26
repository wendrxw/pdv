#!/bin/sh
# Instalador do Local Print Agent (Void Linux / runit).
#
# Uso (na máquina da loja):
#   sudo sh instalar.sh
#
# Copia o código para /opt/print-agent, instala o serviço runit em
# /etc/sv/print-agent (com log via svlogd) e ativa em /var/service/.
# Depois: edite /etc/sv/print-agent/conf (URL do servidor, dispositivo,
# codepage) e pareie (veja o README.md).

set -e

AGENT_ROOT=$(cd "$(dirname "$0")/../.." && pwd)
DEST_DIR=/opt/print-agent
SV_DIR=/etc/sv/print-agent

if [ ! -d "$AGENT_ROOT/app" ]; then
    echo "ERRO: app/ não encontrado em $AGENT_ROOT" >&2
    exit 1
fi

echo "==> Copiando código para $DEST_DIR"
mkdir -p "$DEST_DIR"
cp -r "$AGENT_ROOT/app" "$DEST_DIR/app"

echo "==> Instalando serviço runit em $SV_DIR"
mkdir -p "$SV_DIR/log"
cp "$AGENT_ROOT/deploy/print-agent/run" "$SV_DIR/run"
chmod +x "$SV_DIR/run"
if [ ! -f "$SV_DIR/conf" ]; then
    cp "$AGENT_ROOT/deploy/print-agent/conf" "$SV_DIR/conf"
fi
cp "$AGENT_ROOT/deploy/print-agent/log-run" "$SV_DIR/log/run"
chmod +x "$SV_DIR/log/run"
mkdir -p /var/log/print-agent

echo "==> Ativando serviço (/var/service/print-agent)"
[ -e /var/service/print-agent ] || ln -s "$SV_DIR" /var/service/print-agent

echo
echo "Próximo passo:"
echo "  1. Edite $SV_DIR/conf (PRINT_AGENT_SERVER_URL, PRINTER_DEVICE,"
echo "     PRINTER_CODEPAGE, PRINTER_ESCPOS)."
echo "  2. Pareie: PRINT_AGENT_SERVER_URL=... PRINT_AGENT_PAIR_CODE=ABC123 \\"
echo "       python3 -m app.main pair   (código gerado no PDV → Estações)"
echo "  3. Confira: sv status print-agent"
