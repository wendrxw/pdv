# Estudo Técnico — Migração do PDV (Web/Django) para Aplicação Desktop

**Autor:** Arquiteto de Software Sênior (estudo automatizado)
**Data:** 2026-08-28
**Status:** ESTUDO — aguardando aprovação do proprietário antes de qualquer implementação
**Escopo:** Nenhum arquivo de código foi alterado. Este documento é somente-leitura.

---

## 1. Resumo Executivo

O PDV é um **SaaS multi-tenant em produção** (`https://pdv.wendrxw.online`) com 15 apps Django,
~19 mil linhas de Python, 46 templates HTML e **456 testes automatizados passando**. O sistema
cobre: onboarding de clientes da plataforma, produtos, estoque/inventário, clientes da loja,
financeiro completo, PDV (vendas/caixa), NFC-e (SEFAZ-SP), relatórios, impressão de comprovantes
(ESC/POS) e etiquetas (EPL2), com arquitetura de impressão distribuída via "Print Agent" instalado
nas lojas (Linux e Windows).

A migração para desktop deve ser tratada como **migração de interface e execução**, nunca como
oportunidade de reescrever regras de negócio. O backend Django contém a totalidade das regras
(multi-tenancy, validações, cálculos financeiros, fiscal, impressão) e está coberto por testes.

**Decisão central recomendada:** manter o Django como backend inalterado (servidor central, como
hoje — o SaaS multi-tenant e a produção dependem disso) e construir um **shell desktop em Python
usando PyWebview** que carrega a aplicação existente em uma janela nativa, adicionando capacidades
de desktop (janela nativa, atalhos globais, bandeja, integração direta com impressora, atualização
automática). O Print Agent existente é **incorporado** ao shell, eliminando a instalação separada.

Essa escolha preserva 100% das funcionalidades por construção (o frontend atual é reaproveitado
integralmente), mantém a aparência moderna já construída (Tailwind, sidebar azul #001B3D, tela de
venda com catálogo/carrinho) e elimina o maior risco de qualquer migração: regressão funcional.

**Qt não foi escolhida** (ver seção 8/9): reescrever 46 templates como widgets Qt implicaria
esforço altíssimo e alto risco; QWebEngine embute um Chromium (~250 MB) redundante. PyWebview usa o
webview nativo do SO (WebKitGTK no Linux, WebView2 no Windows), com binário pequeno e 100% Python
(alinhado à equipe).

---

## 2. Arquitetura Atual

### 2.1 Visão geral

```
Internet ── Cloudflare ── cloudflared tunnel ── Nginx :80 ── gunicorn 127.0.0.1:8001 ── Django 5.2 ── PostgreSQL 15
                                                                                                   └── media/ (privado, certificados A1)
Loja (Linux/Windows):
  Print Agent (Python stdlib, polling 3s) ──HTTPS──> /api/print-agent/{pair,poll,jobs/<uuid>/resultado}
  └─ impressora térmica ESC/POS (/dev/usb/lp0 ou spooler RAW) e Elgin L42 Pro (EPL2)
```

- **Backend:** Python 3.11, Django 5.2 + DRF (declarado, ainda sem uso), psycopg2, bcrypt,
  cryptography, signxml, lxml, requests, gunicorn.
- **Frontend:** Django Templates + TailwindCSS via **CDN (Play CDN)** + JavaScript vanilla inline.
  Nenhum framework JS. Ícones SVG inline. Gráficos em SVG puro.
- **Banco:** SQLite em dev; PostgreSQL 15 em produção (Debian 12 i686, servidor compartilhado).
- **Infra:** systemd (`pdv.service`, gunicorn 3 workers × 2 threads), Nginx (site `pdv`),
  Cloudflare Tunnel (`pdv-tunnel.service`), deploy via `deploy/setup-pdv.sh` e
  `deploy/ssh-servidor.py` (paramiko).

### 2.2 Apps e responsabilidades

| App | Papel | Views próprias | Templates |
|---|---|---|---|
| `core` | Tenancy (`TenantAwareModel`, `TenantQuerySet.for_tenant`), validadores CPF/CNPJ, context processors | — | — |
| `companies` | `Tenant` (uuid, slug, status, `permitir_estoque_negativo`) | — (admin) | — |
| `accounts` | `User` custom (FK tenant), login/logout | 2 | 1 |
| `clients` | `ClientePlataforma` (SaaS), `Onboarding`, `LeadContato`, backend de auth por e-mail | — (admin) | — |
| `web` | Landing, contato, dashboard `/app/` | 4 | 4 |
| `products` | Categoria/Marca/Produto, EAN-13 interno + SVG, CRUD | 9 | 3 |
| `customers` | Cliente da loja (CRUD + ativar/desativar) | 5 | 3 |
| `inventory` | Fornecedor, Estoque, Movimentações, Inventário | 12 | 9 |
| `financial` | Entradas, Saídas, Contas a Receber, Contas, Análise/Dashboard | 13 | 7 |
| `sales` | PDV, Venda, Caixa, Movimentações de caixa | 11 | 6 |
| `reports` | Índice de relatórios (agregações SQL) | 1 | 1 |
| `fiscal` | NFC-e (model, chave, XML 4.00, assinatura, SEFAZ SOAP, QR Code) | — (admin) | — |
| `printing` | Estações, PrintJob, pareamento, API do agente | 3 + 3 API | 2 |
| `labels` | Etiquetas Elgin (config, jobs, preview, API) | 8 + 2 API | 3 |
| `audit` | `AuditLog` + helper `registrar()` não-bloqueante | — (admin) | — |

### 2.3 Multi-tenancy (regra fundamental — intocável)

- Fonte de verdade: `request.user.get_tenant()` (`apps/accounts/models.py:58`). Nunca parâmetros do
  frontend.
- Todo queryset operacional: `Model.objects.for_tenant(tenant)` ou
  `get_object_or_404(Model, tenant=tenant, uuid=...)`.
- Unicidades por tenant via `UniqueConstraint` no banco (produtos, categorias, clientes, contas…).
- Arquivos de produto isolados por tenant: `produtos/{tenant_id}/{uuid}/…`.
- Isolamento garantido por testes (`apps/core/tests/test_tenancy.py`).

### 2.4 Frontend atual (o que define a "cara" do sistema)

- `frontend/templates/pdv_shell.html` — shell com sidebar azul-navy (`#001B3D`), 8 itens de menu,
  topbar com busca (atalho **F2**), avatar, controles de janela decorativos
  (lock/minimize/maximize/close), toasts, relógio, status NFC-e "Conectado".
- `base.html` — Tailwind Play CDN + fonte Inter (única dependência externa de rede do frontend).
- `apps/sales/templates/sales/venda.html` — tela de PDV: catálogo paginado (9/página), carrinho,
  modais, atalhos **F3** (desconto), **F4** (cliente), **F5** (receber), busca de produto via
  `fetch` (`sales:produto_busca`) compatível com leitor USB HID (keyboard wedge).
- `apps/financial/templates/financial/dashboard.html` — KPIs + gráficos SVG puros (linha/rosca) a
  partir de JSON embutido no contexto.
- `apps/labels/templates/labels/selecao.html` — seleção de produtos, preview de etiquetas
  client-side via `fetch`, aviso de posição vazia na bobina (2 etiquetas/fileira).
