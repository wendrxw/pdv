# CONTEXTO DO PROJETO — PDV WEB + AGENTE LOCAL

## 1. Visão geral

O projeto será um sistema de Ponto de Venda (PDV) desenvolvido em Python, com arquitetura web/híbrida.

A decisão arquitetural principal é:

> O PDV NÃO será um aplicativo desktop tradicional. Será uma aplicação Web/PWA, com um agente local Python responsável pela comunicação com hardware do computador do caixa.

Objetivos principais:

- Interface rápida e simples para operadores de caixa.
- Funcionamento centralizado via servidor.
- Suporte a múltiplos caixas, filiais e empresas.
- Possibilidade de operação offline.
- Impressão de NFC-e/notas fiscais em impressoras térmicas.
- Impressão de etiquetas.
- Integração com leitor de código de barras.
- Possibilidade futura de integração com gaveta de dinheiro, balança e outros periféricos.
- Arquitetura preparada para virar um produto SaaS multiempresa.

---

## 2. Arquitetura geral

Arquitetura desejada:

```text
                         INTERNET
                            |
                            v
                    +----------------+
                    | NGINX /        |
                    | CLOUDFLARE     |
                    +-------+--------+
                            |
                            v
                    +----------------+
                    |    DJANGO      |
                    |                |
                    | REST API       |
                    | Autenticação   |
                    | PDV            |
                    | Estoque        |
                    | Financeiro     |
                    | Fiscal         |
                    +-------+--------+
                            |
               +------------+------------+
               |            |            |
               v            v            v
         PostgreSQL       Redis       Celery


                    COMPUTADOR DO CAIXA
               +--------------------------+
               |                          |
               |       PWA / WEB APP      |
               |                          |
               |  +--------------------+  |
               |  | Banco local        |  |
               |  | IndexedDB/SQLite   |  |
               |  +--------------------+  |
               |            |             |
               |            v             |
               |    Python Local Agent   |
               |            |             |
               |      +-----+------+      |
               |      |     |      |      |
               |      v     v      v      |
               |   Térmica Etiqueta Gaveta|
               |   NFC-e     Zebra   Caixa |
               |                          |
               +--------------------------+
```

---

# 3. Stack tecnológica

## Backend

- Python
- Django
- Django REST Framework
- PostgreSQL
- Redis
- Celery

## Frontend

Preferencialmente:

- Django Templates quando fizer sentido.
- HTML.
- Tailwind CSS.
- JavaScript/TypeScript para comportamento dinâmico.
- PWA.
- Interface responsiva.
- Arquitetura preparada para operação offline.

Não utilizar um frontend SPA pesado sem necessidade. Priorizar simplicidade, desempenho e manutenção.

## Agente local

- Python.
- Comunicação local via HTTP/WebSocket.
- Responsável por acessar hardware.
- Executado no computador do caixa.
- Deve funcionar independentemente do servidor central quando possível.

---

# 4. Conceito central: Web + Agente Local

O navegador não deve acessar diretamente as impressoras e periféricos.

O fluxo será:

```text
PDV Web
   |
   | WebSocket / HTTP
   v
Python Local Agent
   |
   +--> Impressora térmica
   +--> Impressora de etiquetas
   +--> Gaveta de dinheiro
   +--> Balança
   +--> Outros periféricos
```

O agente local será uma camada de abstração de hardware.

Isso permite manter o sistema web independente de marcas e modelos específicos.

---

# 5. Agente local

O agente local deve ser tratado como um componente independente.

Responsabilidades:

- Descobrir impressoras.
- Identificar status das impressoras.
- Enviar trabalhos de impressão.
- Comunicar-se com impressoras USB/rede.
- Trabalhar com protocolos comuns de impressão térmica.
- Imprimir etiquetas.
- Imprimir comprovantes.
- Imprimir DANFE NFC-e.
- Controlar gaveta de dinheiro quando suportado.
- Futuramente conversar com balanças e outros periféricos.
- Manter fila local de impressão.
- Informar erros ao PDV.

O agente deve possuir uma API local e/ou WebSocket.

Exemplo:

```text
GET /printers
POST /print
GET /jobs
GET /health
```

---

# 6. Abstração de impressoras

