# Impressão em Produção — Estudo Técnico e Plano de Implantação

> Documento de estudo. Implementação atual: [docs/print.md](print.md).
> Objetivo: preparar o caminho do ambiente de desenvolvimento (servidor e
> impressora na MESMA máquina) para o cenário real de produção.

## 1. Contexto e problema

**Hoje (desenvolvimento)**: o servidor Django roda na máquina de teste e a
impressora térmica está conectada por USB na mesma máquina. O Local Print
Agent escreve direto em `/dev/usb/lp0` — funciona, mas **esse arranjo não
pode ir para produção como está**.

**Produção real**:

```
SERVIDOR LINUX (remoto)                    LOJA DO CLIENTE
┌────────────────────────────┐            ┌──────────────────────────────┐
│ Django + PostgreSQL        │            │ Computador (Void Linux)      │
│ PrintJobs (fila)           │◄── HTTPS ──│ Local Print Agent (polling)  │
│ API /api/print-agent/      │   saída    │      │                       │
└────────────────────────────┘            │      ▼ USB (usblp)           │
                                          │ /dev/usb/lp0                 │
                                          │ IMPRESSORA TÉRMICA (MDK-080) │
                                          └──────────────────────────────┘
```

- O servidor **nunca terá** acesso ao `/dev/usb/lp0` da loja;
- a loja está atrás de NAT/CGNAT/firewall (roteador doméstico/comercial):
  o servidor **não consegue abrir conexão de entrada**;
- a máquina da loja usa Void Linux (runit) e a impressora só tem driver
  Windows — a comunicação no Linux é via `usblp` + escrita direta no
  dispositivo, sem sudo (usuário no grupo `lp`).

**Conclusão**: a arquitetura correta já está implementada (PrintJob no
servidor + Local Print Agent na loja com conexão de saída). O trabalho de
produção é **operacionalizar** essa arquitetura: HTTPS obrigatório,
instalação/pareamento na loja, validação de falhas e monitoramento.

## 2. Análise das alternativas de arquitetura

| Alternativa | Como funciona | Vantagens | Problemas | Veredito |
| --- | --- | --- | --- | --- |
| **A. Local Print Agent + polling HTTPS (saída)** | Processo Python na loja consulta a fila do servidor, imprime e reporta. | Funciona atrás de NAT/CGNAT; sem porta aberta na loja; impressora nunca exposta; zero dependências (stdlib); já implementado. | Latência de até ~3s (intervalo de poll); precisa de processo instalado na loja. | **ESCOLHIDO** (já em produção de código) |
| B. Servidor abre conexão TCP direta com a loja | Servidor conecta na impressora/agente da loja. | Sem polling. | Impossível com NAT/CGNAT/firewall; exigiria porta pública ou VPN por loja. | Descartado |
| C. Impressão pelo navegador (WebUSB/Web Serial) | O próprio navegador do caixa acessa a impressora USB. | Sem processo extra. | `usblp` não expõe a impressora como dispositivo WebUSB; exige driver no navegador; acopla impressão ao navegador aberto (falha se fechar); segurança frágil. | Descartado como padrão (alternativa futura p/ quiosques) |
| D. CUPS + IPP remoto (porta 631) | Compartilhar a impressora via CUPS/IPP para o servidor imprimir nela. | Padrão de mercado. | Exige expor a impressora na internet ou VPN; administração por loja; adiciona superfície de ataque; dependência de CUPS (desnecessário: `usblp` direto funciona). | Descartado (no máximo como fallback LOCAL na loja) |
| E. Serviço de nuvem de impressão de terceiros | Filas gerenciadas por SaaS. | Sem infra própria. | Custo recorrente; dados da venda em terceiros (LGPD); dependência externa. | Descartado |
| F. WebSocket em vez de polling | Conexão persistente do agente para o servidor. | Latência ~0. | Projeto ainda não usa Channels/ASGI; ganho irrelevante para comprovante (o papel leva ~1s para sair). | Adiado para roadmap |

### Decisão

Manter a alternativa **A** (Local Print Agent, polling HTTPS de saída,
autenticação por estação com token + pareamento por código). Detalhes de
implementação em [docs/print.md](print.md).

## 3. Estado atual do código — gap analysis

O que já existe e funciona (validado na máquina de teste):