- `apps/sales/templates/sales/venda_detalhe.html` e `labels/status.html` — polling de status de
  impressão a cada 3 s.

### 2.5 Impressão (já é um componente "desktop" hoje)

- Servidor nunca toca a impressora. `PrintJob` PENDING → PROCESSING → PRINTED/FAILED, com retry
  backoff [5,15,60,300,900]s, lease de 300 s para PROCESSING órfão, idempotência por uuid.
- API machine-to-machine: `pair/` (código de pareamento de uso único, token bcrypt no banco),
  `poll/` (com `disponivel:false`), `jobs/<uuid>/resultado/`; throttle por IP; sem sessão/CSRF.
- Agente local (`local-print-agent/`): Python **stdlib** (urllib), ESC/POS (58/80 mm, codepages,
  modo texto puro para Tomate MDK-080), EPL2 para Elgin L42 Pro Full (203 DPI, Code 128 com
  estreitamento), dedupe local por uuid (`processados.jsonl`), Linux (`/dev/usb/lp0`, runit) e
  Windows (spooler RAW via pywin32, autostart HKCU, exe PyInstaller publicado via GitHub Actions).

---

## 3. Inventário Completo de Funcionalidades

### 3.1 Matriz de funcionalidades (Web atual → Desktop)

| # | Funcionalidade | Web atual | Desktop (recomendado) | Backend reutilizável | Interface necessária | Hardware | Risco |
|---|---|---|---|---|---|---|---|
| 1 | Login (usuário loja + cliente SaaS por e-mail) | `/login/` POST + CSRF | Mesma tela dentro do shell | 100% (`accounts`, `clients.backends`) | Nenhuma | — | Baixo |
| 2 | Logout | `/logout/` POST | Item na sidebar/sair nativo | 100% | Nenhuma | — | Baixo |
| 3 | Dashboard `/app/` | `web/dashboard` + relógio JS | Idem; relógio já existe | 100% | Nenhuma | — | Baixo |
| 4 | PDV — abrir caixa | POST `sales:pdv_home` | Idem | 100% (`CaixaService`) | Nenhuma | — | Baixo |
| 5 | PDV — nova venda / reutilizar caixa | POST `sales:nova_venda` | Idem | 100% | Nenhuma | — | Baixo |
| 6 | PDV — carrinho (add/alterar/remover item) | POST `sales:venda_tela` | Idem + atalhos nativos | 100% (`VendaService`) | Manter modais/tabela | — | Baixo |
| 7 | PDV — busca de produto (nome/SKU/código de barras) | GET `sales:produto_busca` (fetch) | Idem (leitor USB = teclado) | 100% | Nenhuma | **Leitor código de barras USB HID** | Baixo |
| 8 | PDV — desconto | POST ação `desconto` | Idem (F3) | 100% | Nenhuma | — | Baixo |
| 9 | PDV — seleção de cliente | POST ação `cliente` | Idem (F4) | 100% | Nenhuma | — | Baixo |
| 10 | PDV — pagamento (formas, taxa, troco) | POST ação `pagamento` | Idem (F5) | 100% (`PagamentoVenda`) | Nenhuma | — | Baixo |
| 11 | PDV — finalizar venda + financeiro integrado | POST ação `finalizar` | Idem | 100% (`finalizar_venda` → conta a receber/entrada caixa) | Nenhuma | — | Baixo |
| 12 | PDV — impressão de comprovante obrigatória | `criar_print_job` → agente | **Agente embutido no shell** (polling local) | 100% (`printing.services`, API) | Status de impressão na tela de venda | **Térmica ESC/POS 58/80mm** | Médio |
| 13 | PDV — cancelar venda com motivo | POST `venda_detalhe` | Idem | 100% (estornos financeiros) | Nenhuma | — | Baixo |
| 14 | Vendas — listar/filtrar/detalhar | `/app/vendas/` | Idem | 100% | Nenhuma | — | Baixo |
| 15 | Caixa — listar/detalhar/fechar | `/app/caixa/` | Idem | 100% (`fechar_caixa`) | Nenhuma | — | Baixo |
| 16 | Caixa — suprimento/sangria | POST `movimentacao_caixa` | Idem | 100% | Nenhuma | — | Baixo |
| 17 | Produtos — CRUD completo | CRUD views | Idem | 100% | Nenhuma | — | Baixo |
| 18 | Produtos — busca assíncrona na listagem | `products:busca` (fetch) | Idem | 100% | Nenhuma | — | Baixo |
| 19 | Produtos — geração EAN-13 interno + SVG | `gerar_codigo_barras`, `codigo_barras.svg` | Idem | 100% (`barcode.py`) | Nenhuma | — | Baixo |
| 20 | Produtos — upload de imagem (jpg/png/webp, 5 MB) | form multipart | Idem; opcional diálogo nativo de arquivo | 100% | Diálogo nativo (opcional) | — | Baixo |
| 21 | Clientes da loja — CRUD + ativar/desativar | CRUD views | Idem | 100% | Nenhuma | — | Baixo |
| 22 | Estoque — dashboard/entrada/saída/saldos/movimentações/histórico | views estoque | Idem | 100% (`EstoqueService` com lock) | Nenhuma | — | Baixo |
| 23 | Inventário — ciclo completo (contagem congelada, revisão, divergências, ajustes) | `views_inventario` | Idem | 100% | Nenhuma | — | Baixo |
| 24 | Financeiro — entradas/saídas (receber/pagar/cancelar/estornar) | views | Idem | 100% | Nenhuma | — | Baixo |
| 25 | Financeiro — contas a receber com parcelamento (1–48x) | views | Idem | 100% | Nenhuma | — | Baixo |
| 26 | Financeiro — cadastro de contas/categorias/formas | `financial:contas` | Idem | 100% | Nenhuma | — | Baixo |
| 27 | Financeiro — dashboard/análise (caixa × competência, gráficos SVG) | `financial:analise` | Idem | 100% | Nenhuma | — | Baixo |
| 28 | Relatórios — índice com 9 agregações | `reports:indice` | Idem | 100% | Nenhuma | — | Baixo |
| 29 | Etiquetas — seleção de produtos + preview | `labels:selecao/preview` | Idem | 100% | Nenhuma | — | Baixo |
| 30 | Etiquetas — impressão Elgin L42 (2/fileira) | `labels:imprimir` → agente | Agente embutido | 100% | Nenhuma | **Elgin L42 Pro Full (EPL2)** | Médio |
| 31 | Etiquetas — calibração | `labels:calibrar` | Idem | 100% | Nenhuma | Elgin L42 | Baixo |
| 32 | Etiquetas — configuração (dimensões, DPI) | `labels:configuracao` | Idem | 100% | Nenhuma | — | Baixo |
| 33 | Impressão — configuração (largura, cabeçalho) | `printing:configuracao` | Idem | 100% | Nenhuma | — | Baixo |
| 34 | Impressão — estações (criar/parear/desparear) | `printing:estacoes` | Adaptar: estação = o próprio desktop (pareamento 1 clique) | 95% (API de pair reutilizada) | Fluxo de pareamento simplificado | — | Médio |
| 35 | Impressão — status/polling de job | `printing:status_venda`, polling JS | Idem | 100% | Nenhuma | — | Baixo |
| 36 | Fiscal NFC-e — emissão/consulta/cancelamento | Admin + `FiscalService` | Manter no servidor; UI web no desktop apenas se desejado (hoje é admin) | 100% (SaaS central) | Status NFC-e no rodapé | **Certificado A1 no servidor** | Baixo (sem mudança) |
| 37 | Landing page + contato | `/` público | **Permanece web** (não pertence ao desktop) | 100% | — | — | N/A |
| 38 | Django Admin global | `/admin/` | **Permanece web** (uso administrativo da plataforma) | 100% | — | — | N/A |
| 39 | Onboarding de clientes SaaS | Admin | **Permanece web** | 100% | — | — | N/A |
| 40 | Auditoria | `audit.registrar` nos services | Automática (backend) | 100% | — | — | Baixo |
| 41 | Atalhos F2–F5, relógio, toasts | JS do shell/pdv | Mantidos; F-chaves também nativas (opcional) | 100% | Bind nativo opcional | — | Baixo |
| 42 | Notificações de erro/sucesso (messages) | Django messages → toasts | Idem | 100% | Nenhuma | — | Baixo |

