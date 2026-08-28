#!/bin/sh
# =============================================================================
# setup-pdv.sh — implanta o PDV em produção (Debian)
#
# Topologia: Cloudflare Tunnel → Nginx (:80) → gunicorn (127.0.0.1:8001) → Django
# Domínio padrão: pdv.wendrxw.online
#
# Uso:
#   sudo sh deploy/setup-pdv.sh                     # deploy completo
#   sudo sh deploy/setup-pdv.sh --skip-cloudflared  # sem mexer no túnel
#   sudo sh deploy/setup-pdv.sh --port 8005         # porta própria do PDV
#
# Segurança:
#   - Nunca sobrescreve configurações de outros sites sem backup;
#   - valida nginx -t antes de recarregar;
#   - não cria/reinicia o Cloudflare Tunnel existente sem confirmação;
#   - roda o gunicorn como usuário 'pdv' sem privilégios;
#   - SECRET_KEY e senhas geradas localmente, nunca no git.
# =============================================================================
set -eu

DOMAIN="pdv.wendrxw.online"
APP_DIR="/opt/pdv"
APP_USER="pdv"
PDV_PORT="8001"
SKIP_CLOUDFLARED=0
REPO_URL=""

for ARG in "$@"; do
    case "$ARG" in
        --skip-cloudflared) SKIP_CLOUDFLARED=1 ;;
        --port=*) PDV_PORT="${ARG#--port=}" ;;
        --repo=*) REPO_URL="${ARG#--repo=}" ;;
        *) echo "Argumento desconhecido: $ARG" >&2; exit 1 ;;
    esac
done

if [ "$(id -u)" -ne 0 ]; then
    echo "Execute como root (sudo)." >&2
    exit 1
fi

echo "=============================================================================="
echo " ETAPA 0 — Auditoria do servidor (não modificar nada antes de entender)"
echo "=============================================================================="
echo "--- Serviços rodando ---"
systemctl list-units --type=service --state=running --no-pager || true
echo
echo "--- Portas em uso ---"
ss -lntp || true
echo
echo "--- Sítios Nginx existentes ---"
ls -1 /etc/nginx/sites-enabled/ 2>/dev/null || true
echo
echo "--- Túneis Cloudflare existentes ---"
if command -v cloudflared >/dev/null 2>&1; then
    cloudflared tunnel list 2>/dev/null || echo "(sem túneis listáveis / não autenticado)"
else
    echo "(cloudflared não instalado)"
fi
echo
echo "PDV usará a porta 127.0.0.1:$PDV_PORT (gunicorn)."
if ss -lntp | grep -q "127.0.0.1:$PDV_PORT"; then
    echo "ERRO: a porta $PDV_PORT já está em uso. Escolha outra com --port=N." >&2
    exit 1
fi

echo
echo "=============================================================================="
echo " ETAPA 1 — Backup das configurações críticas"
echo "=============================================================================="
BACKUP_DIR="/root/backups-pdv-$(date +%Y%m%d-%H%M%S)"
mkdir -p "$BACKUP_DIR"
for CAMINHO in /etc/nginx /etc/cloudflared /etc/systemd/system; do
    if [ -e "$CAMINHO" ]; then
        cp -a "$CAMINHO" "$BACKUP_DIR/$(basename "$CAMINHO")"
    fi
done
echo "Backup em: $BACKUP_DIR"

echo
echo "=============================================================================="
echo " ETAPA 2 — Pacotes e usuário da aplicação"
echo "=============================================================================="
if ! command -v apt-get >/dev/null 2>&1; then
    echo "ERRO: este script é para Debian/Ubuntu (apt)." >&2
    exit 1
fi
apt-get update
DEBIAN_FRONTEND=noninteractive apt-get install -y nginx postgresql postgresql-contrib curl git ca-certificates

if ! command -v uv >/dev/null 2>&1; then
    echo "Instalando uv (gerencia o Python 3.14 e as dependências)..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
    # shellcheck disable=SC1091
    . "$HOME/.local/bin/env" 2>/dev/null || true
    UV_BIN="$HOME/.local/bin/uv"
else
    UV_BIN="$(command -v uv)"
fi

if ! id "$APP_USER" >/dev/null 2>&1; then
    useradd --system --home "$APP_DIR" --shell /usr/sbin/nologin "$APP_USER"
fi
mkdir -p "$APP_DIR" "$APP_DIR/media" "$APP_DIR/staticfiles" "$APP_DIR/.django-cache"
chown -R "$APP_USER:$APP_USER" "$APP_DIR"