| Componente | Estado |
| --- | --- |
| `apps/printing`: PrintJob (PENDING/RETRYING/PROCESSING/PRINTED/FAILED), estações com pareamento, config por loja, admin | OK + testado (346 testes) |
| API `/api/print-agent/` (pair/poll/resultado) com token bcrypt | OK |
| Painel do PDV com estados (aguardando agente/impressora, imprimindo, impresso, falha) | OK |
| `local-print-agent`: ESC/POS + texto puro (printf), cp850/cp860/cp1252 p/ MDK-080, folga de corte, dedupe por uuid, retry/backoff, runit | OK + testado (49 testes) |
| Idempotência e lease de PROCESSING órfão | OK |

Gaps identificados para produção (numerados conforme o plano da §5):

1. **HTTPS** — em dev a API roda em HTTP; o token de estação trafega nos
   cabeçalhos e **exige TLS em produção**.
2. **Rate limiting** — pair/poll têm apenas um freio de 0,5s por falha de
   autenticação; suficiente para começar, mas sem conta por IP.
3. **Monitoramento de estação offline** — `ultima_atividade` é gravada a
   cada poll, mas não há alerta quando uma estação para de responder.
4. **Versionamento do agente** — o payload tem `versao: 1`, mas o agente
   não envia versão própria e o servidor não exige versão mínima.
5. **Atualização do agente** — hoje é manual (copiar arquivos); não há
   mecanismo de update remoto (fora de escopo imediato).
6. **Logs/rotação** — agente loga em stdout; com runit usar `svlogd`
   (log/run) para arquivar e rotacionar.

## 4. Análise técnica dos pontos críticos

### 4.1 Segurança do canal e credenciais

- **Credencial por estação**: `parear_estacao` consome um código curto de
  uso único (alfabeto sem 0/O/1/I, ~1,07×10⁹ combinações) e devolve o
  token UMA vez; o banco guarda apenas o hash bcrypt (`make_password`),
  comparado com `check_password` (tempo constante).
- **Pareamento e tráfego via HTTPS**: em produção todo o fluxo (pair
  inclusive) deve trafegar em TLS — senão o token é capturável na rede.
- **Escopo mínimo do token**: um agente só consegue (a) listar o próximo
  job do PRÓPRIO tenant e (b) reportar resultado de jobs que ELE
  reivindicou. Comprometer um agente não dá acesso ao Django, a outros
  tenants nem a segredos da plataforma.
- **Nunca no agente**: SECRET_KEY, senhas do Django, certificado A1.
  O único segredo é o token da própria estação, em
  `~/.print-agent/credencial.json` com permissão 0600.
- **Rotação/revogação**: desparear/inativar a estação na tela
  Impressão → Estações invalida a credencial imediatamente.
- **Ameaças residuais e mitigações planejadas**: brute-force no par
  (freio 0,5s + código de uso único; evoluir p/ lockout por IP),
  replay de request (TLS), agente adulterado na loja (escopo mínimo,
  logs e re-pareamento).

### 4.2 Topologia de rede na loja

- O agente **só abre conexões de saída** para `PRINT_AGENT_SERVER_URL`
  (porta 443): nenhum redirecionamento de porta, DMZ ou IP fixo é
  necessário na loja.
- Carga: 1 poll/3s ≈ 28.800 requests/dia por estação; com resposta vazia
  (~150 B) ≈ 4 MB/dia por estação — desprezível.
- DNS/TLS: urllib abre uma conexão por poll (sem keep-alive). Aceitável;
  manter o timeout em 30s e o backoff de rede (5s→60s) já implementado.

### 4.3 Confiabilidade — entrega "exatamente uma vez"

- **Idempotência**: `uuid` do PrintJob é a chave. O agente grava em
  `processados.jsonl` (máx. 500) os uuids já tratados; se o servidor
  redelivers (reconexão, reporte perdido), o agente apenas **reconfirma**
  sem reimprimir.
- **Impressão parcial**: a térmica pode ter recebido metade do job antes
  de falhar; por isso falha NUNCA reimprime automaticamente no mesmo
  ciclo — vira RETRYING com backoff (5s/15s/60s/300s/900s) e, esgotadas
  as tentativas, FAILED com "Tentar novamente" manual no PDV.
- **PROCESSING órfão**: lease de 5 min devolve à fila (impressora morreu
  no meio).