> **Nota:** "Backend reutilizável = 100%" significa que a view, o service e o template atuais
> continuam rodando sem nenhuma alteração. A paridade funcional é **garantida por construção**
> (mesmo código executando), não por reimplementação.

### 3.2 Funcionalidades que hoje dependem de comportamento de navegador

| Comportamento | Mecanismo atual | Impacto no desktop |
|---|---|---|
| Leitor de código de barras USB | Keyboard wedge (digita + Enter) → form/busca | Funciona idêntico em webview; nada a fazer |
| Foco automático no campo de busca | `F2` via JS | Mantido; opcionalmente interceptado nativamente |
| Polling de impressão (3 s) | `fetch` + `setInterval` | Mantido (webview suporta); o shell pode substituir por notificação nativa |
| Popup/novas janelas | Não utilizado | Confirmar `window.open` bloqueado no shell (ok — não há uso) |
| Download do print-agent.exe | Link público GitHub Releases | Deixa de ser necessário (agente embutido) |
| Print nativo do navegador | Não utilizado (impressão é via agente) | N/A |

---

## 4. Dependências do Sistema

### 4.1 Python (backend — intocáveis)

Django 5.2, DRF 3.18 (sem uso atual), psycopg2, bcrypt, cryptography, signxml, lxml, requests,
gunicorn. Dev: ruff. Gerenciador: uv.

### 4.2 Externas / rede

| Dependência | Tipo | Comportamento offline |
|---|---|---|
| SEFAZ-SP (SOAP 1.2, TLS mútuo) | Crítica (fiscal) | NFC-e exige conexão — sem mudança |
| Tailwind Play CDN + Google Fonts | UI | **Risco real no desktop** (PDV pode rodar sem internet plena) → migrar para build estático local (pendência P2 já registrada em `tasks/MVP.md`) |
| PostgreSQL central | Dados | Sem conexão = sem operação (ver seção 14) |
| Cloudflare Tunnel / Nginx | Acesso | Idem |
| GitHub Releases (print-agent.exe) | Distribuição | Substituído pelo instalador do desktop |

### 4.3 Hardware

- Impressoras térmicas ESC/POS (Elgin/Bematech/Epson e Tomate MDK-080 modo texto).
- Elgin L42 Pro Full (etiquetas EPL2, 203 DPI, bobina 2/fileira).
- Leitor de código de barras USB HID (teclado) — transparente.
- Gaveta de dinheiro: **não há integração atual** (impressora com kick-out não configurado —
  investigar se necessário no futuro; o ESC/POS do agente não envia `ESC p` hoje).

---

## 5. Mapeamento Web → Desktop

| Elemento web | Equivalente desktop |
|---|---|
| Aba do navegador | Janela nativa (título, ícone, tamanho mínimo 1024×700 recomendado) |
| URL/barra de endereço | Nada (URL fixa do servidor ou modo embutido) |
| `pdv_shell.html` controles de janela decorativos | Controles nativos reais (minimizar/maximizar/fechar) — remover os decorativos |
| F5 refresh acidental | Bloquear/ignorar refresh (evita re-submissão de POST e perda de carrinho) |
| Toasts de `messages` | Mantidos + opção de notificações nativas do SO |
| "Sair" (form POST) | Mantido + item "Sair" no menu de bandeja |
| Relógio/data no rodapé | Mantido (JS) ou nativo |
| Status NFC-e "Conectado" | Mantido (indicador vem do backend) |
| Impressão | Agente embutido no mesmo processo (ou subprocesso) |
| Login | Mesma página; shell detecta `LOGIN_REDIRECT_URL` para mostrar/esconder janela |

---

## 6. Componentes Reutilizáveis

Classificação A/B/C/D:

### A — REUTILIZAR DIRETAMENTE (sem nenhuma alteração)

- **Todo o backend Django**: models, services, forms, views, urls, migrations, admin, signals,
  context processors, validadores, testes (456), configurações de produção (gunicorn/nginx/tunnel).
- **Todos os templates e JS**: `pdv_shell.html`, tela de venda, dashboards, formulários, modais,
  fetch/polling — são exatamente a UI do desktop.
- **`local-print-agent/app`** (agente): `client.py`, `escpos.py`, `receipt.py`, `labels.py`,
  `printer.py`, `config.py`, `agent.py` — reutilizados como biblioteca pelo shell.
- **Deploy do servidor**: `setup-pdv.sh`, systemd, nginx, cloudflared — inalterados.
- **CI do agente Windows** (pywin32, PyInstaller) — reaproveitado para o empacotador do desktop.

### B — REUTILIZAR COM ADAPTAÇÃO (pequenas alterações)

- `local-print-agent/app/main.py` — a CLI vira um módulo chamado pelo shell (o loop de polling
  roda em thread do shell; comandos `pair/test/raw-test/codepage-test/label-test` viram ações da UI
  de configuração).
- `pdv_shell.html` — remover controles de janela decorativos (substituídos por nativos); adicionar
  indicador "agente embutido" e estado offline; bloco para versão do shell.
- `base.html` — substituir Tailwind CDN por **build estático local** (necessário para offline e
  para CSP — já era pendência P2).
- `apps/printing` (fluxo de estações) — a estação do desktop pode ser auto-criada no primeiro
  pareamento, simplificando o onboarding da loja (sem perder o fluxo atual para outros PCs).
- API `/api/print-agent/*` — inalterada; apenas o cliente (shell) a consome agora.

### C — REIMPLEMENTAR (novo, mas pequeno)

- Shell desktop (`pdv-desktop/`): janela PyWebview, ciclo de vida, bandeja, menu, updater,
  detecção offline, atalhos globais, inicialização do agente embutido.
- Instalador/empacotamento (PyInstaller Linux `.deb`/AppImage e Windows `.exe`/MSI).
- Atualização automática (baixar release do GitHub Actions, verificar assinatura/sha256, reiniciar).

### D — REMOVER (justificativa técnica)

- `main.py` (resquício "Hello from pdv!" do scaffold uv, sem função no Django).
- Link/instruções de download do `print-agent.exe` nas telas — substituído por "agente embutido"
  (manter como fallback para máquinas sem o shell).
