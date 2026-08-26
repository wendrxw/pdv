# Etiquetas de Produtos — Elgin L42 Pro Full

Módulo de seleção, visualização e impressão de etiquetas de produtos
(`apps/labels` + suporte no Local Print Agent).

## Arquitetura (mesma dos comprovantes)

A Elgin L42 Pro Full fica na LOJA, conectada por USB na mesma máquina do
Local Print Agent. O servidor NUNCA toca a impressora: gera
`EtiquetaJob`s com as fileiras prontas; o agente faz polling, converte
para EPL2 e escreve no dispositivo.

```
PDV → Produtos (buscar/selecionar) → Preparar impressão
        ↓
Etiquetas: quantidades + ordem + PREVIEW (fileiras da bobina)
        ↓
Confirmar impressão → EtiquetaJob (payload com fileiras)
        ↓ API /api/print-agent/etiquetas/ (poll/resultado, token da estação)
Local Print Agent → EPL2 → PRINTER_LABEL_DEVICE (ex.: /dev/usb/lp1)
        ↓
Elgin L42 Pro Full (203 DPI, 2 etiquetas por fileira)
```

A regra de consistência é estrutural: **o preview e a impressão usam a
mesma estrutura de dados** (`fileiras` no payload) — o que aparece na
tela é exatamente o que vai para a impressora.

## Regras da bobina

- A bobina tem **2 etiquetas lado a lado por fileira física**.
- A lógica monta uma **lista linear** de etiquetas e depois agrupa em
  **pares** (`agrupar_em_fileiras`).
- 1 etiqueta = 1 posição + 1 posição **vazia** (a fileira é consumida —
  aviso na tela e na confirmação).
- 2 etiquetas = 1 fileira completa; 3 = 2 fileiras (última parcial);
  4 = 2 fileiras completas.
- Quantidade ímpar → última posição vazia (aviso no preview).
- A ordem é a ordem da lista de impressão (reordenável com ▲/▼).

## Fluxo no PDV

1. **Produtos** → campo "Buscar produto..." (nome, SKU, código de barras —
   atualização em tempo real via `products:busca`, sem recarregar).
2. Checkboxes individuais + "Selecionar todos" + mensagem
   "Nenhum produto encontrado." quando vazio.
3. **Preparar impressão de etiquetas** → tela de preparação com
   quantidade individual, ordem e **preview da bobina** (2 por fileira,
   vazias explícitas, resumo: produtos/etiquetas/fileiras/posições
   vazias).
4. **Confirmar impressão** → `EtiquetaJob` (PENDING) → tela de status
   com polling ("Aguardando agente…", "Imprimindo...", ✓, ⚠ + Tentar
   novamente).
5. **Calibrar etiquetas** → job de calibração (moldura + código de teste
   nas duas colunas) para validar sensor, offsets e leitura do código.

## Configuração da impressora (por loja)

`Etiquetas → Configuração`: largura/altura de cada etiqueta, gaps
horizontal/vertical, margens, offsets, DPI (203) e quantidade padrão.
Valores em mm; a conversão para dots é feita no agente
(`mm × DPI / 25,4`). Padrões iniciais: 40×30mm, gaps 2mm, margens 2/1mm
— ajustar conforme o rolo real e validar com a calibração.

## EPL2 (agente)

A L42 Pro fala **EPL2**. O agente gera para cada fileira:

```
N  (limpa)  D8 (densidade 203)  q<largura>  Q<altura>,<gap>  P2
[etiqueta esquerda: textos A + código B (Code 128)] P1
[etiqueta direita (ou vazia)]                        P1
```

- Código de barras **Code 128** com largura estreitada automaticamente
  para nunca ultrapassar a área da etiqueta; texto abaixo opcional
  (`mostrar_texto_codigo`).
- Nomes com acento vão em latin-1 (tabela estendida da Elgin).
- Variáveis do agente:
  - `PRINTER_LABEL_DEVICE` (ex.: `/dev/usb/lp1`; vazio desativa etiquetas
    na estação);
  - `PRINTER_LABEL_DPI` (padrão 203);
  - `PRINTER_LABEL_LINGUAGEM` (padrão `epl2`).
- Diagnóstico local: `python -m app.main label-test` imprime a etiqueta
  de calibração direto, sem servidor.

## Idempotência e falhas

Mesmo comportamento dos comprovantes: uuid como chave de dedupe no
agente (prefixo `etiqueta:` no log local), lease de 5 min para PROCESSING
órfão, backoff 5s→900s, FAILED com "Tentar novamente" após esgotar as
tentativas, impressora desligada não consome o trabalho.

## Testes

- Django (`apps/labels/tests/`): regras da bobina (1/2/3/4/ímpar,
  quantidades mistas A3+B1), preview = payload, API com isolamento entre
  tenants, views (preparação, preview JSON, confirmação, status,
  calibração, configuração), busca de produtos. Rodar:
  `uv run python manage.py test apps.labels`.
- Agente (`local-print-agent/tests/test_labels.py`): conversão mm→dots,
  duas colunas, P1 por posição, posição vazia sem conteúdo, narrow=1
  automático, latin-1, dedupe e falhas. Rodar:
  `uv run python -m unittest discover -s local-print-agent/tests -t local-print-agent`.

## Validação física (a fazer com a L42 na loja)

1. Conectar a L42 na máquina da loja e conferir `ls -l /dev/usb/lp1`
   (grupo `lp`).
2. `PRINTER_LABEL_DEVICE=/dev/usb/lp1 python -m app.main label-test` —
   moldura e código devem sair dentro de UMA etiqueta.
3. Calibrar pelo PDV e ajustar margens/offsets até a moldura acompanhar
   as bordas da etiqueta física.
4. Imprimir 1, 2 e 3 etiquetas e conferir: fileiras consumidas, posição
   vazia sem impressão, avanço correto entre fileiras e leitura do
   código com leitor.
