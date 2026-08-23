# Impressão de Comprovantes — PrintJobs + Local Print Agent

Módulo de impressão de comprovantes/notas de venda para o PDV
(`apps/printing` + `local-print-agent/`).

> Estudo de produção (arquitetura remota, análise de alternativas e
> plano de implantação passo a passo): [docs/print-producao.md](print-producao.md).

## Arquitetura obrigatória

O servidor Django fica em local remoto e **nunca** acessa a impressora.
A impressora térmica está conectada via USB (`/dev/usb/lp0`, driver
`usblp`) no computador da LOJA. Quem imprime é o **Local Print Agent**,
um processo Python independente do Django, instalado na máquina da loja.

```
SERVIDOR REMOTO (Django)                 COMPUTADOR DA LOJA
┌────────────────────────────┐           ┌─────────────────────────────┐
│ Venda finalizada           │           │ Local Print Agent (Python)  │
│      ↓                     │           │   │ 1. polling HTTPS (saída) │
│ PrintJob criado (fila)     │◄──────────┼───┤ 2. valida job (uuid)     │
│      ↓                     │  HTTPS    │   │ 3. formata comprovante   │
│ API /api/print-agent/      │───────────┼──►│ 4. ESC/POS → /dev/usb/lp0│
│ pair / poll / resultado    │           │   └──────────┬──────────────┘
└────────────────────────────┘           │              ▼ USB
                                         │     IMPRESSORA TÉRMICA
                                         └─────────────────────────────
```

Decisões fundamentais (cenário obrigatório da task):

- O servidor **não** abre conexão TCP para a loja. O agente mantém a
  conexão de **saída** (funciona atrás de NAT/CGNAT/firewall).
- Comunicação por **polling** HTTP (`POST /api/print-agent/poll/`).
  WebSocket foi descartado: o projeto não usa Channels/ASGI e o polling
  (intervalo padrão de 3s) é suficiente para comprovantes.
- O agente escreve direto no dispositivo com `open("/dev/usb/lp0", "wb")`
  — sem `printf`, sem sudo, sem CUPS, sem Wine/driver `.exe`.
- A impressora física **nunca** é exposta na internet e a API do agente
  exige autenticação própria por estação.

## Camadas (servidor)

```
PrintingService (apps/printing/services.py)   ← regras: fila, retry, pareamento
      ↓ payload (snapshot JSON da venda)
PrintJob (fila com estados e idempotência)
      ↓ API
Local Print Agent (local-print-agent/)
      ├── receipt.py   ReceiptFormatter   ← texto do comprovante (largura 58/80)
      ├── escpos.py    EscPosPrinter      ← comandos ESC/POS
      ├── printer.py   UsbPrinterDevice   ← /dev/usb/lp0 (FakePrinterDevice nos testes)
      ├── client.py    PrintAgentClient   ← HTTPS (urllib, zero dependências)
      └── agent.py     loop, dedupe local, retry
```

Lógica de negócio (Django) e comandos ESC/POS nunca se misturam.

## PrintJob

Estados: `PENDING → PROCESSING → PRINTED` ou `PENDING → PROCESSING →
RETRYING → … → FAILED`.

- `uuid` = **chave de idempotência**. O agente guarda localmente os uuids
  já processados e nunca reimprime o mesmo job, mesmo que uma reconexão
  entregue o trabalho de novo.
- `payload` = snapshot serializável da venda (itens, totais, pagamentos,
  cabeçalho da loja) — a venda já está persistida antes do PrintJob.
- `tentativa`/`tentativas_maximas`, `erro`, `data_criacao`,
  `data_processamento`, `data_impressao`, `estacao`, `venda`.

### Falhas e retry

| Cenário | Comportamento |
| --- | --- |
| Impressora desligada/desconectada | Agente informa `disponivel=false` no poll; o job permanece `PENDING` (não conta tentativa, não é perdido). |
| Agente offline | Job permanece na fila; quando o agente volta ele autentica e consulta os pendentes. |
| Falha durante a impressão | Agente reporta `FAILED` com erro; servidor agenda `RETRYING` com backoff (5s, 15s, 60s, 300s, 900s). Esgou as tentativas → `FAILED` (operador usa "Tentar novamente" no PDV). |
| Impressora morre no meio (lease 5 min) | Job `PROCESSING` parado volta para a fila como `RETRYING`; o uuid impede impressão duplicada no agente. |
| Reporte de sucesso se perde | Servidor redelivers após o lease; agente reconhece o uuid e apenas **reconfirma** `PRINTED`, sem reimprimir. |

## API do agente (`/api/print-agent/`)

Autenticação por estação via cabeçalhos `X-Station-UUID` +
`X-Station-Token` (token gerado no pareamento, armazenado como hash
bcrypt; comparação em tempo constante). Endpoints `csrf_exempt` (máquina
a máquina), sem sessão:

