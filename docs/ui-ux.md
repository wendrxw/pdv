# UI/UX — Shell e telas redesenhadas (TSK_00011)

## Visão geral

As telas operacionais do PDV ganharam uma identidade visual única,
desktop-first (16:9), inspirada em sistemas ERP/POS comerciais:

- **Sidebar** azul-marinho com logo, menu vertical e "Versão 1.0.0";
- **Barra superior** branca com busca rápida (atalho F2), operador/caixa e
  controles de janela;
- **Rodapé** com status NFC-e ("Conectado"), relógio e data em tempo real;
- Paleta: azul-marinho (navegação), azul vibrante (ações e preços), verde
  (pagamento/positivo), vermelho (destrutivo), branco e cinza claro.

## Arquivos

| Arquivo | Papel |
| --- | --- |
| `frontend/templates/base.html` | Fonte Inter, paleta `navy` e config do Tailwind (CDN) |
| `frontend/templates/pdv_shell.html` | Shell compartilhado (sidebar, topbar, toasts, rodapé, F2, relógio) |
| `frontend/templates/partials/icon.html` | Ícones SVG lineares (estilo lucide), sem dependências externas |
| `apps/sales/templates/sales/venda.html` | Tela de venda (catálogo + carrinho + resumo + modais) |
| `apps/sales/templates/sales/pdv.html` | Frente de caixa no novo shell |
| `apps/products/templates/products/formulario.html` | Cadastro de Produto em cards (70/30) |
| `apps/financial/templates/financial/dashboard.html` | Controle Financeiro (KPIs, gráficos SVG, tabelas) |
| `apps/financial/templates/financial/_filtros_ocultos.html` | Persiste filtros ao trocar período |

## Tela de venda (PDV)

- Catálogo real do tenant: categorias (filtro por `?cat=`), grade de 3
  colunas com imagem/nome/preço/estoque e paginação (9 produtos por página).
- Carrinho mantém os POSTs server-side existentes (`add_item`,
  `remover_item`, `desconto`, `cancelar`, `finalizar`).
- Novo: ação `acao=cliente` define `Venda.cliente_nome` (venda aberta).
- Atalhos: F2 foca a busca (Enter adiciona o primeiro resultado), F3
  desconto, F4 cliente, F5 receber (fluxo de confirmação em duas etapas).
- "Limpar venda" cancela com justificativa obrigatória (regra preservada).

## Cadastro de Produto

- Cards: Informações básicas, Preços e estoque, Informações fiscais
  (recolhível), Imagem do produto, Outras informações.
- Margem de lucro calculada no frontend (somente exibição).
- Upload de imagem com drag-and-drop; validações: PNG/JPG/WEBP, máx. 2MB.
- Novos campos no model `Produto`: `ncm` (8 dígitos) e `imagem`
  (`FileField` com upload isolado por tenant — `produtos/<tenant>/<uuid>/`).
- "Estoque atual" é somente leitura; no modo edição exibe o saldo real.

## Controle Financeiro

- Períodos: Hoje, Ontem, Esta semana, Este mês, Últimos 7/30 dias e
  Período personalizado (`?periodo=`).
- Filtros: forma de pagamento, categoria, operador, caixa e status da
  transação — todos validados contra o tenant e aplicados via
  `financial.services.resumo_controle` (vendas do PDV como fonte).
- Indicadores: recebido hoje/semana/mês com variação percentual e total
  do período; série diária, donut por forma de pagamento e resumos por
  dia/categoria.
- Gráficos renderizados em SVG/JS vanilla (sem bibliotecas), com
  agrupamento Diário/Semanal/Mensal e tooltip.

## Backend

- `apps/sales/views.py`: catálogo paginado no contexto da venda e ação
  `cliente`.
- `apps/financial/services.py`: `resumo_controle()` com isolamento por
  tenant e validação de filtros (`FinancialError`).
- `apps/financial/views.py`: presets de período e filtros do dashboard.
- `apps/products/`: fields `ncm`/`imagem` (migração
  `products/0003_produto_imagem_produto_ncm`), validações no form, upload
  via `request.FILES` e admin atualizado.
- `config/urls.py`: serve `MEDIA_URL` em desenvolvimento (DEBUG).

## Segurança e multi-tenancy

- Nenhum dado é carregado sem o filtro de tenant; filtros do dashboard são
  resolvidos via `for_tenant()` e nunca confiados ao frontend.
- Upload de imagem: validação de extensão/tamanho no backend e caminho
  isolado por tenant.

## Testes

- `ResumoControleTest` (financial): recebidos, canceladas, isolamento,
  formas de pagamento, filtros, série e resumo diário.
- `ProdutoImagemENcmTest` (products): validação de NCM e imagem.
- Sales: ação `cliente` e catálogo na tela de venda.
- `test_cards_presentes` atualizado para o novo dashboard.