- Nada de regra de negócio é removido.

---

## 7. Componentes que Precisam ser Reescritos

Nenhuma **funcionalidade** precisa ser reescrita. Apenas a camada de "hospedagem":

1. **Shell de janela**: ~300–500 linhas Python (janela, bandeja, updater, agente em thread).
2. **Empacotamento**: specs PyInstaller para Linux (Debian 12 i686, 32-bit — atenção! ver seção
   16) e Windows 10/11.
3. **Tailwind build local**: adicionar etapa de build (tailwindcss standalone) — remove a
   dependência do CDN; zero mudança visual.
4. **Integração agente↔shell**: chamar `PrintAgent` existente a partir do shell, mantendo a API
   do servidor idêntica.

---

## 8. Alternativas de Arquitetura (Comparativo)

### 8.1 Tabela comparativa de tecnologias de shell

| Critério | PySide6 widgets nativos | PySide6 + QWebEngine | Electron | Tauri | **PyWebview** (recomendado) |
|---|---|---|---|---|---|
| Linguagem da equipe | Python ✓ | Python ✓ | JS ✗ | Rust ✗ | Python ✓ |
| Reescrita da UI (46 templates) | **Total** | Nenhuma | Nenhuma | Nenhuma | **Nenhuma** |
| Risco de regressão (456 testes cobrem backend+HTML) | Altíssimo | Mínimo | Mínimo | Mínimo | **Mínimo** |
| Binário instalado | ~60–90 MB | ~250 MB | ~200 MB | ~15–25 MB | **~25–40 MB** |
| Consumo de RAM em idle | Baixo | Alto (Chromium) | Alto (Chromium) | Baixo–médio | Médio (webview do SO) |
| Suporte Linux | ✓ | ✓ (pré-req extra) | ✓ | ✓ (webkit2gtk) | ✓ (webkit2gtk) |
| Suporte Windows | ✓ | ✓ | ✓ | ✓ (WebView2) | ✓ (WebView2/Edge) |
| Acesso a hardware via Python | ✓ | ✓ | ✗ (Node) | ✗ (Rust/plugins) | **✓** |
| Integração com print-agent existente (Python) | ✓ | ✓ | Ponte Node↔Python | Ponte Rust↔Python | **Direta (mesmo processo)** |
| Manutenção da UI (o dono investiu em Tailwind nas TSK_00011/13) | Perdida | Mantida | Mantida | Mantida | **Mantida** |
| Ciclo de atualização de UI (novas telas web) | Reimplementar sempre | Automático | Automático | Automático | **Automático** |
| Maturidade/licença | LGPL | LGPL | MIT | MIT/Apache | BSD-3 |

### 8.2 Por que NÃO Qt

1. **Qt Widgets puros**: seria reescrever todo o frontend (telas de PDV, dashboards SVG,
   preview de etiquetas, 46 templates, fluxos de POST/form) como widgets — meses de trabalho,
   altíssimo risco de divergência de comportamento e perda do design já aprovado (sidebar navy,
   cards, gráficos). O Qt moderno (QML/Qt Quick) exigiria aprender uma linguagem declarativa
   própria, fora da stack da equipe.
2. **Qt + QWebEngine**: resolve a UI (embute a web), mas arrasta um Chromium inteiro (~250 MB,
   RAM alta) duplicando o webview que o SO já fornece — desproporcional para máquinas de PDV
   (hardware simples; o próprio servidor de produção é i686 32-bit).
3. PyWebview atinge o mesmo resultado (webview nativo + pontes JS↔Python) com binário pequeno,
   sem dependência pesada, e mantém tudo em Python.

### 8.3 Por que NÃO Electron/Tauri

- **Electron**: outra linguagem (JS/Node), RAM/binário altos, mesma duplicação de engine.
- **Tauri**: excelente tecnologia, mas introduz Rust em uma equipe 100% Python (manutenção,
  contratação, CI); o ganho de tamanho binário não compensa o custo de manter dois mundos.

---

## 9. Arquitetura Recomendada

```
┌────────────────────────────── Desktop (loja) ──────────────────────────────┐
│  pdv-desktop (PyInstaller, Python 3.11)                                    │
│  ┌──────────────────────────────────────────────────────────────────────┐ │
│  │ PyWebview (WebKitGTK no Linux / WebView2 no Windows)                 │ │
│  │   └─ carrega https://<servidor>/app/  (mesmo Django de produção)     │ │
│  │      js_api bridge: print.status, shell.version, updater.*           │ │
│  ├──────────────────────────────────────────────────────────────────────┤ │
│  │ Thread: PrintAgent embutido (apps do local-print-agent reutilizados) │ │
│  │   polling /api/print-agent/poll  →  impressora ESC/POS / Elgin EPL2  │ │
│  ├──────────────────────────────────────────────────────────────────────┤ │
│  │ Updater (GitHub Releases + sha256), bandeja, atalhos globais,        │ │
│  │ detecção offline, página de erro amigável                            │ │
│  └──────────────────────────────────────────────────────────────────────┘ │
└───────────────────────────────┬────────────────────────────────────────────┘
                                │ HTTPS (Cloudflare Tunnel existente)
                        ┌───────▼────────┐
                        │ Django central │ (inalterado: SaaS multi-tenant,
                        │ PostgreSQL     │  admin, onboarding, NFC-e, fiscal)
                        └────────────────┘
```

**Regras da arquitetura:**

1. O Django **continua exatamente como está** — SaaS multi-tenant, um banco central, admin global,
   onboarding, NFC-e. A transformação não muda o modelo de negócio nem a produção.
2. O desktop é um **cliente rico**: mesma aplicação web, em janela nativa, com serviços locais
   (impressão, atualização, notificações).
3. A UI é a mesma para web e desktop (uma única base de código de interface) — novos recursos de
   UI continuam beneficiando os dois canais.
4. O agente de impressão pode continuar standalone (máquinas sem o shell) **ou** rodar embutido no
   shell (padrão no desktop). A API do servidor é a mesma nos dois casos.

### Por que manter o backend central (e não embutir Django em cada loja)

- O produto é um **SaaS multi-tenant em produção**: tenants compartilham infra, admin global
  gerencia todos, faturamento/onboarding centralizados. Embarcar Django+PostgreSQL por loja
  fragmentaria o sistema e exigiria sincronização bidirecional (alto risco, alto custo).
- NFC-e exige conexão com SEFAZ de qualquer forma (emissão online; contingência não implementada).
- Os prints agents já provam que o modelo cliente+servidor funciona em campo.
- **Alternativa considerada e adiada**: modo local com SQLite + fila de sincronização (seção 14).
  Decisão do proprietário necessária (seção 21, questão 1).

---

## 10. Estratégia para Banco de Dados

- **Sem mudança.** PostgreSQL central (produção), SQLite (dev).
- O shell desktop nunca acessa o banco diretamente — somente via HTTP/Django (igual hoje). Isso
  preserva isolamento multi-tenant, migrations únicas e backups centralizados.
- Cenario futuro (se aprovado): banco local SQLite por estação com sincronização — avaliar UUIDs
  (já usados em todas as entidades), timestamps de atualização, fila de operações pendentes e
  resolução de conflitos. **Não recomendado para a 1ª versão desktop** (ver seção 14).