Nunca acoplar o sistema diretamente a uma única marca.

Criar uma camada de abstração:

```python
class Printer:
    def print_receipt(self, document):
        pass

    def print_nfce(self, document):
        pass

    def print_label(self, label):
        pass
```

Possível organização:

```text
printing/
    base.py
    service.py
    thermal.py
    label.py

    escpos/
        generic.py
        elgin.py
        bematech.py

    zebra/
        zpl.py
```

A implementação concreta deve ser escolhida conforme a impressora configurada.

---

# 7. Fila de impressão

A impressão deve ser orientada a jobs.

Modelo conceitual:

```text
PrintJob
---------
id
type
document
printer
content
status
attempts
error
created_at
printed_at
```

Estados possíveis:

```text
pending
printing
printed
failed
cancelled
```

Exemplo:

```text
Venda
  |
  v
NFC-e autorizada
  |
  v
PrintJob
  |
  v
Agente local
  |
  v
Impressora
```

Se a impressora estiver offline, o job não deve simplesmente desaparecer.

Ele deve permanecer pendente e ser reprocessado.

---

# 8. Impressão de NFC-e

A parte fiscal deve ser desacoplada da impressão.

Fluxo:

```text
Venda
  |
  v
Módulo fiscal
  |
  v
NFC-e
  |
  v
SEFAZ
  |
  v
Autorização
  |
  v
XML
  |
  v
DANFE NFC-e
  |
  v
Agente local
  |
  v
Impressora térmica
```

Separar claramente:

```text
fiscal/
    nfce/
        models.py
        services.py
        sefaz.py
        xml.py
        authorization.py

printing/
    services.py
    thermal.py
    labels.py
```

O módulo fiscal não deve conhecer detalhes de USB, drivers ou hardware.

---

# 9. Etiquetas

O sistema deve permitir gerar etiquetas de produtos.

Exemplo:

```text
+-------------------------+
|       CAFÉ 500g         |
|                         |
|        R$ 18,90         |
|                         |
|    |||||||||||||||||    |
|    7891234567890        |
+-------------------------+
```

Dados possíveis:

- Nome do produto.
- Preço.
- Código de barras.
- SKU.
- Lote.
- Validade.
- Unidade.
- Informações adicionais.

A camada de impressão deve permitir diferentes formatos/protocolos, incluindo ESC/POS e, quando aplicável, ZPL.

---

# 10. Leitor de código de barras

O PDV deve ser projetado desde o início para trabalhar com leitores de código de barras.

A maioria dos leitores USB funciona como teclado HID.

Fluxo:

```text
Leitor
  |
  v
Código de barras
  |
  v
Campo/handler do PDV
  |
  v
Busca produto
  |
  v
Adiciona ao carrinho
```

O fluxo de caixa deve ser extremamente rápido, evitando cliques desnecessários.

---

# 11. Operação offline

Um dos requisitos arquiteturais mais importantes é evitar que uma queda de internet paralise completamente o caixa.

Estratégia:

```text
                    INTERNET ONLINE

PDV
 |
 v
API Django
 |
 v
PostgreSQL


                    INTERNET OFFLINE

PDV
 |
 v
Banco local
 |
 v
Venda local


                    INTERNET VOLTOU

Banco local
 |
 v
Sincronização
 |
 v
Django
 |
 v
PostgreSQL
```

O mecanismo de sincronização deverá ser desenvolvido de forma segura e idempotente.

Não confiar apenas em timestamps.

Cada operação importante deve possuir identificadores únicos e controle de sincronização.

---

# 12. Módulos principais do sistema

## Empresas

- Empresa.
- CNPJ.
- Configurações.
- Plano.
- Status.

## Filiais

- Empresa.
- CNPJ.
- Endereço.
- Configurações fiscais.
- Caixas.

## Usuários

Papéis iniciais:

- Administrador.
- Gerente.
- Caixa.
- Estoquista.

Implementar RBAC.

---

# 13. Produtos

Produto deve possuir, entre outros:

- ID.
- SKU.
- Código de barras.
- Nome.
- Descrição.
- Categoria.
- Unidade.
- Preço de venda.
- Custo.
- Estoque.
- Estoque mínimo.
- NCM.
- CFOP.
- CEST quando aplicável.
- Informações fiscais.
- Ativo/inativo.

