# MVP — Análise de prontidão e pendências

> Gerado na TSK_00010 (auditoria de MVP + preparação de deploy).
> Data: 26/08/2026. Branch auditada: `feat/tsk-00011-ui-ux` (contém
> TSK_00011, TSK_00012 e TSK_00013; aguardando revisão/merge do PR).

## 1. Resumo executivo

O sistema está **funcionalmente próximo do MVP**: vendas com caixa,
produtos/estoque, clientes, financeiro, relatórios, fiscal NFC-e
(homologação), impressão via agente e multi-tenancy com isolamento
coberto por testes. O que falta é basicamente **polimento de UI
(TKS_00014), deploy automatizado e decisões operacionais**.

- Testes: **451 passando** (unit + integração, incluindo isolamento
  multi-tenant, concorrência de caixa/estoque e fluxos do PDV).
- `manage.py check --deploy` limpo em modo produção (2 avisos de HSTS
  opcionais, controlados por env).

## 2. O que já está pronto

| Área | Status | Observações |
| --- | --- | --- |
| Multi-tenancy | ✅ | `for_tenant()`, isolamento backend, testes de isolamento |
| PDV (venda, carrinho, desconto, cliente, pagamento) | ✅ | UI nova (TSK_00011) + backend adaptado (TSK_00012) |
| Produtos (cadastro, NCM/CEST/CFOP, código automático, imagem) | ✅ | UI nova |
| Clientes | ✅ | CRUD completo (TSK_00012) |
| Financeiro (dashboard, entradas/saídas, contas a receber) | ✅ | Dashboard novo; telas de lançamento em UI antiga |
| Relatórios (9 relatórios com filtros) | ✅ | TSK_00012 |
| Caixa (abertura/fechamento/suprimento/sangria) | ✅ | Funcional; UI antiga |
| Fiscal NFC-e | ✅ (homologação) | Geração/assinatura/transmissão (TSK_00008) |
| Impressão de comprovantes/etiquetas | ✅ | Print agent + Elgin L42 Pro |
| Landing + contato (leads) | ✅ | SEO básico |
| Django Admin (todos os models) | ✅ | list_display/filters/tenant |
| Auditoria | ✅ | `apps/audit` em operações críticas |

## 3. Pendências para o MVP (por prioridade)

### P1 — UI/UX (TSK_00014, em andamento nesta branch)

1. **Padronizar telas restantes** no `pdv_shell` (hoje usam
   `app_base.html`/`pdv_base.html`, visuais antigos):
   - `products/lista.html`, `products/detalhe.html`;
   - `sales/caixa_lista.html`, `sales/caixa_detalhe.html`,
     `sales/venda_lista.html`, `sales/venda_detalhe.html`;
   - `printing/config.html`, `printing/estacoes.html` (Configurações);
   - `financial/*` (contas, lançamentos, receber), `inventory/*`,
     `labels/*` (etiquetas) — segundo lote.
2. **Formulário de produto**: apenas NOME obrigatório (hoje
   `preco_custo`/`estoque_minimo` também são exigidos).
3. **Controles de janela**: remover "minimizar"; "maximizar" vira
   fullscreen (Fullscreen API); "X" continua logout.
4. **Busca universal** no topo (≥3 caracteres, resultados ao vivo,
   redirecionamento ao clicar) — endpoint + dropdown no shell.
5. **Responsivo/fullscreen**: sidebar vira drawer em mobile, grades e
   tabelas com overflow, PDV empilhável em telas pequenas.

### P1 — Deploy (TSK_00010)

6. **Executar `deploy/setup-pdv.sh` no servidor Debian** (auditoria,
   backup, pacotes, usuário `pdv`, venv/uv, `.env` com segredos
   gerados, PostgreSQL, migrations, static, systemd `pdv.service`,
   Nginx, Cloudflare Tunnel para `pdv.wendrxw.online`).