- **Agente offline / impressora desligada**: o job permanece na fila
  (impressora desligada nem consome tentativa — `disponivel=false`).
- **Persistência**: tudo vive no PostgreSQL do servidor; a loja não
  perde nada se o computador reiniciar (estado local só evita duplicata).

### 4.4 Compatibilidade de hardware (Tomate MDK-080 e similares)

- Caminho validado em campo: `usblp` → `/dev/usb/lp0` (grupo `lp`), sem
  driver proprietário, sem CUPS, sem sudo.
- MDK-080: firmware interpreta bytes como tabela de 1 byte → usar
  `PRINTER_ESCPOS=0` (texto puro) + `PRINTER_CODEPAGE=cp850`
  (cp860/cp1252 como alternativas; `codepage-test` identifica no papel).
- `PRINTER_ALIMENTACAO_FINAL` (padrão 8 linhas) garante folga para o
  corte/rasgo não pegar o conteúdo.
- Riscos: impressoras futuras sem suporte `usblp` (chip novo) — fallback
  planejado: CUPS **apenas na máquina da loja** com o agente imprimindo
  via backend CUPS em vez de escrita direta (mesma interface
  `PrinterDevice`, nova implementação).

### 4.5 Multi-tenant e atribuição de trabalhos

- Estação pertence a um tenant; poll/resultado são isolados pelo tenant
  da estação (testado cross-tenant).
- Job sem estação (`estacao=None`) pode ser assumido por qualquer estação
  ativa do tenant; `estacao_padrao` da loja direciona quando necessário.
- PrintJobs sem dono ativo ficam PENDING e o painel do PDV avisa
  "Aguardando o agente de impressão da loja…".

## 5. Plano de implantação (passos a executar)

### Fase 0 — Servidor

> Guia completo passo a passo do servidor (sistema, banco, gunicorn,
> nginx, HTTPS, backups, monitoramento e passos específicos da
> impressão): [docs/producao-servidor.md](producao-servidor.md).

1. Deploy Django em produção: PostgreSQL (`PDV_DB_ENGINE=postgres` +
   `PDV_DB_*`), `DJANGO_DEBUG=False`, `DJANGO_SECRET_KEY` forte,
   `DJANGO_ALLOWED_HOSTS` correto (padrão do projeto já cobre HSTS,
   cookies seguros e SSL redirect).
2. **HTTPS obrigatório** para `/api/print-agent/`: Cloudflare Tunnel
   (padrão do projeto: Nginx + Cloudflare Tunnel) ou Nginx +
   Let's Encrypt. Sem TLS, o token de estação trafega em claro.
3. Aplicar migrations (`printing.0001` e `0002`) e smoke test da API:
   - `POST pair/` com código inválido → `400`;
   - `POST poll/` sem credencial → `401`;
   - parear uma estação de teste e conferir `poll` → `{"job": null}`.
4. (Aprimoramento recomendado) `POST pair/` com lockout por IP e log de
   pareamentos; view/action no admin de estações com
   `ultima_atividade` para detectar estação offline.

### Fase 1 — Máquina da loja (Void Linux, runit)

5. Instalar o agente: copiar `local-print-agent/app/` para
   `/opt/print-agent/` (sem venv — usa só stdlib).
6. Serviço runit: copiar `deploy/print-agent/run` e `conf` para
   `/etc/sv/print-agent/`, ajustar o `conf` e ativar
   (`ln -s /etc/sv/print-agent /var/service/`). Adicionar `log/run` com
   `svlogd` para arquivar os logs.
7. Configurar conforme a impressora (MDK-080):
   ```sh
   export PRINT_AGENT_SERVER_URL=https://pdv.dominio.com
   export PRINTER_DEVICE=/dev/usb/lp0
   export PRINTER_ESCPOS=0
   export PRINTER_CODEPAGE=cp850
   export PRINT_AGENT_LARGURA_PADRAO=80   # MDK-080 = 80mm
   export PRINTER_ALIMENTACAO_FINAL=8
   ```
8. Verificar pré-requisitos na loja: usuário no grupo `lp`
   (`groups | grep lp`), `ls -l /dev/usb/lp0` gravável, e validar com
   `python -m app.main raw-test` e `python -m app.main codepage-test`.