---

# 14. Estoque

Módulo responsável por:

- Entrada.
- Saída.
- Ajuste.
- Inventário.
- Transferência entre filiais.
- Histórico.
- Estoque por filial.
- Estoque mínimo.

Evitar simplesmente alterar o campo de estoque sem registrar movimentação.

Preferir:

```text
StockMovement
```

com histórico completo.

---

# 15. PDV / Venda

Fluxo principal:

```text
Abrir caixa
    |
    v
Identificar operador
    |
    v
Adicionar produtos
    |
    v
Carrinho
    |
    v
Descontos
    |
    v
Pagamento
    |
    v
Fiscal
    |
    v
Impressão
    |
    v
Finalização
```

O operador deve conseguir:

- Ler código de barras.
- Buscar produto.
- Alterar quantidade.
- Remover item.
- Aplicar desconto conforme permissão.
- Identificar cliente.
- Escolher forma de pagamento.
- Cancelar item/venda conforme permissão.
- Reimprimir comprovante/documento.
- Consultar vendas recentes.

---

# 16. Caixa

Funcionalidades:

- Abrir caixa.
- Fechar caixa.
- Sangria.
- Suprimento.
- Conferência.
- Saldo esperado.
- Saldo informado.
- Diferença.
- Histórico.

Formas de pagamento:

- Dinheiro.
- PIX.
- Débito.
- Crédito.
- Outras formas configuráveis.
- Fiado/conta a receber, se habilitado.

---

# 17. Financeiro

Deve ser integrado às vendas, mas não depender diretamente da interface do PDV.

Possíveis módulos:

- Contas a receber.
- Contas a pagar.
- Fluxo de caixa.
- Recebimentos.
- Despesas.
- Categorias financeiras.
- Conciliação futura.

---

# 18. Fiscal

Criar módulo fiscal isolado.

Possíveis documentos futuros:

- NFC-e.
- NF-e.
- Outros documentos conforme necessidade legal.

Responsabilidades:

- Geração de documentos.
- XML.
- Assinatura digital quando aplicável.
- Comunicação com SEFAZ.
- Autorização.
- Cancelamento.
- Inutilização quando aplicável.
- Contingência.
- Armazenamento dos documentos.
- Histórico fiscal.

IMPORTANTE:

Regras fiscais brasileiras mudam com frequência. Não espalhar regras fiscais pelo código de vendas.

Centralizar regras no módulo fiscal e manter componentes configuráveis.

---

# 19. Segurança

Considerar desde o início:

- RBAC.
- Auditoria.
- Logs.
- Controle de sessão.
- Expiração de sessão.
- Rate limiting.
- Proteção contra CSRF/XSS/SQL Injection.
- Criptografia de dados sensíveis.
- Proteção de certificados digitais.
- LGPD.
- Controle de permissões por operação crítica.

Operações como:

- cancelar venda;
- aplicar desconto elevado;
- abrir/fechar caixa;
- alterar preço;
- alterar estoque;
- cancelar documento fiscal;

devem possuir controle de permissão e auditoria.

---

# 20. Multiempresa / SaaS

A arquitetura deve ser preparada para:

```text
Empresa
  |
  +-- Filial 1
  |     +-- Caixa 1
  |     +-- Caixa 2
  |
  +-- Filial 2
        +-- Caixa 1
        +-- Caixa 2
```

Todas as entidades relevantes devem possuir relação com empresa/tenant quando necessário.

Nunca permitir que um usuário consulte ou altere dados de outra empresa.

---

# 21. Princípios arquiteturais

Seguir estes princípios:

1. Separação clara de domínios.
2. Fiscal desacoplado de vendas.
3. Impressão desacoplada do fiscal.
4. Hardware desacoplado do Django.
5. Agente local independente.
6. Operações críticas auditáveis.
7. Sistema preparado para offline.
8. Operações de sincronização idempotentes.
9. Não acoplar o sistema a uma marca de impressora.
10. Não espalhar regras fiscais pelo projeto.
11. Não criar complexidade desnecessária antes da necessidade.
12. Priorizar desempenho no caixa.
13. Priorizar recuperação de falhas.
14. Priorizar manutenção e testes.