---

## 11. Estratégia para Backend Django

**Manter 100% do backend, sem refatoração.** Ações concretas limitadas a:

1. **Nenhuma** mudança em models/services/views de negócio.
2. Ajustes pontuais e seguros (opcionais, item a item):
   - View/endpoint `health` para o shell detectar conectividade (ou reutilizar uma página
     existente).
   - `Vary`/cache já existentes (HTML `Cache-Control: no-cache` no nginx) são suficientes.
   - Emissão de header `X-PDV-Shell-Version` mínima (bloqueio suave de shell antigo, se desejado).
3. DRF declarado: **não usar** nesta etapa (nada a converter; o frontend usa forms/HTML).
4. Sessão: manter cookies de sessão atuais (o webview do SO gerencia cookies como o navegador);
   avaliar "lembrar dispositivo" com cookie persistente para login automático no shell.

---

## 12. Estratégia para Frontend Desktop

1. **Base**: reutilizar integralmente `pdv_shell.html` + Tailwind. O visual já foi projetado como
   desktop (sidebar, topbar, atalhos).
2. **Ajustes visuais mínimos**:
   - Remover os controles de janela decorativos do HTML (substituídos por nativos).
   - Substituir Tailwind CDN por build estático (compila os mesmos utilitários usados — sem
     mudança visual; permite offline e CSP).
   - Adicionar faixa/badge de "modo offline" e versão do shell no rodapé.
   - Fonte Inter: baixar e servir localmente (`@font-face`) — elimina Google Fonts.
3. **Interação desktop** (via `js_api` do PyWebview):
   - `shell.closeWindow()`, `shell.minimize()`, `shell.maximize()`.
   - `shell.printStatus(uuid)` → notificação nativa quando PRINTED/FAILED (substitui/apoia o
     polling de 3 s).
   - `shell.offline()` → página de aviso amigável com "Tentar novamente".
   - Atalhos F2–F5 permanecem em JS (já funcionam); nada a duplicar.
4. **Responsividade**: janela mínima ~1024×700; layouts atuais já funcionam nessa faixa.

---

## 13. Estratégia para Hardware e Impressão

| Dispositivo | Hoje | No desktop |
|---|---|---|
| Térmica ESC/POS 58/80 mm (USB) | Print Agent (`/dev/usb/lp0` ou spooler RAW) | **Mesmo código embutido no shell** — zero mudança de protocolo |
| Tomate MDK-080 (modo texto) | `PRINTER_ESCPOS=0`, codepage | Mantido (config do agente embutido) |
| Elgin L42 Pro Full (EPL2) | Agente `labels.py` | Mantido |
| Leitor código de barras USB HID | Keyboard wedge | Transparente (nada a fazer) |
| Gaveta de dinheiro | **Não integrada hoje** | Oportunidade futura: enviar `ESC p 0/1` no ESC/POS após comprovante — NECESSITA INVESTIGAÇÃO (hardware do cliente) |
| Balança (serial/USB) | Não existe hoje | Fora do escopo; ponto de extensão (bridge nativa pode ler porta serial) |
| Certificado A1 (fiscal) | Servidor (MEDIA_ROOT privado) | Inalterado |

**Pareamento no desktop:** o primeiro uso do shell pode gerar automaticamente uma `EstacaoImpressao`
(com o nome da máquina), apresentar o código de pareamento uma única vez e guardar credencial em
`~/.pdv-desktop/credencial.json` (0600) — reutilizando exatamente `parear_estacao`/`autenticar_estacao`
existentes. O fluxo atual (estação separada) permanece disponível.

---

## 14. Estratégia Offline/Online

**Recomendação para a 1ª versão: sempre online (cliente → servidor central).**

Justificativa:

- NFC-e exige SEFAZ online (autorização imediata; contingência não implementada por decisão de
  projeto — `agents.md` §4.4).
- O modelo SaaS central é o produto; offline-local exigiria sincronização bidirecional de
  inventário, vendas, financeiro e fiscal — projeto de meses, alto risco de conflito/duplicidade.
- Ganho prático baixo hoje (conexão já é obrigatória para o fiscal).

**O que a 1ª versão desktop entrega mesmo assim:**

- Detecção de queda de rede no shell (timeout → tela de erro amigável + "tentar novamente").
- Fila de impressão **já tolera offline** (jobs ficam PENDING no servidor; agente retoma ao
  reconectar — comportamento atual preservado).
- Tailwind/fontes locais (o app carrega sem depender de CDNs).

**Roadmap futuro (fora do escopo imediato):** modo offline com banco local SQLite + fila de
operação e sincronização (UUIDs já existem em todas as entidades; exigiria vetor de relógio ou
last-write-wins com confirmação, e tratamento de numeração de venda/NFC-e em contingência).
NECESSITA INVESTIGAÇÃO + aprovação do proprietário.

---

## 15. Segurança

**Preservado:**

- Multi-tenancy no backend (nunca confiado ao cliente), CSRF, bcrypt, sessões, throttle da API de
  impressão, token da estação com hash bcrypt, certificado A1 privado no servidor, logs sem
  segredos.

**Riscos introduzidos pelo desktop e mitigações:**

| Risco | Mitigação |
|---|---|
| Credencial da estação em disco (`credencial.json`) | Já é o padrão do agente: chmod 0600; manter em `~/.pdv-desktop/` |
| Cookies de sessão persistidos no webview | Webview do SO com perfil dedicado ao app; botão "Sair" limpa sessão; logout encerra janela |
| Shell antigo com falha conhecida | Versão mínima via header; updater obrigatório-opt-in |
| Update malicioso | Releases via GitHub + verificação sha256; assinatura de release (ação futura: codesign/notarização) |
| Expoção de js_api a conteúdo remoto | `js_api` expõe apenas funções whitelist (nada de acesso a arquivos/sistema); validar origem |
| Senha do certificado A1 | Continua só em env do servidor (SEFAZ_CERTIFICATE_PASSWORD) — nunca no desktop |
| Refresh/submissão dupla de POST no webview | Bloquear F5/reload no shell (evita re-finalizar venda) |
| Logs locais | Nível INFO, sem tokens/senhas (mesma política atual) |

---

## 16. Empacotamento e Distribuição

| Plataforma | Pacote | Notas |
|---|---|---|
| Linux (lojas Void/runit e Debian) | PyInstaller onefile + tarball e opcionalmente `.deb` | Servidor de produção é **i686 32-bit** — verificar arquitetura das máquinas das lojas; se 32-bit, construir com Python 3.11 i686 ou manter agente standalone nessas máquinas |
| Windows 10/11 | PyInstaller onefile (`.exe`) + instalador NSIS opcional | WebView2 já presente no Win10/11; pywin32 para spooler RAW (já usado no agente) |
| Atualização | GitHub Releases (mesmo fluxo do print-agent.exe) | Checksum sha256; download e reinício |
| Configuração inicial | Assistente no 1º uso: URL do servidor (default produção), pareamento da impressora, teste de impressão | Mesmo UX do agente atual |
| Arquivos locais | `~/.pdv-desktop/` (credencial, config, logs, cache de update) | Limpeza na desinstalação |
| Rollback | Manter 2 últimas versões no cache de update | Botão "restaurar versão anterior" no menu de bandeja |