9. Parear pela interface do PDV (Impressão → Estações → criar estação →
   copiar código) e no terminal: `PRINT_AGENT_PAIR_CODE=ABC123 python -m
   app.main pair`; depois iniciar o serviço e conferir `sv status`.

### Fase 2 — Validação ponta a ponta

10. Venda de teste: finalizar pagamento → painel mostra
    "Aguardando impressora…" → "Imprimindo..." → "✓ Comprovante
    impresso"; conferir no papel: itens, valores, acentos (cp850),
    folga de corte e mensagem final.
11. Testes de falha:
    - impressora desligada → job permanece na fila (painel "Aguardando
      impressora…"); ligar → imprime;
    - rede derrubada no agente → job pendente; religar → retoma sozinho;
    - sem papel → retry com backoff e depois "⚠ + Tentar novamente";
    - matar o agente no meio de um job → lease devolve à fila e o uuid
      impede impressão duplicada.
12. Conferir PrintJobs no Django Admin (estados, tentativas, erro,
    data_impressao) e registros de auditoria.

### Fase 3 — Operação e monitoramento

13. Rotina de verificação: estação com `ultima_atividade` atrasada (>
    10 min) = agente caído; runbook de diagnóstico em
    [docs/print.md](print.md#troubleshooting) (raw-test, codepage-test,
    grupo lp, sv status).
14. Procedimentos documentados: re-pareamento (desparear → novo código),
    troca de impressora (ajustar `PRINTER_DEVICE`/largura), backup do
    servidor (fila de jobs vive no banco).

### Roadmap (fora do escopo imediato)

- WebSocket quando o projeto adotar Channels (latência ~0);
- fallback CUPS local (impressoras sem `usblp`);
- alerta automático de estação offline e relatório de falhas;
- versão mínima do agente exigida pelo servidor + auto-update;
- rate limiting por IP na API do agente.

## 6. Check-list de aceite para produção

Legenda: `[x]` validado no ambiente de teste (esta máquina, impressora real);
`[ ]` pendente do servidor real de produção.

- [x] API responde com autenticação e erros corretos (pair inválido → 400;
  poll sem credencial → 401; força bruta bloqueada com 429 após 20 falhas).
- [ ] API em HTTPS com certificado válido (requer o servidor real; artefatos
  prontos em `deploy/`: nginx, env e Cloudflare Tunnel).
- [x] Estação pareada e agente rodando na máquina da loja (serviço runit
  pronto em `local-print-agent/deploy/print-agent/`; instalar com
  `sudo sh instalar.sh`).
- [x] `raw-test` e `codepage-test` aprovados no papel (acentos corretos —
  MDK-080 usa `PRINTER_ESCPOS=0` + `PRINTER_CODEPAGE=cp850`).
- [x] Venda real: comprovante sai completo, acentuado, com folga de corte
  (validação ponta a ponta: venda finalizada via HTTP → agente → PRINTED).
- [x] Agente offline: job permanece PENDING e imprime quando o agente volta.
- [x] Impressora desligada: job permanece PENDING (tentativa 0) e imprime
  ao religar.
- [x] Painel do PDV reflete todos os estados sem enganar o operador.
- [ ] Falha física (sem papel) termina em ⚠ + "Tentar novamente" — coberto
  por testes automatizados; pendente validação física.
- [x] Estação sem atividade detectável: `python manage.py check_print_agents
  --minutos 10` (exit 1 quando houver estação atrasada; pronto para cron).
- [x] Nenhuma porta aberta na loja; nenhum segredo do Django no agente
  (credencial local 0600, escopo mínimo do token).

## 7. Status de execução

| Item | Onde | Estado |
| --- | --- | --- |
| Throttle por IP (429 após 20 falhas) + auditoria de pareamento | `apps/printing/api.py`, `services.py` | Implementado + testado |
| Monitoramento de estação offline | `python manage.py check_print_agents` | Implementado + testado |
| gunicorn (WSGI de produção) | `pyproject.toml` | Adicionado (v26.1.0) |
| Artefatos de deploy do servidor | `deploy/` (nginx, env, Cloudflare Tunnel) | Prontos |
| Instalador runit da loja + svlogd | `local-print-agent/deploy/print-agent/instalar.sh`, `log-run` | Prontos (executar com sudo) |
| Validação ponta a ponta + falhas | Esta máquina (impressora real) | Aprovada |
