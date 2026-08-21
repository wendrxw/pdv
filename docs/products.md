# Produtos, Estoque e Inventário

Implementação das fases 2–5 de `docs/general.md` (módulo de Produtos,
Estoque e Inventário), dividida nas tasks TSK_00002 a TSK_00005.

## Aplicações

- `apps/products`: Categoria, Marca, Produto, BarcodeService/Renderer.
- `apps/inventory`: Fornecedor, Estoque, MovimentacaoEstoque, Inventario,
  InventarioItem + services.

Todos os models herdam de `TenantAwareModel` — isolamento garantido no
backend (`for_tenant()`); UUID/SKU/código de barras nunca isolam dados.

## Produtos

- Identificadores distintos: **uuid** (técnico, global), **sku**
  (interno/comercial, único por tenant, opcional) e **codigo_barras**
  (leitura no PDV, único por tenant, opcional).
- Preços com `DecimalField(12,2)` não negativos; quantidades com
  precisão de 3 casas (produtos fracionados, ex.: KG).
- Soft delete via `ativo=False`; produtos com histórico nunca são
  removidos fisicamente.
- Regras de negócio exclusivamente em `ProductService`; views apenas
  orquestram.
- Campos fiscais (NCM, CEST, CFOP...) ficam para o módulo fiscal em
  estrutura separada — decisão documentada para não poluir o model.

### Código de barras (EAN-13 interno)

- `BarcodeService.generate()` gera códigos com **prefixo 2** (faixa GS1
  de uso interno da loja). Não são GTINs registrados — o sistema deixa
  isso explícito na UI.
- Dígito verificador calculado no backend; código informado manualmente
  é validado; unicidade por tenant via constraint condicional.
- Códigos de produtos desativados não são reutilizados.
- `BarcodeRenderer.to_svg()` renderiza SVG dinamicamente (a imagem não é
  armazenada; o número é a fonte da verdade).
- Botão "Gerar código" no formulário usa endpoint POST/JSON; o código
  definitivo sempre passa por revalidação server-side.
- Busca da listagem aceita nome, SKU ou código (compatível com leitor
  USB HID que digita o código).

## Estoque

- **Estoque** mantém o saldo atual; **MovimentacaoEstoque** é o histórico
  imutável com saldo_anterior/saldo_posterior. Nunca alterar
  `estoque.quantidade` fora do `EstoqueService`.
- Tipos explícitos: ENTRADA, SAIDA, AJUSTE_POSITIVO, AJUSTE_NEGATIVO,
  VENDA, DEVOLUCAO, CANCELAMENTO_VENDA, INVENTARIO.
- `EstoqueService` opera sob `transaction.atomic()` +
  `select_for_update()`: saldo e movimentação nascem na mesma transação.
- Regra de estoque negativo configurável por tenant
  (`Tenant.permitir_estoque_negativo`, padrão False). Saída sem saldo
  gera `EstoqueError` e rollback completo.
- Concorrência: duas vendas simultâneas consomem no máximo o saldo
  disponível (testado em `test_vendas_simultaneas_nao_geram_negativo`;
  em PostgreSQL via lock de linha, em SQLite via serialização de escrita).
- Integridade (§42): qualquer saldo é reconstruível pelas movimentações;
  a tela "Histórico" do produto responde "como este produto chegou ao
  estoque atual?".
- Dashboard `/app/estoque/`: totais, sem estoque, estoque baixo, valor
  estimado por custo e venda, últimas movimentações/produtos.

## Inventário

Fluxo: ABERTO → EM_CONTAGEM → EM_REVISAO → FINALIZADO (ou CANCELADO a
qualquer momento antes da finalização).

- Ao criar cada item, o saldo do sistema é **congelado** como referência
  (`quantidade_sistema`). Vendas durante a contagem não alteram essa
  base — estratégia documentada no model.
- Contagem em lote na página própria; divergência = contada − sistema.
- Finalização transacional: cada item contado gera movimentação
  INVENTARIO levando o saldo à quantidade física (via EstoqueService);
  itens sem contagem são ignorados. Cancelamento não aplica ajustes.
- Inventários FINALIZADO/CANCELADO são imutáveis.

## URLs (todas exigem login e tenant)

```
/app/produtos/                     listagem (busca, filtros, paginação)
/app/produtos/novo/
/app/produtos/<uuid>/              detalhe (com código de barras)
/app/produtos/<uuid>/editar/
/app/produtos/<uuid>/alternar-status/   POST
/app/produtos/gerar-codigo-barras/      POST JSON
/app/produtos/<uuid>/codigo-barras.svg  imagem SVG
/app/estoque/                      dashboard
/app/estoque/entrada/  /app/estoque/saida/
/app/estoque/movimentacoes/  /app/estoque/saldos/
/app/estoque/produtos/<uuid>/      histórico do produto
/app/inventarios/                  lista
/app/inventarios/novo/
/app/inventarios/<uuid>/           detalhe/status
/app/inventarios/<uuid>/contagem/
/app/inventarios/<uuid>/divergencias/
/app/inventarios/<uuid>/finalizar/ POST
```

Usuários da plataforma (sem tenant) são redirecionados ao dashboard com
mensagem informativa. Operações destrutivas usam POST + CSRF.

## Testes

`apps/products/tests/` (45) e `apps/inventory/tests/` (36): isolamento
multi-tenant, validações, barcode (dígito verificador, unicidade,
renderização), movimentações, estoque negativo, rollback transacional,
concorrência e ciclo completo do inventário.
