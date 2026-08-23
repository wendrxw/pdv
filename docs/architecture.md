# Arquitetura — Fundação (TSK_00001)

## Visão geral

Sistema SaaS multi-tenant para gestão de PDV. Esta fundação entrega a base
arquitetural exigida por todos os módulos futuros (produtos, estoque,
financeiro, fiscal, PDV):

- projeto Django configurado (config/, apps/);
- infraestrutura de multi-tenancy;
- autenticação com bcrypt;
- módulo de clientes da plataforma com onboarding;
- Django Admin como painel administrativo global;
- landing page pública em pt-BR com captura de leads.

## Estrutura

```
pdv/
├── config/            # settings, urls, wsgi, asgi
├── apps/
│   ├── core/          # tenancy base + validadores (CPF/CNPJ)
│   ├── companies/     # Tenant
│   ├── accounts/      # User customizado, login/logout
│   ├── clients/       # ClientePlataforma, histórico, onboarding, leads
│   ├── audit/         # AuditLog
│   └── web/           # landing page, contato, dashboard
├── frontend/
│   └── templates/     # base.html compartilhado
├── docs/              # documentação arquitetural
└── tasks/             # tasks do fluxo de desenvolvimento
```

## Decisões arquiteturais

### Multi-tenancy

- Fonte única de verdade: `request.user.get_tenant()`.
- `TenantQuerySet.for_tenant()` e base abstrata `TenantAwareModel`
  (`apps.core.tenancy`) para todos os models operacionais.
- Isolamento no backend; UUID/SKU/código nunca isolam dados.
- Detalhes: [docs/multi-tenancy.md](multi-tenancy.md).

### Banco de dados

- Produção: PostgreSQL via variáveis de ambiente (`PDV_DB_ENGINE=postgres`,
  `PDV_DB_NAME`, `PDV_DB_USER`, `PDV_DB_PASSWORD`, `PDV_DB_HOST`,
  `PDV_DB_PORT`).
- Desenvolvimento local/testes: SQLite por padrão (zero configuração),
  sem perda de portabilidade — o código não usa recursos exclusivos de um
  SGBD.

### Segurança

- Hash de senhas: bcrypt (`BCryptSHA256PasswordHasher` primeiro na lista).
- CSRF obrigatório em todo POST (formulários nativos do Django).
- `/admin/` restrito a `is_staff`; usuários de tenant não têm acesso.
- Configurações sensíveis via env vars; `DEBUG=False` ativa HSTS,
  cookies seguros e SSL redirect.
- Auditoria básica centralizada (`apps.audit.registrar`) para operações
  críticas (criação/ativação/conversão de clientes).

### Frontend

- Django Templates + TailwindCSS (CDN nesta fase; migrar para build
  compilado antes de produção) + JavaScript mínimo.
- Sem SPA/frameworks frontend, conforme diretriz do projeto.
- Landing page: hero, recursos, benefícios, como funciona, CTA, footer;
  SEO básico (title, description, Open Graph); responsiva.

## Fluxo comercial implementado

```
Visitante → /contato/ → LeadContato (NOVO)
    ↓ (admin converte)
ClientePlataforma (LEAD)
    ↓ EM_ANALISE → PENDENTE (actions do admin)
    ↓ ativar_cliente() [transacional]
Tenant criado + Onboarding INICIADO + cliente ATIVO
    ↓ (próximas fases)
Usuário convidado vinculado ao tenant
```

## Módulos implementados

### Fundação (TSK_00001)

Scaffold, multi-tenancy, autenticação, clientes da plataforma, auditoria,
landing page. Ver [docs/clients.md](clients.md) e
[docs/multi-tenancy.md](multi-tenancy.md).

### Produtos, Estoque e Inventário (TSK_00002–00005)

Catálogo com isolamento por tenant, EAN-13 interno com renderização SVG,
controle de estoque transacional com lock pessimista e histórico completo,
inventário físico com ajustes auditáveis. Ver
[docs/products.md](products.md).

### Impressão de comprovantes (print)

PrintJobs com fila, retry e idempotência no servidor + Local Print Agent
na máquina da loja (polling HTTPS, ESC/POS, `/dev/usb/lp0`, runit no Void
Linux). Ver [docs/print.md](print.md).

## Próximas fases (fora do escopo atual)

1. Módulo financeiro (entradas, saídas, recebíveis, análise).
2. PDV (caixa, carrinho, pagamentos) consumindo `EstoqueService`.
3. Módulo fiscal NFC-e (SEFAZ-SP homologação).

## Como rodar

```bash
uv sync
uv run python manage.py migrate
uv run python manage.py createsuperuser
uv run python manage.py runserver
```

Testes e lint:

```bash
uv run python manage.py test
uv run ruff check apps config manage.py
```