7. **Cloudflare Tunnel**: adicionar o hostname no ingress EXISTENTE
   (não criar túnel novo — servidor é compartilhado).
8. **Configurar HTTPS/HSTS** e validar CSRF/cookies com o domínio real
   (`PDV_BEHIND_PROXY=True` já suportado em settings).
9. **Backup diário** (pg_dump + media) e teste de restauração.
10. **Cron `check_print_agents`** com alerta (ver docs/producao-servidor.md §11.4).

### P2 — Segurança/higiene (já encaminhados nesta branch)

11. ~~`SECURE_PROXY_SSL_HEADER`, HSTS completo, nosniff, referrer
    policy~~ → implementados (env-gated) na TSK_00010.
12. ~~`.gitignore` (.env, media, staticfiles, sqlite, cache) e
    `db.sqlite3` fora do git~~ → implementados na TSK_00010.
13. ~~Bibliotecas desatualizadas (cryptography, gunicorn, sqlparse)~~ →
    atualizadas com testes verdes na TSK_00010.
14. **Rate limiting** em login/contato (hoje só a API de impressão tem
    throttle) — sugerir `django-ratelimit` ou middleware próprio.
15. **Content Security Policy** — avaliar compatibilidade com Tailwind
    CDN antes de habilitar (o Play CDN exige script inline externo;
    produção deve compilar o CSS localmente — ver item 17).
16. **Monitoramento**: alerta de erros 5xx/restarts (sentry ou e-mail).

### P2 — Arquitetura

17. **Tailwind em produção**: hoje o CSS vem do CDN (`cdn.tailwindcss.com`)
    — substituir por build estático (ex.: Tailwind CLI) para remover
    dependência de terceiros e habilitar CSP.
18. **DRF**: `djangorestframework` está declarado mas sem uso;
    remover do `pyproject.toml` ou usar nas futuras integrações.
19. **Fluxo de leads → tenant**: validar ponta a ponta com e-mail real
    (convite de usuário) antes do lançamento.
20. **Seed de demonstração** (produtos/categorias da TSK_00011) para
    ambientes de teste — hoje não existe.

### P3 — Futuro (pós-MVP)

21. Módulo fiscal: sair da homologação SEFAZ-SP e emissão real;
    contingência offline (deliberadamente fora do escopo inicial).
22. Multi-caixa/multi-loja: preparar a tela de caixas para várias
    estações simultâneas (backend já suporta).
23. TEF/PIX via API, integração contábil, app mobile (offline).
24. Testes E2E (Playwright) dos fluxos críticos do PDV.

## 4. Decisões que dependem do dono

1. **Servidor de produção**: este ambiente de trabalho não tem acesso
   SSH ao servidor Debian — informar como executar o deploy (acesso ao
   servidor ou execução local dos scripts).
2. **Túnel Cloudflare**: confirmar o ID do túnel existente para apenas
   adicionar o hostname `pdv.wendrxw.online`.
3. **Domínio**: `pdv.wendrxw.online` já configurado na Cloudflare?
4. **E-mail transacional** (convites/alertas) — qual provedor usar?
5. **NFC-e**: manter homologação no lançamento do MVP?

## 5. Checklist final de produção (docs/producao-servidor.md §15)

- [ ] `.env` criado (600) com `DJANGO_SECRET_KEY` forte e `DEBUG=False`
- [ ] PostgreSQL provisionado; `migrate` OK
- [ ] `collectstatic` OK; gunicorn em 127.0.0.1:8001
- [ ] Nginx ativo; static servido; `/media/` NÃO exposto
- [ ] HTTPS válido via Cloudflare Tunnel (teste pair/poll 429/401)
- [ ] `PDV_CACHE_BACKEND=file`
- [ ] Cron `check_print_agents` ativo
- [ ] Backup diário + restauração testada
- [ ] Superusuário criado; sem segredos no git
- [ ] Loja pareada imprime comprovante ponta a ponta