CI: ampliar o workflow existente (`build-windows-agent.yml`) com jobs de build Linux + Windows do
shell, publicando na mesma release (tags `desktop-v*`).

---

## 17. Estratégia de Atualização

1. **Canal único:** releases do GitHub (`pdv-desktop-linux`, `pdv-desktop-windows.exe`).
2. **Checagem:** a cada inicialização e a cada 24 h, consultar a última release (API pública ou
   endpoint do próprio Django — preferir Django para evitar dependência de domínio externo).
3. **Aplicação:** baixar para cache, validar sha256, notificar o operador, aplicar no próximo
   restart (PDV nunca interrompe venda em andamento).
4. **Versão mínima:** header `X-PDV-Shell-Min-Version` — shell abaixo do mínimo mostra aviso
   bloqueante (decisão de produto).
5. **Rollback automático:** se o novo binário falhar 2× ao iniciar, restaurar versão anterior.

---

## 18. Estratégia de Testes

**Princípio:** como o backend e os templates não mudam, a paridade Web = Desktop é verificada
contra o **mesmo conjunto de testes existente** (456) + suíte nova focada no shell.

| Camada | Testes |
|---|---|
| Backend (inalterado) | `uv run python manage.py test` — 456 testes, gate obrigatório |
| Shell (novo) | `pdv-desktop/tests/`: unidade do bootstrap (config, updater sha256, js_api whitelist), teste de integração com `FakePrinterDevice` (agente embutido), smoke test do exe (igual CI do agente) |
| E2E visual | Piloto manual por módulo (checklist §24) em máquina real da loja, com impressora física |
| CI | Novo workflow: lint (ruff) + testes do shell + build Linux/Windows + smoke test dos exes |
| Regressão de UI | Screenshot comparativo (web vs webview) nas telas críticas (PDV, financeiro, etiquetas) — script simples com PyWebview em modo headless (se disponível no webview alvo) |

---

## 19. Plano de Migração (por módulos, item a item)

Cada fase é uma branch `feat/<task-id>-<descricao>` (fluxo git do projeto), com PR e revisão
humana. Nenhuma fase depende de reescrever backend.

### Fase 0 — Decisões e preparação

- **Objetivo:** resolver as questões da seção 21 (decisões do proprietário) e criar o esqueleto do
  pacote `pdv-desktop/`.
- **Arquivos:** `pdv-desktop/pyproject.toml`, estrutura de diretórios (§22), `tasks/TSK_00014*.md`.
- **Dependências:** pywebview, pyinstaller (dev).
- **Riscos:** nenhum (nenhum código de produção tocado).
- **Conclusão:** repositório do shell criado com testes vazios passando.
- **Testes:** `pytest` do shell rodando no CI.

### Fase 1 — Shell base (janela + carga do app)

- **Objetivo:** abrir o Django em janela nativa; título/ícone; tamanho mínimo; bloquear F5;
  detecção offline com tela amigável.
- **Arquivos:** `pdv-desktop/src/main.py`, `window.py`, `offline.html`.
- **Dependências:** Fase 0.
- **Riscos:** variação de webview entre SOs — testar cedo nos dois alvos.
- **Conclusão:** login → dashboard funcionando em janela nativa no Linux e Windows.
- **Testes:** unidade do bootstrap; smoke manual nos dois SOs.

### Fase 2 — Autenticação e sessão

- **Objetivo:** fluxo de login/logout no shell; opção "lembrar sessão"; "Sair" limpa cookies e
  encerra; redirecionamento correto quando deslogado.
- **Arquivos:** shell (`session.py`) + ajustes mínimos no template de login (CSS já existente).
- **Dependências:** Fase 1.
- **Riscos:** cookies em webviews Linux (WebKitGTK) vs Windows (WebView2) — testar persistência.
- **Conclusão:** login/logout idêntico ao web em ambos os SOs.
- **Testes:** manual + teste de integração do gerenciador de sessão.

### Fase 3 — Navegação e shell visual

- **Objetivo:** remover controles de janela decorativos; ligar botões a `js_api`; bandeja com
  abrir/fechar/sair; atalho global F2→busca.
- **Arquivos:** `pdv_shell.html` (remoção), `tray.py`, bridge.
- **Dependências:** Fase 2.
- **Riscos:** quebrar layout do shell web para quem usa pelo navegador → manter compatibilidade
  (controles decorativos só somem quando `window.pywebview` existe).
- **Conclusão:** shell desktop com janela nativa e bandeja; navegador continua igual.
- **Testes:** screenshots comparativos web vs desktop.

### Fase 4 — Módulo PDV/Vendas (prioridade máxima do negócio)

- **Objetivo:** garantir a tela de venda perfeita no desktop: atalhos F3/F4/F5, busca de produto
  com leitor USB, finalização com impressão embutida (Fase 6), cancelamento, caixa
  (abrir/fechar/suprimento/sangria).
- **Arquivos:** nenhum backend; testes de fluxo + ajustes pontuais de JS se necessário.
- **Dependências:** Fases 1–3 (impressão entra na Fase 6).
- **Riscos:** foco do teclado no webview (teclas F* e Enter do leitor) — validar captura.
- **Conclusão:** ciclo completo de venda no desktop = web (validação com checklist §24).
- **Testes:** script E2E manual + cenários automatizados no backend (já existentes).

### Fase 5 — Módulo Produtos

- **Objetivo:** listagem/busca assíncrona, cadastro/edição, geração EAN-13 + SVG, upload de
  imagem (opcional: diálogo nativo de arquivo via js_api), etiquetas a partir da listagem.
- **Arquivos:** templates existentes (sem mudança) + opcional bridge de diálogo.
- **Dependências:** Fase 3.
- **Riscos:** input file em webview — validar nos dois SOs.
- **Conclusão:** CRUD completo operando.
- **Testes:** checklist de paridade produtos.

### Fase 6 — Módulo Clientes

- **Objetivo:** CRUD + ativar/desativar + busca/filtros.
- **Arquivos:** nenhum (validação).
- **Dependências:** Fase 3.
- **Riscos:** baixo (telas 100% server-rendered, sem JS).
- **Conclusão:** fluxos completos.
- **Testes:** checklist de paridade clientes.

### Fase 7 — Módulo Estoque e Inventário

- **Objetivo:** dashboard, entradas/saídas, saldos, movimentações, histórico, inventários
  (contagem/divergências/finalização).
- **Arquivos:** nenhum backend; validação no shell.
- **Dependências:** Fase 3.
- **Riscos:** baixo.
- **Conclusão:** paridade total (regras de estoque negativo por tenant preservadas).
- **Testes:** checklist de paridade estoque.

### Fase 8 — Módulo Financeiro

- **Objetivo:** entradas/saídas/recebíveis/contas + dashboard com gráficos SVG.
- **Arquivos:** nenhum backend.
- **Dependências:** Fase 3.
- **Riscos:** baixo; conferir renderização dos SVGs no WebKitGTK.
- **Conclusão:** paridade.
- **Testes:** checklist de paridade financeiro.

### Fase 9 — Módulo Relatórios