echo
echo "=============================================================================="
echo " ETAPA 3 — Código e dependências"
echo "=============================================================================="
if [ -n "$REPO_URL" ]; then
    if [ -d "$APP_DIR/.git" ]; then
        echo "Repositório já existe em $APP_DIR — atualizando para a main..."
        (cd "$APP_DIR" && git fetch origin && git checkout main && git pull --ff-only origin main)
    else
        git clone "$REPO_URL" "$APP_DIR"
        (cd "$APP_DIR" && git checkout main)
    fi
elif [ ! -d "$APP_DIR/manage.py" ] && [ ! -f "$APP_DIR/manage.py" ]; then
    echo "ERRO: informe --repo=https://github.com/<conta>/pdv.git ou copie o código para $APP_DIR." >&2
    exit 1
fi
chown -R "$APP_USER:$APP_USER" "$APP_DIR"

(cd "$APP_DIR" && "$UV_BIN" sync --frozen)

echo
echo "=============================================================================="
echo " ETAPA 4 — Variáveis de ambiente ($APP_DIR/.env)"
echo "=============================================================================="
if [ -f "$APP_DIR/.env" ]; then
    echo "$APP_DIR/.env já existe — mantendo (não sobrescrever segredos)."
else
    SECRET_KEY=$("$APP_DIR/.venv/bin/python" -c "import secrets; print(secrets.token_urlsafe(64))")
    DB_PASSWORD=$(tr -dc 'A-Za-z0-9' < /dev/urandom | head -c 32)
    cat > "$APP_DIR/.env" <<EOF
# Gerado por deploy/setup-pdv.sh em $(date)
DJANGO_SECRET_KEY=$SECRET_KEY
DJANGO_DEBUG=False
DJANGO_ALLOWED_HOSTS=$DOMAIN
DJANGO_CSRF_TRUSTED_ORIGINS=https://$DOMAIN

PDV_DB_ENGINE=postgres
PDV_DB_NAME=pdv
PDV_DB_USER=pdv
PDV_DB_PASSWORD=$DB_PASSWORD
PDV_DB_HOST=127.0.0.1
PDV_DB_PORT=5432

PDV_BEHIND_PROXY=True
DJANGO_SECURE_SSL_REDIRECT=True
DJANGO_HSTS_SECONDS=31536000

PDV_CACHE_BACKEND=file
PDV_CACHE_DIR=$APP_DIR/.django-cache

PDV_MEDIA_ROOT=$APP_DIR/media

PDV_PORT=$PDV_PORT

SEFAZ_UF=SP
SEFAZ_AMBIENTE=HOMOLOGACAO
EOF
    chmod 600 "$APP_DIR/.env"
    chown "$APP_USER:$APP_USER" "$APP_DIR/.env"
    echo ".env criado com SECRET_KEY e senha do banco gerados."
fi

echo
echo "=============================================================================="
echo " ETAPA 5 — Banco de dados (PostgreSQL)"
echo "=============================================================================="
set -a
# shellcheck disable=SC1090
. "$APP_DIR/.env"
set +a

su - postgres -c "psql -tAc \"SELECT 1 FROM pg_roles WHERE rolname='pdv'\"" | grep -q 1 || {
    su - postgres -c "psql -c \"CREATE ROLE pdv LOGIN PASSWORD '$PDV_DB_PASSWORD';\""
}
su - postgres -c "psql -tAc \"SELECT 1 FROM pg_database WHERE datname='pdv'\"" | grep -q 1 || {
    su - postgres -c "createdb -O pdv pdv"
}
su - postgres -c "psql -c \"GRANT ALL PRIVILEGES ON DATABASE pdv TO pdv;\""

echo
echo "=============================================================================="
echo " ETAPA 6 — Migrations, static e superusuário"
echo "=============================================================================="
cd "$APP_DIR"
sudo -u "$APP_USER" .venv/bin/python manage.py migrate
sudo -u "$APP_USER" .venv/bin/python manage.py collectstatic --noinput
sudo -u "$APP_USER" .venv/bin/python manage.py makemigrations --check || {
    echo "AVISO: existem migrations pendentes (makemigrations --check falhou)." >&2
    echo "Gere-as no repositório antes do deploy; nada foi aplicado aqui." >&2
}
sudo -u "$APP_USER" .venv/bin/python manage.py check --deploy || true
if [ ! -f "$APP_DIR/../.superuser-criado" ]; then
    echo "Crie o superusuário global da plataforma agora (interativo):"
    sudo -u "$APP_USER" .venv/bin/python manage.py createsuperuser || true