- `POST pair/` — consome o código de pareamento e devolve `estacao`,
  `token` (uma única vez), `nome`, `loja`.
- `POST poll/` — devolve o próximo job pendente (ou `{job: null}`) e o
  marca `PROCESSING` atômicamente. Aceita `{"disponivel": false}`.
- `POST jobs/<uuid>/resultado/` — `{"status": "PRINTED"}` ou
  `{"status": "FAILED", "erro": "..."}`.

Falha de autenticação atrasa 0,5s (freio de força bruta); códigos de
pareamento são de uso único (alfabeto sem 0/O/1/I).

### Pareamento (seguro, sem token manual)

```
Loja: PDV → Impressão → Estações → "Criar estação" (Caixa 01)
      → código exibido: ABC123 (uso único)
Agente: PRINT_AGENT_PAIR_CODE=ABC123 python -m app.main pair
      → servidor devolve estacao + token → salvos em ~/.print-agent (0600)
```

O usuário nunca digita token complexo; o código curto é consumido no
primeiro pareamento bem-sucedido.

## Modelos

- `ConfiguracaoImpressao` (1:1 tenant): largura 58/80mm, estação padrão,
  tentativas máximas, nome da loja, CNPJ, endereço, telefone, mensagem
  final. Campos de cabeçalho vazios caem para o `Emitente` fiscal (ou
  nome do tenant).
- `EstacaoImpressao`: `nome`, `status` (ATIVA/INATIVA), `token_hash`,
  `codigo_pareamento`, `ultima_atividade`, `data_pareamento`. Única por
  tenant+nome.
- `PrintJob`: descrito acima. Todos registrados no Django Admin com
  `list_display`/`list_filter` (filtro por tenant).

## Fluxo no PDV — impressão obrigatória

A impressão do comprovante acontece **SEMPRE ao final da compra**, no
momento em que o atendente **confirma o pagamento** (finalização da
venda):

1. Operador confirma o pagamento → venda finalizada (persistida).
2. A view enfileira o PrintJob **obrigatoriamente** — sem opção de
   desligar. Falha de impressão **nunca** bloqueia a venda (apenas aviso
   ao operador; o job fica na fila com retry).
3. A tela `venda_detalhe` mostra o painel do comprovante (polling JS a
   cada 3s em `printing:status_venda`):
   - `Aguardando o agente de impressão da loja…` — **nenhuma estação
     ativa**: falta cadastrar/parear/iniciar o agente na máquina da loja;
   - `Aguardando impressora…` — há estação ativa; o agente pega o job em
     segundos (ou o retry está aguardando o backoff);
   - `Imprimindo...` — o agente reivindicou o job (PROCESSING);
   - `✓ Comprovante impresso` (+ "Imprimir novamente");
   - `⚠ Não foi possível imprimir [ Tentar novamente ]`.
4. `Imprimir novamente` cria um novo job (idempotente por venda;
   após PRINTED é gerado novo uuid).

## ESC/POS e largura do papel

- 58mm → 32 colunas; 80mm → 48 colunas (configurável por loja). Nomes
  longos quebram em linhas sem estourar a coluna; valores em pt-BR
  (`1.234,56`), quantidades sem zeros à direita (`2`, `2,5`).
- Codificação: `utf8` (padrão) ou `cp850` via `PRINTER_CODEPAGE`
  (seleciona a tabela com `ESC t 2`). Acentos e UTF-8 cobertos por teste.

## Impressora Tomate MDK-080 — alternativa em texto puro (printf)

O driver oficial da **Tomate MDK-080** só existe para Windows, mas a
impressora funciona no Linux via `usblp` com escrita direta no
dispositivo. O teste que valida a impressora é:

```bash
printf "TESTE SEM SUDO\n\n\n" > /dev/usb/lp0
```

O agente reproduz esse comportamento em Python (abertura direta do
dispositivo — nunca um shell) no **modo texto puro**:

- `PRINTER_ESCPOS=0` desativa os comandos ESC/POS: o comprovante é
  enviado como texto puro + `\n\n\n` (exatamente o padrão do comando
  acima), que é o caminho mais compatível com impressoras de firmware
  restrito como a MDK-080.
- Diagnóstico equivalente ao printf: `python -m app.main raw-test`
  escreve `TESTE SEM SUDO\n\n\n` direto em `PRINTER_DEVICE`.
- `python -m app.main test` imprime uma página de teste: com ESC/POS por
  padrão, ou em texto puro com `PRINTER_ESCPOS=0`.

Configuração recomendada para a MDK-080 em
`/etc/sv/print-agent/conf`:

```sh
export PRINTER_DEVICE=/dev/usb/lp0
export PRINTER_ESCPOS=0        # texto puro (printf), firmware MDK-080
export PRINTER_CODEPAGE=cp850  # acentos em 1 byte (firmware não entende UTF-8)
export PRINT_AGENT_LARGURA_PADRAO=58
export PRINTER_ALIMENTACAO_FINAL=8   # folga p/ o rasgo não pegar o texto
```

