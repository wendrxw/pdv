Agents.md — Contexto do Projeto PDV
1. Visão Geral do Projeto

Este projeto consiste em um sistema SaaS multi-tenant para gestão de PDV (Ponto de Venda), abrangendo:

    Cadastro de clientes da plataforma (onboarding)

    Produtos, estoque e inventário

    Módulo financeiro (entradas, saídas, contas a receber, análise)

    Módulo fiscal NFC-e (emissão, assinatura, transmissão SEFAZ)

    Landing page pública e área administrativa global

O sistema atende múltiplas empresas (tenants) de forma isolada, com um administrador global utilizando o Django Admin.
2. Stack Tecnológica

    Backend: Python + Django

    API/REST: Django REST Framework (apenas para futuras integrações)

    Banco de dados: PostgreSQL

    Cache/mensageria: Redis + Celery

    Frontend: Django Templates + TailwindCSS + HTML + JavaScript (vanilla)

    Servidor: Nginx + Cloudflare Tunnel

    Versionamento: Git + GitHub (fluxo com branches e Pull Requests)

NÃO utilizar frameworks frontend como React, Vue ou Angular.
3. Multi-tenancy — Regra Fundamental

    Todo dado operacional deve estar associado a um tenant.

    Um tenant NUNCA pode acessar dados de outro tenant.

    O isolamento é garantido no backend, nunca apenas no frontend.

    Identificadores como UUID, SKU ou código de barras não são mecanismos de isolamento.

    Sempre filtrar querysets com o tenant atual:

python

Model.objects.get(uuid=uuid, tenant=current_tenant)

    O tenant é determinado pelo contexto autenticado do usuário; nunca confiar em parâmetros enviados pelo frontend.

4. Módulos do Sistema
4.1. Cadastro de Clientes da Plataforma (Onboarding)

    Entidade Cliente representa a empresa/pessoa que contratou o sistema.

    Possui: uuid, nome, email, telefone, cpf_cnpj, tipo_pessoa, status (LEAD, PENDENTE, ATIVO, SUSPENSO, CANCELADO).

    Não confundir com cliente da loja (consumidor final).

    O cliente pode existir antes da criação do tenant.

    O fluxo: contato → lead → cadastro → aprovação → criação do tenant → convite do usuário.

4.2. Produtos, Estoque e Inventário

    Produto: uuid, nome, data_cadastro, tamanho, observacao, sku, codigo_barras, preco_custo, preco_venda.

    SKU e código de barras são únicos dentro do tenant, não globalmente.

    Geração de código de barras EAN‑13 para uso interno (não oficial).

    Estoque: modelo com quantidade, estoque_minimo, estoque_maximo, e histórico de movimentações.

    Movimentações: entrada, saída, ajuste, venda, devolução, inventário.

    Toda alteração de estoque deve gerar movimentação; nunca alterar saldo diretamente.

    Operações de estoque usam transações atômicas e select_for_update() quando necessário.

    Inventário: status (ABERTO, EM_CONTAGEM, EM_REVISAO, FINALIZADO, CANCELADO) e geração de ajustes.

4.3. Módulo Financeiro

Dividido em:

    Entradas (receitas)

    Saídas (despesas)

    Contas a Receber (com parcelamento)

    Análise financeira por período (caixa x competência)

Regras:

    Valores monetários sempre com Decimal, nunca float.

    Contas financeiras (Caixa, Banco, PIX) com saldo controlado por movimentações.

    Lançamentos separados de pagamentos/recebimentos (competência ≠ caixa).

    Status: PREVISTA, PENDENTE, RECEBIDA/PAGA, CANCELADA, ATRASADA.

    Isolamento por tenant.

4.4. Módulo Fiscal NFC-e

    Emissão de NFC-e modelo 65 para SEFAZ-SP (homologação inicial).

    Geração do XML conforme leiaute oficial, assinatura com certificado A1, validação XSD.

    Transmissão via SOAP, interpretação de retorno (autorização/rejeição).

    Operações: consultar, cancelar, inutilizar, consultar status.

    Persistência: XMLs, protocolo, chave de acesso, status fiscal (PENDENTE, AUTORIZADA, REJEITADA, CANCELADA).

    Idempotência obrigatória para evitar duplicidade.

    Não implementar contingência inicialmente.

5. Segurança

    Nunca registrar em logs: senha do certificado, chave privada, CPF/CNPJ completo, tokens.

    Utilizar bcrypt para hash de senhas.

    CSRF em todos os POSTs de alteração.

    Permissões baseadas no sistema existente (Groups, Permissions).

    Dados pessoais devem ser tratados conforme princípios da LGPD.

6. Django Admin — Painel Administrativo Global

    O administrador da plataforma utiliza o Django Admin para gerenciar todos os tenants.

    Somente usuários com is_staff podem acessar /admin/.

    Todos os models importantes devem ser registrados com configuração adequada:

        list_display, list_filter, search_fields, readonly_fields, autocomplete_fields, inlines, actions.

    Incluir filtro por tenant em todos os models tenant-aware.

    Não usar Django Admin como interface principal do tenant.

7. Landing Page

    Página pública em / em português do Brasil.

    Deve apresentar: hero, recursos, benefícios, como funciona, CTA para contato.

    Design minimalista, responsivo, com TailwindCSS.

    SEO básico: title, description, Open Graph.

    Formulário de contato em /contato/ que gera um lead (não cria tenant automaticamente).