fi

echo
echo "=============================================================================="
echo " ETAPA 7 — Serviço systemd (gunicorn em 127.0.0.1:$PDV_PORT)"
echo "=============================================================================="
install -m 0644 "$APP_DIR/deploy/pdv.service" /etc/systemd/system/pdv.service
systemctl daemon-reload
systemctl enable pdv
systemctl restart pdv
sleep 3
systemctl is-active --quiet pdv || {
    echo "ERRO: pdv.service não subiu. Veja: journalctl -u pdv -n 50" >&2
    exit 1
}
echo "gunicorn respondendo:"
curl -s -o /dev/null -w "  HTTP %{http_code} em http://127.0.0.1:$PDV_PORT/app/\n" \
    "http://127.0.0.1:$PDV_PORT/app/" || true

echo
echo "=============================================================================="
echo " ETAPA 8 — Nginx (site exclusivo do PDV)"
echo "=============================================================================="
if [ -f /etc/nginx/sites-enabled/pdv ] || [ -f /etc/nginx/sites-available/pdv ]; then
    cp -a /etc/nginx/sites-available/pdv "$BACKUP_DIR/nginx-pdv-anterior" 2>/dev/null || true
fi
sed "s/pdv\.wendrxw\.online/$DOMAIN/g" "$APP_DIR/deploy/nginx-pdv.example" \
    > /etc/nginx/sites-available/pdv
ln -sf /etc/nginx/sites-available/pdv /etc/nginx/sites-enabled/pdv
nginx -t
systemctl reload nginx
echo "Nginx recarregado com sucesso."

echo
echo "=============================================================================="
echo " ETAPA 9 — Cloudflare Tunnel"
echo "=============================================================================="
if [ "$SKIP_CLOUDFLARED" -eq 1 ]; then
    echo "Pulado (--skip-cloudflared)."
else
    if command -v cloudflared >/dev/null 2>&1 && cloudflared tunnel list >/dev/null 2>&1; then
        echo "Já existe um túnel Cloudflare. Para NÃO quebrar outros serviços,"
        echo "adicione manualmente o hostname no ingress existente:"
        echo
        echo "  - hostname: $DOMAIN"
        echo "    service: http://127.0.0.1:80"
        echo
        echo "  e recarregue: systemctl restart cloudflared"
        echo "  (modelo completo: deploy/cloudflared.example.yml)"
    else
        echo "Nenhum túnel autenticado. Para criar um novo (requer login no"
        echo "dashboard da Cloudflare):"
        echo
        echo "  cloudflared tunnel login"
        echo "  cloudflared tunnel create pdv"
        echo "  cloudflared tunnel route dns pdv $DOMAIN"
        echo "  sudo mkdir -p /etc/cloudflared"
        echo "  sudo cp deploy/cloudflared.example.yml /etc/cloudflared/config.yml"
        echo "  # edite <TUNNEL_ID> e mova o credentials-file para /etc/cloudflared/"
        echo "  sudo cloudflared service install"
        echo "  sudo systemctl start cloudflared"
    fi
fi

echo
echo "=============================================================================="
echo " ETAPA 10 — Validações finais"
echo "=============================================================================="
echo "--- systemd ---"
systemctl status pdv --no-pager | head -n 6
echo
echo "--- testes ---"
cd "$APP_DIR"
set -a
# shellcheck disable=SC1090
. "$APP_DIR/.env"
set +a
sudo -u "$APP_USER" .venv/bin/python manage.py check
sudo -u "$APP_USER" .venv/bin/python manage.py test 2>&1 | tail -n 4

echo
echo "=============================================================================="
echo " CONCLUÍDO — resumo"
echo "=============================================================================="
echo "  Domínio:        https://$DOMAIN"
echo "  App:            $APP_DIR"
echo "  gunicorn:       127.0.0.1:$PDV_PORT (systemd: pdv.service)"
echo "  Nginx:          /etc/nginx/sites-available/pdv"
echo "  Backup:         $BACKUP_DIR"
echo "  Logs:           journalctl -u pdv -f | journalctl -u nginx -f | journalctl -u cloudflared -f"
echo
echo "  Pendências manuais:"
echo "   1) Cloudflare Tunnel ingress para $DOMAIN (Etapa 9);"
echo "   2) criar o superusuário global se ainda não existir;"
echo "   3) configurar o módulo fiscal (Emitente/NFC-e) no sistema."
