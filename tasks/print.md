# PRINT - IMPRESSÃO

1. **Leitura compulsória:** `agents.md`.
2. **Verificação do tenant:** Antes de qualquer `Model.objects.get()`, confirmar se existe filtro por `tenant`.
3. **Django Admin:** Todo novo model deve ser registrado no admin com list_display e filters.
4. **Commit:** Usar Conventional Commits.

Você é o agente responsável por implementar um sistema de impressão de comprovantes/notas de venda para o PDV.

## Contexto da arquitetura

Este é um sistema WEB.

IMPORTANTE: o servidor da aplicação ficará em um local remoto, enquanto o cliente/loja ficará em outro local físico.

A impressora térmica ficará conectada por USB no computador da LOJA/CLIENTE.

Portanto:

* O servidor Django NÃO terá acesso ao `/dev/usb/lp0` da loja.
* O navegador do cliente NÃO deve tentar acessar diretamente a impressora USB.
* O servidor remoto NÃO deve tentar executar `printf ... > /dev/usb/lp0`.
* O `/dev/usb/lp0` existe somente na máquina local onde a impressora está conectada.
* Precisamos de um mecanismo de impressão local na máquina do cliente.

A arquitetura obrigatória deve ser:

```text
┌──────────────────────────────┐
│       SERVIDOR REMOTO        │
│                              │
│ Django / API / Banco         │
│                              │
│ Venda                        │
│ Produtos                     │
│ Valores                      │
└──────────────┬───────────────┘
               │
               │ HTTP/HTTPS
               │
               ▼
┌──────────────────────────────┐
│       COMPUTADOR DA LOJA     │
│                              │
│ Navegador                    │
│       │                      │
│       └── PDV Web            │
│                              │
│ Agente Local de Impressão    │
│       │                      │
│       ▼                      │
│ /dev/usb/lp0                 │
└──────────────┬───────────────┘
               │ USB
               ▼
┌──────────────────────────────┐
│      IMPRESSORA TÉRMICA      │
└──────────────────────────────┘
```

## Objetivo

Implementar um sistema de impressão de comprovantes de venda semelhante ao comprovante entregue em supermercados.

O comprovante deve apresentar, no mínimo:

* Nome da empresa/loja
* CNPJ, quando disponível
* Data e hora da venda
* Número/identificador da venda
* Nome dos produtos
* Quantidade de cada produto
* Valor unitário
* Subtotal de cada item
* Total da venda
* Forma de pagamento
* Valor recebido, quando aplicável
* Troco, quando aplicável
* Mensagem final configurável

Exemplo conceitual:

```text
========================================
              MINHA LOJA
           CNPJ: 00.000.000/0001-00
========================================
Venda: #000123
Data: 23/08/2026 17:42
----------------------------------------
Produto              Qtd   Unit   Total
----------------------------------------
Coca-Cola 350ml       2    5,00   10,00
Salgadinho            1    8,50    8,50
Chocolate              3    4,00   12,00
----------------------------------------
TOTAL:                         R$ 30,50
----------------------------------------
Pagamento: PIX
----------------------------------------

        Obrigado pela preferência!
========================================
```

A implementação deve respeitar a largura real da impressora térmica e evitar linhas quebradas incorretamente.

## Impressão local

Na máquina da loja deverá existir um pequeno **Local Print Agent**.

Esse agente será responsável por:

1. Rodar localmente na máquina do cliente.
2. Detectar/acessar a impressora térmica.
3. Receber uma solicitação de impressão.
4. Converter os dados da venda em comandos apropriados para a impressora.
5. Enviar os dados diretamente para a impressora.

A comunicação com a impressora deve utilizar diretamente:

```text
/dev/usb/lp0
```

O teste atualmente funcional é:

```bash
printf "TESTE SEM SUDO\n\n\n" > /dev/usb/lp0
```

O agente deve reproduzir conceitualmente esse comportamento através do código, escrevendo os dados da impressão no dispositivo:

```text
/dev/usb/lp0
```

NÃO executar literalmente um comando shell com `printf` para cada impressão se houver uma implementação Python mais segura e adequada.

Preferencialmente utilizar abertura direta do dispositivo, por exemplo:

```python
with open("/dev/usb/lp0", "wb") as printer:
    printer.write(data)
```

ou uma abstração equivalente.

## IMPORTANTE: não criar dependência do driver Windows

Não utilizar:

* `.exe`
* Wine
* driver proprietário Windows

A impressora já funciona diretamente no Linux através do:

```text
usblp
```

e:

```text
/dev/usb/lp0
```

Portanto, aproveitar a comunicação Linux existente.

## ESC/POS

Antes de implementar comandos específicos, identificar se a impressora suporta ESC/POS.

A arquitetura deve permitir encapsular os comandos da impressora em uma camada própria.

Exemplo conceitual:

```text
PrintingService
      │
      ▼
ReceiptFormatter
      │
      ▼
EscPosPrinter
      │
      ▼
LocalPrinterDevice
      │
      ▼
/dev/usb/lp0
```

Evitar misturar lógica de negócio do PDV com comandos ESC/POS.

## Arquitetura do Local Print Agent

O agente local deve ser um processo independente do Django.

Sugestão:

```text
local-print-agent/
├── app/
│   ├── main.py
│   ├── printer.py
│   ├── escpos.py
│   ├── client.py
│   └── config.py
├── pyproject.toml
└── README.md
```

O agente poderá ser implementado em Python.

Ele deverá:

* possuir configuração da URL do servidor;
* possuir identificação única da estação;
* possuir token/chave de autenticação;
* verificar se a impressora está disponível;
* receber trabalhos de impressão;
* imprimir;
* retornar sucesso/erro;
* possuir logs;
* possuir mecanismo de retry;
* evitar impressão duplicada.

## Comunicação servidor → agente

NÃO assumir que o servidor consegue abrir uma conexão TCP diretamente para o computador da loja.

A máquina da loja pode estar atrás de:

* NAT
* firewall
* CGNAT
* roteador doméstico/comercial

Portanto, prefira um modelo em que o agente local mantenha uma conexão de saída com o servidor.

Exemplo:

```text
                 HTTPS/WebSocket
        ┌──────────────────────────┐
        │                          │
        ▼                          │
Servidor Django                Agente
        │                          │
        │     conexão persistente  │
        └──────────────────────────►
                                   │
                                   ▼
                              /dev/usb/lp0
                                   │
                                   ▼
                              Impressora
```

Uma alternativa aceitável é o agente fazer polling periódico em uma API:

```text
POST /api/print-jobs/poll
```

ou equivalente.

Porém, se a arquitetura atual permitir WebSocket, considerar WebSocket para diminuir latência.

NÃO expor `/dev/usb/lp0` ou o agente de impressão diretamente na internet.

## Segurança

O sistema deve considerar que o agente está instalado na máquina do cliente.

Cada estação deverá possuir uma credencial própria.

Exemplo:

```text
store_id
terminal_id
print_agent_token
```

Nunca confiar somente no IP do cliente.

O servidor deve conseguir identificar:

```text
Loja X
   └── Caixa 01
         └── Impressora térmica
```

O agente deve autenticar-se no servidor usando credencial própria.

Não colocar credenciais administrativas ou secrets do Django no agente.

## Fluxo esperado

Implementar o seguinte fluxo:

```text
1. Cliente finaliza venda
          ↓
2. Django salva a venda
          ↓
3. Django gera um PrintJob
          ↓
4. PrintJob recebe identificador único
          ↓
5. Agente da loja recebe o trabalho
          ↓
6. Agente valida o trabalho
          ↓
7. Agente formata o comprovante
          ↓
8. Agente envia bytes para /dev/usb/lp0
          ↓
9. Impressora imprime
          ↓
10. Agente informa sucesso ao servidor
```

O `PrintJob` deve possuir um identificador/idempotency key para evitar que uma reconexão faça o mesmo comprovante ser impresso duas vezes.

## Estado do PrintJob

Criar estados adequados, por exemplo:

```text
PENDING
PROCESSING
PRINTED
FAILED
```

Considerar também:

```text
RETRYING
```

se fizer sentido para a arquitetura existente.

Registrar:

* data de criação;
* data de processamento;
* estação;
* tentativa;
* erro;
* data de impressão;
* identificador da venda.

## Falhas

O sistema deve suportar situações como:

### Impressora desligada

O agente não deve perder o trabalho.

### Impressora desconectada

O trabalho deve permanecer pendente/retry.

### Agente offline

O servidor deve manter o PrintJob pendente.

Quando o agente voltar:

```text
agente conecta
    ↓
autentica
    ↓
consulta trabalhos pendentes
    ↓
processa
```

### Falha durante impressão

Registrar erro detalhado.

Evitar automaticamente imprimir novamente sem uma estratégia de idempotência, porque uma impressora térmica pode ter recebido parte do trabalho antes da conexão falhar.

## Interface no PDV

Após finalizar uma venda, apresentar algo como:

```text
Venda finalizada!

[ Imprimir comprovante ]

[ Não imprimir ]
```

Se a impressão for automática por configuração da loja, permitir:

```text
Venda finalizada
Imprimindo...
```

Depois:

```text
✓ Comprovante impresso
```

ou:

```text
⚠ Não foi possível imprimir

[ Tentar novamente ]
```

Não bloquear a venda por uma falha de impressão.

A venda já deve estar persistida antes do PrintJob.

## Configuração da loja

Criar configuração para determinar:

```text
Impressão automática: SIM/NÃO
Impressora padrão: terminal/estação
Largura: 58mm / 80mm
Mensagem final
Nome da loja
CNPJ
Endereço
Telefone
```