---

# 22. Estrutura inicial sugerida

```text
pdv/
├── config/
│
├── apps/
│   ├── accounts/
│   ├── companies/
│   ├── branches/
│   ├── products/
│   ├── inventory/
│   ├── sales/
│   ├── cash_register/
│   ├── payments/
│   ├── customers/
│   ├── financial/
│   ├── fiscal/
│   │   └── nfce/
│   ├── printing/
│   ├── synchronization/
│   ├── audit/
│   └── reports/
│
├── api/
│
├── frontend/
│
├── tests/
│
└── local-agent/
    ├── api/
    ├── websocket/
    ├── printers/
    ├── escpos/
    ├── zebra/
    ├── devices/
    ├── jobs/
    └── config/
```

A estrutura pode ser ajustada conforme a implementação, mas os limites de responsabilidade devem ser preservados.

---

# 23. Ordem recomendada de desenvolvimento

Não implementar tudo simultaneamente.

### Fase 1 — Fundação

- Projeto Django.
- PostgreSQL.
- Autenticação.
- Empresas.
- Filiais.
- Usuários/RBAC.
- Auditoria básica.

### Fase 2 — Produtos

- Cadastro.
- Categorias.
- Código de barras.
- Preços.
- Estoque inicial.

### Fase 3 — PDV

- Tela do caixa.
- Leitor de código de barras.
- Carrinho.
- Quantidade.
- Desconto.
- Pagamentos.
- Finalização.

### Fase 4 — Caixa

- Abertura.
- Sangria.
- Suprimento.
- Fechamento.
- Conferência.

### Fase 5 — Agente local

- Serviço Python.
- Descoberta de impressoras.
- Health check.
- Comunicação WebSocket.
- Fila de impressão.
- Impressão térmica.
- Impressão de etiquetas.

### Fase 6 — Fiscal

- NFC-e.
- Comunicação com SEFAZ.
- XML.
- Autorização.
- Cancelamento.
- Contingência.
- DANFE NFC-e.
- Impressão.

### Fase 7 — Offline

- Banco local.
- Cache.
- Fila de operações.
- Sincronização.
- Recuperação de falhas.
- Idempotência.

### Fase 8 — Estoque/Financeiro/Relatórios

Expandir os módulos administrativos depois que o núcleo do caixa estiver estável.

---

# 24. Requisito de UX do PDV

A tela do caixa deve ser diferente do restante do sistema.

Não criar uma interface administrativa tradicional para o operador.

O caixa precisa de:

- Poucos elementos.
- Números grandes.
- Busca rápida.
- Foco automático no código de barras.
- Atalhos de teclado.
- Operação com teclado numérico.
- Feedback visual imediato.
- Poucos cliques.
- Carrinho sempre visível.
- Total extremamente destacado.
- Fluxo de pagamento rápido.

O objetivo é que um operador consiga realizar uma venda sem precisar navegar por várias páginas.

---

# 25. Decisão arquitetural definitiva

A arquitetura base do projeto deve seguir:

```text
             DJANGO / REST API
                    |
              PostgreSQL
                    |
              Redis/Celery
                    |
          +---------+---------+
          |                   |
       INTERNET           SINCRONIZAÇÃO
          |                   |
          v                   v
       PWA / WEB         BANCO LOCAL
          |
          |
     WebSocket/HTTP
          |
          v
    PYTHON LOCAL AGENT
          |
     +----+----+---------+
     |         |         |
 Impressora  Etiqueta  Periféricos
 térmica               do caixa
```

A ideia central é:

> O Django controla o negócio.  
> O PWA controla a experiência do operador.  
> O banco local garante resiliência do caixa.  
> O agente Python controla o hardware.  
> O PostgreSQL é a fonte central de dados.  
> Redis/Celery executam tarefas assíncronas.  
> O módulo fiscal permanece isolado.  
> O módulo de impressão permanece isolado.

Esse contexto deve ser usado como referência arquitetural durante todo o desenvolvimento. Antes de implementar decisões que alterem esses princípios, avaliar impacto sobre offline, impressão, fiscal, multiempresa e hardware local.
