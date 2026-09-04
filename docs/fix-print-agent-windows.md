# Local Print Agent — Reconhecimento de impressoras no Windows (plano de ação)

> Task: `tasks/fix_09_03_2026.md` (item 6 e 8).

## 1. Diagnóstico (causa raiz)

No Windows o agente identifica a impressora pelo **nome do spooler**
(ex.: `"Elgin L42 PRO"`), enquanto no Linux usa o dispositivo
`/dev/usb/lp0`. O problema: o `Config.from_env()` usava o padrão Linux
`/dev/usb/lp0` **em qualquer sistema**, inclusive no Windows.

Consequência: na configuração interativa do primeiro uso, a condição
`if not config.device` nunca era verdadeira (o valor era `/dev/usb/lp0`),
então o agente **nunca perguntava qual era a impressora de comprovantes**.
Ele seguia tentando usar `/dev/usb/lp0` no Windows — caminho que não
existe — e, por isso, "o sistema não reconhecia os equipamentos".

## 2. Correção

- `local-print-agent/app/config.py`: em `from_env()`, o dispositivo padrão
  passa a ser **vazio no Windows** (`""`) e `/dev/usb/lp0` no Linux. Com o
  valor vazio, a configuração interativa pergunta (e lista) a impressora.
- `local-print-agent/app/main.py`:
  - `_precisa_escolher_dispositivo()` também trata o caso de um
    dispositivo estilo `/dev/...` salvo no Windows (migração de usuários
    que já rodaram a versão antiga).
  - `_listar_impressoras_windows()` agora enumera impressoras **locais e
    de conexão (rede)**, remove duplicadas e coloca a **impressora padrão**
    em primeiro lugar (facilita a escolha).
  - novo comando `print-agent listar-impressoras` para diagnóstico.

## 3. Impressoras fiscal e de etiquetas (item 8)

O servidor agora registra a **impressora fiscal/não fiscal** por tenant
(`ConfiguracaoImpressao.impressora_fiscal`) e já registrava a impressora
de etiquetas (`ConfiguracaoEtiqueta.nome_impressora`). O nome escolhido é
enviado no payload de cada trabalho e o agente o respeita:

- payload de comprovante: `impressora` (fiscal);
- payload de etiqueta: `impressora` (etiquetas).

`PrintAgent._dispositivo_para_job()` abre a impressora indicada pelo
servidor; se ela estiver indisponível, cai para o dispositivo configurado
localmente no agente (nunca perde o trabalho).

## 4. Testes

- **Unitários (agente):** `tests/test_config_autostart.py`
  (`test_from_env_windows_device_padrao_vazio`,
  `test_from_env_linux_device_padrao_usblp`) e `tests/test_agent.py`
  (roteamento por impressora do payload, fallback, sem impressora usa
  padrão).
- **Unitários (servidor):** `apps/printing/tests/test_services.py`
  (payload leva `impressora_fiscal`) e `test_views.py` (atalho da Frente
  de Caixa).
- **Integração:** o workflow `.github/workflows/build-windows-agent.yml`
  já faz smoke test e pareamento E2E do `print-agent.exe`. O build continua
  valendo; o reconhecimento de impressoras usa o mesmo `win32print`
  (pywin32) já empacotado no exe.

## 5. Usabilidade

- Primeiro uso no Windows (duplo clique no exe): pergunta servidor,
  código de pareamento e **lista as impressoras** (com a padrão em
  primeiro) para escolher comprovante e etiquetas.
- `print-agent listar-impressoras` mostra o que o agente enxerga sem
  imprimir nada.
