# Local Print Agent — PDV

Processo local que imprime comprovantes de venda na impressora térmica
USB da loja. Roda na máquina do CLIENTE, independente do servidor Django.

```
Servidor Django (remoto)          Máquina da loja
         ▲                            ┌──────────────┐
         │ HTTPS (polling, saída)     │ print-agent  │
         └────────────────────────────┤      │       │
                                      │  /dev/usb/lp0│
                                      └──────┬───────┘
                                             ▼ USB
                                     IMPRESSORA TÉRMICA
```

Zero dependências (stdlib Python). Não usa Wine, driver `.exe`, CUPS ou
sudo — a impressora já funciona via `usblp` (`/dev/usb/lp0`) com o
usuário no grupo `lp`.

## Instalação (Void Linux — runit)

```bash
# 1. Copie o código (ex.: via git ou pen drive)
sudo mkdir -p /opt/print-agent
sudo cp -r app/ /opt/print-agent/

# 2. Serviço runit
sudo mkdir -p /etc/sv/print-agent
sudo cp deploy/print-agent/run /etc/sv/print-agent/run
sudo chmod +x /etc/sv/print-agent/run
sudo cp deploy/print-agent/conf /etc/sv/print-agent/conf
# edite /etc/sv/print-agent/conf (URL do servidor, dispositivo etc.)

# 3. Ative o serviço
sudo ln -s /etc/sv/print-agent /var/service/
sv status print-agent
```

Logs: o serviço escreve em stdout/stderr (use um serviço de log do runit
se desejar arquivar).

## Primeiro uso — pareamento

1. No PDV (navegador): **Impressão → Estações → Criar estação** (ex.:
   "Caixa 01"). Anote o **código de pareamento** exibido (ex.: `ABC123`).
2. Na máquina da loja:

```bash
cd /opt/print-agent
PRINT_AGENT_SERVER_URL=https://pdv.sua-loja.com \
PRINT_AGENT_PAIR_CODE=ABC123 \
python3 -m app.main pair
```

3. O agente salva a credencial em `~/.print-agent/credencial.json` (0600)
   e o código é consumido (uso único). Depois disso basta `run`.

O código de pareamento pode ficar definido em
`/etc/sv/print-agent/conf` (`PRINT_AGENT_PAIR_CODE=`) na primeira
execução; após o pareamento, deixe a variável vazia.

## Uso

```bash
python3 -m app.main run       # loop: autentica, poll, imprime, reporta
python3 -m app.main pair      # apenas pareamento
python3 -m app.main test      # página de teste na impressora (ESC/POS)
python3 -m app.main raw-test  # teste em texto puro (printf > /dev/usb/lp0)
```

## Modo texto puro (printf) — alternativa para a Tomate MDK-080

A impressora térmica **Tomate MDK-080** tem driver oficial apenas para
Windows, mas funciona no Linux via `usblp`, escrevendo direto no
dispositivo:

```bash
printf "TESTE SEM SUDO\n\n\n" > /dev/usb/lp0
```

O agente reproduz esse comportamento **sem executar shell**: abre o
dispositivo em modo binário e escreve os bytes. Para impressoras de
firmware restrito como a MDK-080, use o modo texto puro:

```sh
export PRINTER_ESCPOS=0   # sem comandos ESC/POS; texto + \n\n\n (printf)
python3 -m app.main raw-test   # equivalente ao printf acima
```

Com `PRINTER_ESCPOS=0` o comprovante sai em texto puro (sem realce/corte
automático); com `PRINTER_ESCPOS=1` (padrão) o agente usa ESC/POS
(Elgin, Bematech, Epson etc.).

## Variáveis de ambiente

| Variável | Padrão | Descrição |
| --- | --- | --- |
| `PRINT_AGENT_SERVER_URL` | `http://127.0.0.1:8000` | URL pública do servidor Django. |
| `PRINTER_DEVICE` | `/dev/usb/lp0` | Dispositivo da térmica (usblp). |
| `PRINT_AGENT_PAIR_CODE` | — | Código de pareamento (uso único). |
| `PRINT_AGENT_LARGURA_PADRAO` | `58` | Largura usada quando o payload não informa. |
| `PRINTER_CODEPAGE` | `utf8` | `utf8` ou `cp850` (acentos via `ESC t 2`). |
| `PRINTER_ESCPOS` | `1` | `0` desativa ESC/POS (texto puro estilo printf; indicado p/ Tomate MDK-080). |
| `PRINTER_CORTE_PARCIAL` | `1` | `0` para corte total (`GS V 0`). |
| `PRINT_AGENT_POLL_INTERVAL` | `3` | Segundos entre polls. |
| `PRINT_AGENT_HTTP_TIMEOUT` | `30` | Timeout HTTP em segundos. |
| `PRINT_AGENT_STATE_DIR` | `~/.print-agent` | Estado local (credencial + dedupe). |
| `PRINT_AGENT_LOG_LEVEL` | `INFO` | Nível de log. |

## Comportamento

- **Polling**: o agente abre a conexão de saída (funciona atrás de
  NAT/CGNAT/firewall) e pergunta se há trabalho a cada
  `PRINT_AGENT_POLL_INTERVAL`.
- **Impressora desligada/desconectada**: o agente informa
  `disponivel=false`; o job permanece na fila do servidor (não é perdido,
  não conta tentativa).
- **Idempotência**: uuids já processados ficam em
  `~/.print-agent/processados.jsonl` (máx. 500). Se o servidor entregar o
  mesmo job de novo (reconexão), o agente apenas reconfirma o sucesso —
  **nunca reimprime sozinho**.
- **Falha**: reporta `FAILED` com o erro; o servidor agenda retry com
  backoff (5s → 15s → 60s → 300s → 900s) até esgotar as tentativas da
  loja. Para repetir depois de `FAILED`, use "Tentar novamente" no PDV.
- **Credencial recusada**: o agente encerra com erro pedindo novo
  pareamento.

## Testes

```bash
python3 -m unittest discover -s tests -t .
```

Os testes usam `FakePrinterDevice` (nunca tocam a impressora física).