**Acentos**: o firmware da MDK-080 interpreta os bytes como tabela de 1
byte — UTF-8 sai como símbolos lixo. Com `PRINTER_CODEPAGE=cp850` (ou
`cp860`/`cp1252`) o agente codifica cada acento em 1 byte e envia
`ESC t n` no início para selecionar a tabela (desativável com
`PRINTER_SELECIONAR_CODEPAGE=0`). Para descobrir a tabela certa em
campo, rode `python -m app.main codepage-test`: a página imprime a mesma
frase em UTF-8, CP850, CP860 e CP1252 rotuladas — defina a que sair
correta. Caracteres sem representação (ex.: travessão `—`) são
normalizados para hífen.

**Folga no fim do comprovante**: por padrão o agente avança 8 linhas em
branco após o conteúdo (ESC/POS: `ESC d 8` antes do corte; texto puro:
`\n` × 8), para o corte/rasgo nunca cair sobre a nota. Ajuste conforme a
distância da guilhotina/barra de rasgo com `PRINTER_ALIMENTACAO_FINAL`.

As térmicas tradicionais (Elgin, Bematech, Epson etc.) continuam usando
ESC/POS (`PRINTER_ESCPOS=1`, padrão) para realce e corte automático.

## Segurança

- Credencial por estação (loja → caixa → impressora); nunca confiar em IP.
- Token trafega uma única vez; banco guarda só o hash bcrypt.
- O agente carrega apenas a credencial da própria estação (nunca segredos
  do Django/plataforma); `credencial.json` com permissão 0600.
- API não expõe o dispositivo; jobs isolados por tenant (estação A só vê
  o próprio tenant — testado).
- Nada de sudo; a máquina da loja usa o usuário no grupo `lp`.

## Local Print Agent (Void Linux)

Ver [local-print-agent/README.md](../local-print-agent/README.md). A
máquina da loja usa **runit** (não systemd):

```
/etc/sv/print-agent/run    ← serviço (deploy/print-agent/run)
/etc/sv/print-agent/conf   ← env vars (deploy/print-agent/conf)
/var/service/print-agent   ← symlink para /etc/sv/print-agent
```

O serviço roda `python3 -m app.main run` (sem venv necessária: o agente
usa apenas stdlib).

## Testes

- Django: `apps/printing/tests/` (payload com desconto/centavos/UTF-8,
  fila, backoff, lease, pareamento, API, isolamento entre tenants,
  integração com o PDV). Rodar: `uv run python manage.py test apps.printing`.
- Agente: `local-print-agent/tests/` (formatação em 58/80mm, nomes
  longos, ESC/POS com `FakePrinterDevice`, dedupe entre "processos",
  impressora indisponível). Rodar:
  `uv run python -m unittest discover -s local-print-agent/tests -t local-print-agent`.
- Nenhum teste toca `/dev/usb/lp0`; a implementação real
  (`UsbPrinterDevice`) só é usada em produção.

## Troubleshooting — "o comprovante não sai"

O painel do PDV mostra exatamente onde está o gargalo:

| Sintoma | Causa provável | Correção |
| --- | --- | --- |
| `Aguardando o agente de impressão da loja…` | Nenhuma estação ATIVA (agente nunca instalado/pareado ou inativado). | Impressão → Estações → criar estação, copiar o código e parear o agente (`PRINT_AGENT_PAIR_CODE=… python -m app.main pair`); depois `python -m app.main run`. |
| `Aguardando impressora…` (eterno) | Agente parado/morto, ou impressora desligada/desconectada. | Verificar processo/serviço (`sv status print-agent`), cabo USB e `ls -l /dev/usb/lp0`; conferir logs do agente. |
| `Imprimindo...` (eterno) | Impressora morreu no meio da escrita. | O lease (5 min) devolve o job à fila; o agente reimprime após o backoff (uuid evita duplicidade). |
| Nada sai, sem erro | Permissão do dispositivo. | Usuário precisa do grupo `lp`: `groups` deve listar `lp`; testar com `python -m app.main raw-test` (equivalente a `printf "TESTE SEM SUDO\n\n\n" > /dev/usb/lp0`). |
| Só sai "?"/lixo | Codificação/firmware. | Acentos quebrados: usar `PRINTER_CODEPAGE=cp850` (ou cp860/cp1252) e `python -m app.main codepage-test` para descobrir a tabela correta no papel. |

Diagnóstico rápido na máquina da loja:

```bash
printf "TESTE SEM SUDO\n\n\n" > /dev/usb/lp0   # a impressora está acessível?
python3 -m app.main raw-test                   # o mesmo teste via agente
python3 -m app.main test                       # página de teste (ESC/POS ou texto)
sv status print-agent                          # serviço runit ativo? (Void Linux)
```