- **Objetivo:** índice completo de relatórios com filtros.
- **Arquivos:** nenhum backend.
- **Dependências:** Fase 3.
- **Riscos:** baixo.
- **Conclusão:** paridade.
- **Testes:** checklist de paridade relatórios.

### Fase 10 — Impressão (agente embutido) — crítica

- **Objetivo:** rodar o PrintAgent existente dentro do shell (thread); pareamento em 1 clique;
  status nativo; comprovante e etiquetas; manter agente standalone como fallback.
- **Arquivos:** `pdv-desktop/src/print_embedded.py` (reutiliza `local-print-agent/app`),
  ajustes em `apps/printing/templates/*` (UI de pareamento), nenhuma mudança em
  `apps/printing/services|api`.
- **Dependências:** Fases 1, 4, 11 (etiquetas junto).
- **Riscos:** comunicação shell↔agente (buffer, threads); bloqueio da UI; portas USB no Windows.
- **Conclusão:** venda finalizada imprime sem agente externo; status PRINTED/FAILED na tela.
- **Testes:** `FakePrinterDevice` + teste real em impressora física; reexecutar testes do agente.

### Fase 11 — Módulo Etiquetas

- **Objetivo:** seleção/preview/impressão/calibração via agente embutido.
- **Arquivos:** nenhum backend; validação.
- **Dependências:** Fase 10.
- **Riscos:** EPL2 via spooler RAW no Windows (já validado pelo agente atual).
- **Conclusão:** paridade com o fluxo atual.
- **Testes:** reexecutar `local-print-agent/tests` + teste físico Elgin.

### Fase 12 — Fiscal NFC-e (sem mudança)

- **Objetivo:** confirmar que emissão/consulta/cancelamento continuam operando pelo servidor
  (fluxo atual via admin); indicador "Conectado" no rodapé; nenhuma mudança de código fiscal.
- **Arquivos:** nenhum.
- **Dependências:** Fase 4 (finalização dispara NFC-e no servidor se configurada — verificar
  integração atual da finalização com `FiscalService`; hoje a emissão é via admin —
  **NECESSITA INVESTIGAÇÃO**: qual o gatilho de emissão em produção?).
- **Riscos:** nenhum novo.
- **Conclusão:** NFC-e inalterada.
- **Testes:** homologação SEFAZ existente.

### Fase 13 — Empacotamento e CI

- **Objetivo:** builds PyInstaller Linux + Windows; workflow GitHub Actions; releases
  `desktop-v*`; instalador/assistente de 1º uso.
- **Arquivos:** specs, workflow `.github/workflows/build-desktop.yml`.
- **Dependências:** Fases 1–12 estáveis.
- **Riscos:** 32-bit Linux (i686) — validar necessidade com o cliente piloto.
- **Conclusão:** exe/AppImage instaláveis nas lojas.
- **Testes:** smoke test dos binários no CI (padrão do print-agent).

### Fase 14 — Atualização automática

- **Objetivo:** updater com sha256, notificação, aplicação no restart, rollback.
- **Arquivos:** `updater.py`.
- **Dependências:** Fase 13.
- **Riscos:** baixo (isolado).
- **Conclusão:** atualização testada em máquina piloto.
- **Testes:** unidade (download/verificação) + manual.

### Fase 15 — Testes de paridade e piloto

- **Objetivo:** executar a checklist §24 em 1 loja piloto, lado a lado com o web.
- **Arquivos:** nenhum; roteiro de validação.
- **Dependências:** Fase 14.
- **Riscos:** achados de campo → ajustes antes do rollout.
- **Conclusão:** assinatura do proprietário para rollout.

### Fase 16 — Produção e rollout

- **Objetivo:** distribuição para as lojas; suporte com diagnóstico (`codepage-test`,
  `raw-test` via UI); monitoramento (cron `check_print_agents` já existente).
- **Arquivos:** docs de uso/instalação.
- **Dependências:** Fase 15 aprovada.
- **Riscos:** suporte a hardware heterogêneo.
- **Conclusão:** todas as lojas no desktop.

---

## 20. Riscos

| Risco | Prob. | Impacto | Mitigação |
|---|---|---|---|
| Regressão funcional na migração | Baixa | Crítico | Backend/templates intocados; paridade por construção; 456 testes + checklist |
| Variabilidade de webview (WebKitGTK vs WebView2) | Média | Médio | Testes cedo nos dois SOs (Fase 1); CSS sem APIs experimentais |
| Impressão embutida conflitar com agente standalone | Média | Médio | Dedupe por uuid já existe; documentar "não rodar os dois" ou detectar instância em execução |
| Hardware loja 32-bit Linux | Média | Médio | Verificar com lojas; manter agente standalone para essas máquinas |
| Tailwind CDN indisponível/offline | Média | Médio | Build estático local (Fase preparatória) — já era pendência |
| Foco/teclado no webview (F*, leitor USB) | Média | Alto (PDV) | Validar na Fase 4 antes de qualquer rollout |
| Quebra do fluxo web para quem usa navegador | Baixa | Médio | Compatibilidade: mudanças condicionais a `window.pywebview` |
| Expectativa errada de "desktop = local sem internet" | Média | Alto | Decisão explícita do proprietário (seção 21) antes da implementação |
| Update quebrado em campo | Baixa | Alto | sha256 + rollback automático |
| Servidor central indisponível (impacta todos) | Baixa | Alto | Não muda com o desktop; manter estratégia atual |

---

## 21. Problemas que Precisam ser Resolvidos Antes da Implementação

1. **Modelo de dados: central (recomendado) ou local por loja?** O desktop mantém o SaaS central
   (minha recomendação técnica) ou o objetivo de produto é vender um aplicativo standalone com
   banco local? Isso muda toda a arquitetura (seção 14). DECISÃO DO PROPRIETÁRIO.
2. **SO das lojas:** confirmar Windows 10/11 e/ou Linux (Void/Debian?) e arquitetura (32/64-bit)
   das máquinas de PDV reais.
3. **Gatilho de emissão NFC-e:** hoje a emissão parece ser via Django Admin. O desktop deve
   acionar emissão na finalização da venda? NECESSITA INVESTIGAÇÃO (código atual: `FiscalService`
   sem views próprias).
4. **Gaveta de dinheiro:** integrar kick-out (`ESC p`) agora ou depois? NECESSITA INVESTIGAÇÃO de
   hardware em campo.
5. **Janela única vs múltiplas janelas:** PDVs às vezes precisam de duas telas (operador +
   cliente). Definir escopo da v1.
6. **Pendências já registradas** (`tasks/MVP.md`): Tailwind build/CSP, rate limiting de login,
   senha do admin de produção, cron de monitoramento, cadastro do Emitente — recomendo resolver
   as duas primeiras dentro da migração (Tailwind local é pré-requisito da Fase 0).

---

## 22. Estrutura de Diretórios Proposta

