# Adaptação do backend ao novo frontend (TSK_00012)

A TSK_00012 especificava originalmente um backend novo em
Node.js/NestJS/Prisma. Por decisão do proprietário, o escopo foi
**adaptado ao stack original do projeto** (Django + PostgreSQL, sem
duplicar arquitetura): o objetivo é o backend dar suporte completo às
telas redesenhadas na TSK_00011.

## O que foi implementado

### 1. Clientes do tenant (`apps/customers`)

A sidebar já exibia "Clientes" e o PDV tinha o botão "Cliente (F4)",
mas não existia módulo de clientes do lojista.

- `Cliente`: nome, CPF/CNPJ (único por tenant quando informado), e-mail,
  telefone, endereço completo, observações e status (ativo/inativo).
- CRUD completo (`/app/clientes/`) com listagem paginada e busca por
  nome/CPF/e-mail/telefone, formulário em cards e tela de detalhe com
  ativação/desativação.
- Regras em `services.py` com auditoria (`registrar`) e validações no
  backend; registro no Django Admin com list_display, filtros e ações.
- Sidebar: o item "Clientes" agora aponta para o módulo real.

### 2. Vendas (`apps/sales`)

- `Venda.cliente`: FK para `Cliente` (opcional) + `cliente_nome`
  mantido como snapshot congelado na venda.
- Ação `acao=cliente` no PDV: aceita cliente cadastrado (uuid, validado
  contra o tenant) **ou** nome informado manualmente. Cliente de outro
  tenant é rejeitado.
- Ação `acao=alterar_item`: altera a quantidade de um item com o
  subtotal sempre recalculado no backend (nunca confiando no frontend).
- Carrinho do PDV com botões +/− para quantidade e modal de cliente com
  seleção de clientes cadastrados.

### 3. Produtos (`apps/products`)

- `Produto.codigo`: código interno gerado automaticamente pelo backend,
  sequencial por tenant (6 dígitos) — o campo "Código do produto" da
  tela exibe "Automático" no cadastro e o código real na edição.
- Campos fiscais novos: `cest` (7 dígitos), `cfop` (4 dígitos) e
  `origem` (0–8), exibidos no card recolhível "Informações fiscais".
- `Produto.margem_lucro`: propriedade calculada (margem sobre o preço
  de venda).
- Validações: NCM/CEST/CFOP apenas dígitos; migração `0004`.

### 4. Relatórios (`apps/reports`)

A sidebar exibia "Relatórios" sem destino. Novo módulo em
`/app/relatorios/` com filtros por período, produto, categoria,
operador, caixa e forma de pagamento:

1. Vendas por período (total, nº de vendas, ticket médio e por dia);
2. Vendas por produto;
3. Vendas por categoria;
4. Vendas por operador;
5. Vendas por forma de pagamento;
6. Estoque atual;
7. Produtos com estoque baixo;
8. Fechamentos de caixa (esperado × informado × diferença);
9. Movimentações financeiras.

Tudo com agregações SQL (sem carregar vendas individualmente) e
isolamento por tenant em todas as consultas.

### 5. Item ativo da sidebar

Novo context processor `apps.core.context_processors.sidebar_ativa`
deriva o item ativo do caminho da URL (nunca de dados do frontend).

## Decisões de arquitetura

- **Sem REST/DRF**: as telas são server-rendered (Django Templates +
  Tailwind); o backend calcula tudo e o frontend apenas exibe.
- **Isolamento multi-tenant**: todos os filtros dos relatórios e as
  ações do PDV validam os objetos contra o tenant do usuário
  autenticado; nenhum parâmetro do frontend é confiado.
- **Integridade**: alterações de item e associação de cliente rodam em
  transações com `select_for_update()`; códigos de produto usam
  constraint de unicidade por tenant.

## Testes

- `apps/customers/tests`: serviços e views (CRUD, isolamento, status).
- `apps/sales/tests`: cliente por nome/uuid, cliente alheio rejeitado,
  alteração de quantidade (recálculo e validação).
- `apps/products/tests`: código sequencial automático, campos fiscais,
  validações e margem calculada.
- `apps/reports/tests`: renderização, isolamento entre tenants,
  filtros por produto e forma de pagamento, estoque baixo e
  fechamentos de caixa.

Suíte completa: 443 testes passando.
