# Produção — Guia do Servidor (passo a passo)

> Guia detalhado para colocar o PDV em produção no SERVIDOR. A impressão
> segue em separado: o servidor só enfileira PrintJobs; quem imprime é o
> Local Print Agent na loja ([docs/print-producao.md](print-producao.md),
> [local-print-agent/README.md](../local-print-agent/README.md)).
>
> Pré-requisitos: servidor Linux (Debian/Ubuntu/RHEL/Arch/Void), acesso
> root ou sudo, um domínio apontado para o servidor (ex.:
> `pdv.sua-empresa.com`) e Python 3.14 (ou `uv`, que instala a versão).

> **Atalho (Debian/Ubuntu):** o script `deploy/setup-pdv.sh` executa os
> passos 2–9 deste guia de forma idempotente (com auditoria de serviços
> e portas, backup de `/etc/nginx`, `/etc/cloudflared` e systemd antes
> de qualquer mudança, e validação de `nginx -t`). Uso:
> `sudo sh deploy/setup-pdv.sh --repo=https://github.com/<conta>/pdv.git`.
> Os modelos de serviço/configuração estão em `deploy/`.

## Índice

1. [Visão geral da topologia](#1-visão-geral-da-topologia)
2. [Preparação do sistema](#2-preparação-do-sistema)
3. [Código e dependências](#3-código-e-dependências)
4. [Variáveis de ambiente](#4-variáveis-de-ambiente)
5. [PostgreSQL](#5-postgresql)
6. [Migrations, static e superusuário](#6-migrations-static-e-superusuário)
7. [gunicorn (WSGI) como serviço](#7-gunicorn-wsgi-como-serviço)
8. [Nginx](#8-nginx)
9. [HTTPS — Opção A: Cloudflare Tunnel](#9-https--opção-a-cloudflare-tunnel)
10. [HTTPS — Opção B: Let's Encrypt (certbot)](#10-https--opção-b-let-s-encrypt-certbot)
11. [Impressão: passos específicos do servidor](#11-impressão-passos-específicos-do-servidor)
12. [Backups](#12-backups)
13. [Monitoramento e logs](#13-monitoramento-e-logs)
14. [Primeiro uso do sistema](#14-primeiro-uso-do-sistema)
15. [Check-list final de produção](#15-check-list-final-de-produção)

---

## 1. Visão geral da topologia

```
Internet
   │
   ▼
Cloudflare Tunnel (ou Nginx com TLS)  ← ÚNICA porta exposta: 443
   │
   ▼ 127.0.0.1:80 (Nginx)
Nginx (static + proxy reverso)
   │
   ▼ 127.0.0.1:8001 (gunicorn)
Django (config.wsgi)
   │
   ▼ 127.0.0.1:5432
PostgreSQL
```

Regras de ouro:

- **Só o 443 é público.** O gunicorn (8001) e o PostgreSQL (5432) ficam
  restritos a localhost/firewall.
- `/api/print-agent/` precisa de HTTPS obrigatório (o token de estação
  trafega nos cabeçalhos).
- `/media/` (certificados A1 do fiscal) **nunca** é servido pelo Nginx.
- Nada de `DEBUG=True`, senhas em texto, ou `.env` no repositório.

## 2. Preparação do sistema

```bash
# Sistema atualizado + pacotes base
sudo apt update && sudo apt upgrade -y        # Debian/Ubuntu
sudo apt install -y nginx postgresql postgresql-contrib curl git
# se for usar certbot: sudo apt install -y certbot python3-certbot-nginx

# Diretório da aplicação
sudo mkdir -p /opt/pdv
sudo chown $USER:$USER /opt/pdv

# Usuário do banco e diretórios de runtime
sudo -u postgres createuser --pwprompt pdv      # anote a senha (vai no .env)
sudo -u postgres createdb -O pdv pdv
sudo mkdir -p /opt/pdv/media /opt/pdv/staticfiles /opt/pdv/.django-cache
```

Firewall (ufw, se ativo):

```bash
sudo ufw default deny incoming
sudo ufw allow 80/tcp     # apenas se usar certbot
sudo ufw allow 443/tcp
sudo ufw allow 22/tcp     # SSH
sudo ufw enable
```

> Com Cloudflare Tunnel não é preciso liberar nem 80/443 — o túnel faz a
> conexão de SAÍDA. Deixe só o 22.

## 3. Código e dependências

```bash
cd /opt/pdv
git clone https://github.com/<sua-conta>/pdv.git .
git checkout main          # SEMPRE a main estável; nunca feature branch

# Opção recomendada: uv (instala o Python 3.14 e as dependências travadas)
curl -LsSf https://astral.sh/uv/install.sh | sh
uv sync --frozen

# Sem uv: criar venv com Python 3.14 e instalar
# python3.14 -m venv .venv && .venv/bin/pip install .
```

> `uv sync --frozen` usa o `uv.lock` — mesma versão de tudo testado em CI.
> A aplicação exige Python ≥ 3.14 (veja `pyproject.toml`).

## 4. Variáveis de ambiente

Crie o arquivo de produção a partir do modelo:

```bash
cp deploy/pdv.env.example /opt/pdv/.env
chmod 600 /opt/pdv/.env
nano /opt/pdv/.env
```

Conteúdo comentado (todas as chaves usadas pela aplicação):

```ini
# --- Django -----------------------------------------------------
# Gere com: python -c "import secrets; print(secrets.token_urlsafe(64))"
DJANGO_SECRET_KEY=COLOQUE_AQUI
DJANGO_DEBUG=False
DJANGO_ALLOWED_HOSTS=pdv.sua-empresa.com
DJANGO_CSRF_TRUSTED_ORIGINS=https://pdv.sua-empresa.com

# --- Banco ------------------------------------------------------
PDV_DB_ENGINE=postgres
PDV_DB_NAME=pdv
PDV_DB_USER=pdv
PDV_DB_PASSWORD=<senha criada no passo 2>
PDV_DB_HOST=127.0.0.1
PDV_DB_PORT=5432

# --- TLS --------------------------------------------------------
# Com Cloudflare Tunnel/nginx terminando TLS, mantenha True.
DJANGO_SECURE_SSL_REDIRECT=True
DJANGO_HSTS_SECONDS=31536000

# --- Cache -------------------------------------------------------
# Obrigatório em produção: o throttle da API de impressão precisa de
# cache COMPARTILHADO entre os workers do gunicorn.
PDV_CACHE_BACKEND=file
PDV_CACHE_DIR=/opt/pdv/.django-cache

# --- Uploads (certificado A1 do fiscal) --------------------------
PDV_MEDIA_ROOT=/opt/pdv/media

# --- Módulo fiscal NFC-e ----------------------------------------
SEFAZ_UF=SP
SEFAZ_AMBIENTE=HOMOLOGACAO
# SEFAZ_CERTIFICATE_PASSWORD=<senha do A1 — NUNCA em logs>
```

> A aplicação carrega o `.env` pelo próprio serviço (veja o passo 7).

## 5. PostgreSQL

```bash
# Permitir senha local (md5/scram) se o peer auth bloquear o Django
sudo -u postgres psql -c "ALTER USER pdv WITH PASSWORD '<senha>';"
sudo -u postgres psql -c "GRANT ALL PRIVILEGES ON DATABASE pdv TO pdv;"
```

Teste a conexão:

```bash
cd /opt/pdv
set -a && . ./.env && set +a
.venv/bin/python manage.py check --database default
```

## 6. Migrations, static e superusuário

```bash
cd /opt/pdv
set -a && . ./.env && set +a

.venv/bin/python manage.py migrate
.venv/bin/python manage.py collectstatic --noinput
.venv/bin/python manage.py createsuperuser   # administrador GLOBAL da plataforma
```

> O superusuário é da PLATAFORMA (is_staff): gerencia tenants/clientes no
> `/admin/`. Usuários de loja são criados depois, dentro do fluxo do
> sistema.

## 7. gunicorn (WSGI) como serviço

O gunicorn já é dependência do projeto. Unit com systemd (Debian/Ubuntu):

`/etc/systemd/system/pdv.service`:

```ini
[Unit]
Description=PDV — gunicorn
After=network.target postgresql.service

[Service]
User=seu-usuario
Group=seu-usuario
WorkingDirectory=/opt/pdv
EnvironmentFile=/opt/pdv/.env
ExecStart=/opt/pdv/.venv/bin/gunicorn config.wsgi:application \
    --bind 127.0.0.1:8001 \
    --workers 3 \
    --timeout 60 \
    --access-logfile - \
    --error-logfile -
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now pdv
systemctl status pdv
curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8001/app/
```

Se o servidor for Void Linux (runit), use `/etc/sv/pdv/run`:

```sh
#!/bin/sh
cd /opt/pdv
set -a; . ./.env; set +a
exec chpst -u seu-usuario /opt/pdv/.venv/bin/gunicorn \
    config.wsgi:application --bind 127.0.0.1:8001 \
    --workers 3 --timeout 60 --access-logfile - --error-logfile -
```

```bash
sudo ln -s /etc/sv/pdv /var/service/
sv status pdv
```

## 8. Nginx

```bash
sudo cp deploy/nginx-pdv.example /etc/nginx/sites-available/pdv
sudo nano /etc/nginx/sites-available/pdv     # ajuste o domínio e o TLS
sudo ln -s /etc/nginx/sites-available/pdv /etc/nginx/sites-enabled/pdv
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t && sudo systemctl reload nginx
```

Pontos críticos do arquivo:

- `proxy_pass http://127.0.0.1:8001;` (gunicorn local);
- `location /static/ { alias /opt/pdv/staticfiles/; }`;
- **nenhum** `location /media/` — certificados A1 não são públicos;
- cabeçalhos `X-Forwarded-Proto` para o Django detectar HTTPS.

## 9. HTTPS — Opção A: Cloudflare Tunnel

Sem abrir portas e sem IP fixo (padrão usado pelo projeto):

```bash
# 1. Instalar o cloudflared
curl -L https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64 -o /usr/local/bin/cloudflared
sudo chmod +x /usr/local/bin/cloudflared

# 2. Login e criar o túnel no dashboard da Cloudflare (domínio já na CF)
cloudflared tunnel login
cloudflared tunnel create pdv        # anote o <TUNNEL_ID>
cloudflared tunnel route dns pdv pdv.sua-empresa.com

# 3. Configurar o ingress (use o modelo)
sudo mkdir -p /etc/cloudflared
sudo cp deploy/cloudflared.example.yml /etc/cloudflared/config.yml
# edite: <TUNNEL_ID> e o hostname; service: http://127.0.0.1:80
sudo nano /etc/cloudflared/config.yml
sudo mv ~/.cloudflared/<TUNNEL_ID>.json /etc/cloudflared/

# 4. Serviço
sudo cloudflared service install
sudo systemctl start cloudflared
```

Valide: `curl -sI https://pdv.sua-empresa.com/` → HTTP/2 200 com cert da
Cloudflare.

## 10. HTTPS — Opção B: Let's Encrypt (certbot)

```bash
sudo apt install -y certbot python3-certbot-nginx
sudo certbot --nginx -d pdv.sua-empresa.com
# certbot ajusta o server block e ativa a renovação automática
```

No `nginx-pdv.example`, descomente o bloco `listen 443 ssl` e os
caminhos do certificado, e no bloco 80 descomente o redirect
`return 301 https://...`.

## 11. Impressão: passos específicos do servidor

1. **HTTPS obrigatório** — só prossiga com o passo 9/10 concluído.
2. Migrations do módulo: `python manage.py migrate printing` (já
   incluídas no passo 6).
3. Smoke test da API do agente:

```bash
# Pareamento com código inválido → 400
curl -s -o /dev/null -w "%{http_code}\n" -X POST https://pdv.sua-empresa.com/api/print-agent/pair/ \
  -H "Content-Type: application/json" -d '{"codigo":"ZZZZZZ"}'

# Poll sem credencial → 401
curl -s -o /dev/null -w "%{http_code}\n" -X POST https://pdv.sua-empresa.com/api/print-agent/poll/ \
  -H "Content-Type: application/json" -d '{}'

# Força bruta → 429 após 20 falhas (throttle)
for i in $(seq 1 21); do curl -s -o /dev/null -w "%{http_code} " -X POST \
  https://pdv.sua-empresa.com/api/print-agent/poll/ -H "Content-Type: application/json" -d '{}'; done
```

4. **Monitoramento das estações** (cron — a cada 5 min, envia e-mail/alert
   se alguma estação ativa ficar sem atividade):

```cron
*/5 * * * * cd /opt/pdv && set -a && . ./.env && set +a && \
  .venv/bin/python manage.py check_print_agents --minutos 10 || \
  echo "Estação de impressão parada" | mail -s "PDV: estação offline" ops@sua-empresa.com
```

5. Cadastre a estação e pareie na loja: PDV → Impressão → Estações (o
   código aparece na tela; a instalação na loja está em
   [local-print-agent/README.md](../local-print-agent/README.md)).
6. Cache compartilhado: confira `PDV_CACHE_BACKEND=file` (o throttle usa
   cache; `locmem` não funciona com múltiplos workers do gunicorn).

## 12. Backups

```bash
# Script diário (cron, ex.: 02:00) — banco + uploads + static
cat > /opt/pdv/backup.sh <<'EOF'
#!/bin/sh
set -e
DATA=$(date +%F)
DEST=/opt/backups/pdv
mkdir -p "$DEST"
cd /opt/pdv && set -a && . ./.env && set +a
.venv/bin/python manage.py dumpdata --natural-foreign --natural-primary --exclude contenttypes --exclude auth.permission --exclude sessions.session --exclude admin.logentry > /dev/null || true
pg_dump -h 127.0.0.1 -U pdv pdv | gzip > "$DEST/db-$DATA.sql.gz"
tar czf "$DEST/media-$DATA.tar.gz" -C /opt/pdv media
find "$DEST" -mtime +14 -delete
EOF
sudo chmod +x /opt/pdv/backup.sh
# crontab: 0 2 * * * /opt/pdv/backup.sh
```

> Melhor ainda: `pg_dump` é o mínimo; para HA use `pg_basebackup`/WAL.
> Teste a RESTAURAÇÃO uma vez por mês (backup não testado não existe).

## 13. Monitoramento e logs

```bash
# Django/gunicorn
journalctl -u pdv -f                      # systemd
tail -f /var/log/pdv/current              # runit + svlogd

# Nginx
tail -f /var/log/nginx/pdv.error.log

# Métricas básicas: uso de disco do backup/cache
du -sh /opt/backups /opt/pdv/.django-cache /var/lib/postgresql
```

Sinais de alerta a vigiar:

- `check_print_agents` acusando estação parada (§11.4);
- erros 5xx no nginx (`grep ' 5[0-9][0-9] ' /var/log/nginx/access.log`);
- `systemctl status pdv` com restart loop (ver `journalctl -u pdv`);
- disco cheio (staticfiles/backups/cache).

## 14. Primeiro uso do sistema

1. Entre em `https://pdv.sua-empresa.com/admin/` com o superusuário.
2. Confira/ative os tenants (`admin` → Tenants) ou siga o onboarding
   (Landing → contato → lead → ativação cria o tenant — fluxo em
   [docs/clients.md](clients.md)).
3. Crie os usuários da loja vinculados ao tenant.
4. Na loja: cadastre produtos/estoque, formas de pagamento e a
   configuração fiscal (Emitente/NFC-e) antes de operar o PDV.
5. Impressão: crie a estação (§11.5) e instale o agente na loja.

## 15. Check-list final de produção

- [ ] `.env` criado (600) com `DJANGO_SECRET_KEY` forte e `DEBUG=False`.
- [ ] PostgreSQL com usuário/senha próprios; `migrate` OK.
- [ ] `collectstatic` OK; gunicorn ativo em `127.0.0.1:8001`.
- [ ] Nginx ativo; static servido; `/media/` NÃO exposto.
- [ ] HTTPS válido (Cloudflare Tunnel ou certbot) — teste no pair/poll.
- [ ] `PDV_CACHE_BACKEND=file` (cache compartilhado entre workers).
- [ ] Throttle respondendo 429 após 20 falhas (§11.3).
- [ ] Cron de `check_print_agents` ativo (§11.4).
- [ ] Backup diário rodando e restauração testada.
- [ ] Superusuário criado; senhas não estão em logs nem no git.
- [ ] Loja pareada imprime comprovante ponta a ponta
      ([docs/print-producao.md](print-producao.md) §6).