```
pdv/
├── (estrutura atual INTOCADA: apps/, config/, frontend/, local-print-agent/, deploy/, ...)
├── pdv-desktop/                      # NOVO — shell desktop
│   ├── pyproject.toml                # pywebview, pyinstaller (dev)
│   ├── launcher.py                   # entry point PyInstaller (padrão do print-agent)
│   ├── src/
│   │   └── pdv_desktop/
│   │       ├── __init__.py
│   │       ├── main.py               # bootstrap: parse args, config, inicia janela+agente
│   │       ├── config.py             # ~/.pdv-desktop/config.json, env PDV_DESKTOP_*
│   │       ├── window.py             # janela PyWebview, js_api bridge (whitelist)
│   │       ├── tray.py               # bandeja/menu nativo
│   │       ├── offline.html          # tela de erro/offline amigável
│   │       ├── session.py            # perfil de cookies, lembrar sessão
│   │       ├── updater.py            # checagem, sha256, rollback
│   │       └── print_embedded.py     # thread do PrintAgent reutilizando local-print-agent/app
│   └── tests/
│       ├── test_bootstrap.py
│       ├── test_updater.py
│       ├── test_bridge.py
│       └── test_print_embedded.py    # FakePrinterDevice
├── packaging/
│   ├── linux.spec                    # PyInstaller
│   └── windows.spec
├── .github/workflows/
│   └── build-desktop.yml             # CI: lint, test, build Linux+Windows, smoke, release
└── docs/
    ├── migracao-desktop.md           # este documento
    └── desktop-<fase>.md             # docs por fase, conforme padrão do projeto
```

---

## 23. Dependências Novas Necessárias

| Dependência | Uso | Justificativa |
|---|---|---|
| `pywebview>=5` (BSD-3) | Janela nativa + js_api | Webview nativo do SO; binário leve; Python puro |
| `pyinstaller` (dev) | Empacotamento | Já usado no print-agent (padrão do projeto) |
| `pywin32` (Windows) | Spooler RAW | Já usado no print-agent |
| TailwindCSS standalone (build-time) | Compilar CSS estático | Substitui o Play CDN (pré-requisito offline/CSP) |

**Sem novas dependências no backend Django.** Nada de React/Vue/Node/Rust.

---

## 24. Checklist Final de Paridade (Web = Desktop)

Como backend e templates são os mesmos, a checklist valida **execução e ambiente**, não regras.
Regras de negócio, cálculos, validações e permissões são idênticos por construção (mesmo código,
mesmo banco, mesmos testes).

### Autenticação
- [ ] Login com usuário da loja funciona igual
- [ ] Login de cliente da plataforma (e-mail) funciona igual
- [ ] Senha inválida → mesma mensagem genérica
- [ ] Logout encerra sessão e limpa cookies no webview
- [ ] Sessão lembrada persiste entre aberturas (quando habilitada)
- [ ] Usuário sem tenant é redirecionado igual

### PDV / Vendas / Caixa
- [ ] Abrir caixa (saldo inicial, conta e formas padrão)
- [ ] Regra "um caixa aberto por operador" mantida
- [ ] Nova venda reutiliza caixa aberto / abre automaticamente
- [ ] Adicionar item (congela preço; merge de quantidades; produto inativo bloqueado)
- [ ] Busca por nome/SKU/código de barras com leitor USB (Enter)
- [ ] F2 (busca), F3 (desconto), F4 (cliente), F5 (receber) funcionam
- [ ] Desconto validado no backend (0 ≤ desconto ≤ subtotal)
- [ ] Pagamento: formas por tenant, taxa (bruto/líquido), rejeição de excedente, troco
- [ ] Finalização: itens obrigatórios, pagamentos = total, financeiro (conta a receber × entrada
  no caixa) idêntico
- [ ] Impressão do comprovante dispara e estados PENDING→PROCESSING→PRINTED/FAILED aparecem
- [ ] Cancelar venda exige motivo e estorna financeiro igual
- [ ] Fechar caixa: bloqueio com vendas abertas, diferença, movimentações
- [ ] Suprimento/sangria idênticos

### Produtos
- [ ] Listagem/busca assíncrona (debounce) igual
- [ ] CRUD + validações (SKU/barras únicos por tenant, EAN-13 com DV, NCM/CEST/CFOP dígitos)
- [ ] Gerar código de barras EAN-13 interno + SVG renderiza
- [ ] Upload de imagem (tipos, 5 MB) igual
- [ ] Ativar/desativar (soft delete) igual

### Clientes
- [ ] CRUD + busca/filtros + ativar/desativar
- [ ] CPF/CNPJ único por tenant (constraint) igual

### Estoque / Inventário
- [ ] Entrada/saída/ajuste com movimentação e saldo anterior/posterior
- [ ] Regra `permitir_estoque_negativo` por tenant mantida
- [ ] Inventário: contagem congelada, revisão, divergências, finalização com ajustes
- [ ] Histórico do produto igual

### Financeiro
- [ ] Entradas/saídas: receber/pagar/cancelar/estornar com estornos referenciando original
- [ ] Contas a receber: parcelamento 1–48, receber parcela (PARCIAL/RECEBIDA), cancelar
- [ ] Cadastro de contas/categorias/formas por tenant
- [ ] Dashboard/análise: mesmos números, gráficos SVG renderizam

### Relatórios
- [ ] Todos os 9 blocos de agregação com filtros por tenant iguais

### Etiquetas / Impressão
- [ ] Seleção de produtos → preview (2/fileira, aviso de posição vazia)
- [ ] Impressão via agente embutido (EPL2) igual ao agente standalone
- [ ] Calibração idêntica
- [ ] Pareamento/despareamento da estação
- [ ] Configurações (largura 58/80, cabeçalho, mensagem final, dimensões etiqueta)

### Ambiente desktop
- [ ] F5/reload não ressubmete POST
- [ ] Janela nativa minimiza/maximiza/fecha corretamente
- [ ] Offline → tela amigável; reconexão retoma (fila de impressão preservada)
- [ ] Atualização automática não interrompe venda em andamento
- [ ] Logs locais sem segredos

---

## Anexo A — Métricas do estudo

- 15 apps Django · ~19.000 linhas de Python (8.500 em models/views/services) · 46 templates
- 456 testes automatizados OK (227 s) · 13 tasks documentadas (TSK_00001–00013) implementadas
- Produção: Debian 12 i686, PostgreSQL 15, gunicorn 3×2, Nginx, Cloudflare Tunnel
- Print Agent: cliente stdlib, dedupe local, ESC/POS + EPL2, Linux/Windows, CI com teste E2E do exe

## Anexo B — Decisões do proprietário (resolvidas em 2026-08-28)

1. **Modelo de dados: CENTRAL (SaaS como hoje).** Desktop = cliente rico conectado ao servidor
   Django central existente. Zero mudança de backend/banco; produção preservada. (Decisão §21.1)
2. **SOs alvo: LINUX E WINDOWS (64-bit).** Builds dos dois desde a Fase 1, como o print-agent.
   (Decisão §21.2)
3. **Gatilho NFC-e: INVESTIGAR NA FASE 12.** Sem mudança de regra fiscal agora; relatório ao
   final da investigação. (Decisão §21.3)
4. **Gaveta de dinheiro: NÃO INTEGRAR.** Nenhum comando `ESC p` será adicionado. (Decisão §21.4)
5. **Janela única na v1.** Multi-janela fica para extensão futura. (Decisão §21.5)

Estas decisões desbloqueiam a Fase 0. As pendências internas restantes (Tailwind build, rate
limiting de login) seguem o plano da seção 21.6.

---

**Próximo passo:** aguardar autorização explícita do proprietário para iniciar a Fase 0. Nenhum
código foi alterado neste estudo.