Não assumir uma largura fixa sem verificar o modelo da impressora.

## Testes

Criar testes para:

### Formatação

Testar:

* produto único;
* vários produtos;
* quantidades diferentes;
* valores com centavos;
* desconto;
* total;
* pagamento;
* troco;
* caracteres UTF-8;
* acentos;
* nomes longos;
* produtos com nomes muito longos.

### Impressão

Não executar testes reais contra `/dev/usb/lp0` na suíte padrão.

Criar uma abstração:

```python
PrinterDevice
```

e uma implementação:

```python
UsbPrinterDevice
```

A implementação real usa:

```text
/dev/usb/lp0
```

Enquanto os testes usam:

```text
FakePrinterDevice
```

que apenas captura os bytes enviados.

Assim podemos validar exatamente os comandos ESC/POS gerados sem precisar de uma impressora física.

## Configuração

O caminho da impressora não deve ficar hardcoded espalhado pelo código.

Usar configuração:

```text
PRINTER_DEVICE=/dev/usb/lp0
```

O padrão pode ser:

```text
/dev/usb/lp0
```

mas deve ser configurável.

## Não fazer

NÃO:

* tentar acessar `/dev/usb/lp0` no Django remoto;
* usar Wine;
* instalar driver `.exe`;
* assumir que o navegador consegue acessar a USB;
* abrir uma porta de impressão pública na internet;
* colocar o agente atrás de uma API sem autenticação;
* acoplar ESC/POS aos models do Django;
* imprimir antes de persistir a venda;
* perder PrintJobs quando o agente estiver offline;
* criar dependência de CUPS se a comunicação direta funcionar;
* utilizar `sudo` durante a impressão;
* alterar permissões para `777`.

A máquina da loja já está configurada com o usuário no grupo `lp`, portanto o agente deve conseguir acessar:

```text
/dev/usb/lp0
```

sem privilégios de root.

## Serviço no Void Linux

A máquina da loja utiliza Void Linux.

IMPORTANTE:

Void Linux utiliza **runit**, não systemd.

Portanto, caso seja implementado um serviço para o Local Print Agent, criar documentação e configuração compatível com runit.

Não usar:

```bash
systemctl
```

Usar a estrutura de serviços do Void:

```text
/etc/sv/<serviço>
/var/service/<serviço>
```

## Descoberta/pareamento da estação

Implementar uma forma segura de registrar o agente.

Exemplo:

```text
Servidor gera código:

ABC123

Cliente instala o agente.

Agente informa:

ABC123

Servidor associa:

Loja:
Minha Loja

Terminal:
Caixa 01

Agente:
terminal-uuid
```

Depois disso o agente recebe uma credencial própria.

Não deixar o usuário ter que colocar manualmente tokens complexos se pudermos criar um processo simples de pareamento.

## API

Criar endpoints necessários no backend seguindo os padrões já existentes no projeto.

Não criar uma arquitetura paralela desnecessária.

Antes de implementar:

1. analisar a arquitetura existente;
2. identificar os models atuais de venda;
3. identificar usuários/tenants/lojas;
4. identificar autenticação existente;
5. identificar padrão atual de APIs;
6. identificar onde a venda é finalizada;
7. identificar o padrão atual de configurações.

Reutilizar o que já existe.

Não duplicar models ou mecanismos existentes.

## Qualidade do código

Seguir os padrões já existentes no projeto.

Manter:

* Clean Architecture quando já utilizada;
* separação de responsabilidades;
* type hints;
* testes;
* tratamento explícito de erros;
* logs;
* código simples.

Não implementar overengineering.

## Entregáveis

Ao terminar:

1. Backend para PrintJobs.
2. API necessária para comunicação com os agentes.
3. Local Print Agent.
4. Impressão ESC/POS.
5. Comunicação segura agente ↔ servidor.
6. Sistema de retry.
7. Idempotência.
8. Interface de impressão no PDV.
9. Configuração da impressora.
10. Testes.
11. Documentação de instalação do agente no Void Linux.
12. Documentação de configuração da impressora.
13. Documentação do fluxo completo.

## Regra importante para o desenvolvimento

Antes de começar a codificar, examine o projeto atual e adapte a solução à arquitetura existente.

Não faça alterações grandes sem necessidade.

Se existir alguma decisão arquitetural importante que não possa ser determinada pelo código existente, documente a decisão e escolha a alternativa mais simples e segura.

O resultado final precisa funcionar neste cenário real:

```text
SERVIDOR REMOTO
    │
    │ Internet
    │
    ▼
COMPUTADOR DA LOJA
    │
    ├── Navegador
    ├── PDV Web
    └── Local Print Agent
             │
             ▼
       /dev/usb/lp0
             │
             ▼
       IMPRESSORA TÉRMICA
```

Esse cenário é obrigatório e deve ser tratado como requisito fundamental da implementação.
