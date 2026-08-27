#!/bin/sh
# Backup dos arquivos de configuração críticos ANTES de qualquer mudança.
# Uso (como root): sh deploy/backup-configs.sh
# Guarda tudo em /root/backups-pdv-<timestamp> e imprime o caminho.

set -eu

TIMESTAMP=$(date +%Y%m%d-%H%M%S)
DEST="/root/backups-pdv-$TIMESTAMP"
mkdir -p "$DEST"

for CAMINHO in /etc/nginx /etc/cloudflared /etc/systemd/system; do
    if [ -e "$CAMINHO" ]; then
        cp -a "$CAMINHO" "$DEST/$(basename "$CAMINHO")"
    fi
done

# Estado atual dos serviços para conferência pós-mudança
{
    echo "=== systemctl (running) ==="
    systemctl list-units --type=service --state=running --no-pager
    echo
    echo "=== portas (ss -lntp) ==="
    ss -lntp
} > "$DEST/servicos-antigos.txt"

echo "Backup criado em: $DEST"