8. Fluxo de Desenvolvimento (Git + GitHub)
8.1. Branches

    main = código estável (nunca trabalhar diretamente).

    Cada task possui sua própria branch: feat/<task-id>-descricao.

    A branch é criada a partir da main mais recente.

    Nunca basear uma branch em outra feature branch.

8.2. Tasks

    As tasks são arquivos Markdown dentro do diretório tasks/.

    Cada task define um escopo claro e é concluída com implementação, testes, documentação e PR.

8.3. Commits

    Commits concisos e informativos, seguindo Conventional Commits quando possível.

    Exemplo: feat(finance): add accounts receivable workflow.

8.4. Pull Requests

    Criar PR via gh pr create.

    O PR deve conter: resumo, alterações, testes, documentação, observações.

    O agente nunca mergeia o próprio PR; aguarda revisão humana.

8.5. CI/CD

    Executar testes, lint e migrations localmente antes do push.

    Verificar status do CI (GitHub Actions) e corrigir falhas.

9. Responsabilidades do Agente

    Ser autônomo na execução da task, sem pedir confirmação para etapas previsíveis.

    Analisar o projeto existente antes de implementar: identificar tenancy, models, views, templates, Tailwind, permissões.

    Não inventar regras de negócio; consultar documentação oficial (SEFAZ, Portal Nacional) para questões fiscais.

    Não criar nova arquitetura de tenancy, autenticação ou permissões; reutilizar a existente.

    Documentar implementações no diretório docs/.

    Revisar o próprio diff antes do PR.

    Não commitar segredos, arquivos temporários ou alterações não relacionadas.

    Se encontrar uma decisão crítica não especificada, parar e solicitar orientação ao proprietário.

10. Critérios de Aceite Gerais

    Multi-tenancy funcional com isolamento comprovado por testes.

    Todos os models importantes registrados no Django Admin.

    Landing page e contato funcionais.

    Módulo de produtos com cadastro, código de barras e estoque.

    Módulo financeiro com entradas, saídas, recebíveis e análise.

    Módulo fiscal NFC-e operacional em homologação (geração, assinatura, transmissão, consulta, cancelamento).

    Testes automatizados para segurança, integridade e isolamento.

    Documentação arquitetural e de uso.

## Procedimento padrão do agente (aplicar a todas as tasks)

1. **Leitura compulsória:** `agents.md`.
2. **Verificação do tenant:** Antes de qualquer `Model.objects.get()`, confirmar se existe filtro por `tenant`.
3. **Django Admin:** Todo novo model deve ser registrado no admin com list_display e filters.
4. **Commit:** Usar Conventional Commits.

## Acesso ao servidor de produção (ação padrão do agente)

O servidor de produção é um **Debian 12 i686 compartilhado** acessível por
SSH. Sempre que uma task envolver deploy, diagnóstico ou operação em
produção, usar este acesso como ação padrão:

- **Host:** `192.168.1.119` · **Usuário:** `servidor1` · **Sudo:** via senha.
- **Credenciais:** no arquivo LOCAL `deploy/servidor.ssh.env` (git-ignored —
  NUNCA versionar as credenciais; modelo em
  `deploy/servidor.ssh.env.example`).
- **Ferramenta padrão:** `deploy/ssh-servidor.py` (paramiko):

  ```bash
  uv run --with paramiko --no-project deploy/ssh-servidor.py "comando"
  uv run --with paramiko --no-project deploy/ssh-servidor.py "comando" --sudo
  uv run --with paramiko --no-project deploy/ssh-servidor.py --upload arquivo /caminho/destino
  ```

### Regras de operação no servidor

1. **AUDITAR ANTES DE MUDAR:** `ss -lntp`, `systemctl list-units
   --type=service --state=running`, `ls /etc/nginx/sites-enabled`,
   `cloudflared tunnel list` — entender o que roda antes de tocar.
2. **Servidor compartilhado:** hospeda outros projetos (farol em
   `/srv/apps/farol`, gunicorn :8000, PostgreSQL 15, Redis, Docker,
   túnel Cloudflare `farol`). Nunca alterar/remover serviços de terceiros;
   validar que continuam funcionando depois de qualquer mudança.
3. **Backup antes de alterar:** `/etc/nginx`, `/etc/cloudflared`,
   `/etc/systemd/system` → `/root/backups-pdv-<data>`.
4. **Nginx:** sempre `nginx -t` antes de `systemctl reload nginx`; não
   usar `listen [::]:80` em servidor compartilhado (quebra roteamento
   IPv6 dos túneis para sites que escutam só IPv4).
5. **PDV em produção:** app em `/srv/apps/pdv` (git em `main`), venv
   Python 3.11, `pdv.service` (gunicorn 127.0.0.1:8001 com
   EnvironmentFile `.env`), site nginx `pdv`, túnel Cloudflare `pdv`
   (`pdv-tunnel.service`), PostgreSQL role/db `pdv`.
   Deploy = `git pull --ff-only origin main` + restart `pdv` + (se
   houver) `migrate`/`collectstatic`. O script `deploy/setup-pdv.sh`
   faz a instalação inicial completa.
6. **Segredos:** nunca imprimir/versionar SECRET_KEY, senhas de banco ou
   certificados; `.env` fica em `/srv/apps/pdv/.env` (chmod 600).
7. **Rollback:** reverter imediatamente a alteração responsável se algo
   quebrar serviço existente; backups em `/root/backups-pdv-*`.