# Clientes da plataforma (onboarding)

## Objetivo

Gerenciar o ciclo comercial do cliente do SaaS: contato → lead → cadastro →
aprovação → criação do tenant → ativação.

**Atenção à terminologia:** "Cliente da plataforma" é quem contrata o
sistema. Não confundir com consumidor final de uma loja (módulo futuro do
PDV) nem com Tenant.

## Models (`apps.clients`)

### ClientePlataforma

- Identificação: `uuid`, `tipo_pessoa` (PF/PJ), `nome`, `razao_social`,
  `nome_fantasia`, `cpf_cnpj`.
- Contato: `email`, `telefone_celular`.
- Comercial: `origem`, `status`, `usuario_responsavel`, `observacao`.
- Endereço opcional (CEP, logradouro, etc.).
- Datas automáticas no backend (`data_cadastro`, `data_atualizacao`).

Regras:

- **CPF/CNPJ**: armazenado apenas com dígitos; validação de dígito
  verificador em `apps.core.validators`; unicidade garantida por constraint
  no banco. Opcional durante o onboarding (leads não possuem documento),
  **obrigatório para ativação**.
- **E-mail** normalizado para minúsculas no backend.

Status e transições válidas:

```
LEAD → EM_ANALISE → PENDENTE → ATIVO
ATIVO → SUSPENSO | CANCELADO
SUSPENSO → ATIVO
LEAD/EM_ANALISE/PENDENTE → CANCELADO
```

Transições fora desse grafo levantam `ClientServiceError`.

### ClienteHistorico

Auditoria própria do cliente: quem alterou, ação, status anterior/novo,
descrição e data. Criado automaticamente pelos services.

### Onboarding

Acompanhamento da ativação: status (INICIADO, DADOS_PENDENTES,
CONFIGURANDO, CONCLUIDO, CANCELADO), tenant associado, responsável e datas.
Criado na ativação do cliente.

### LeadContato

Contato recebido pelo formulário público `/contato/`. Um lead **não** cria
tenant nem cliente ativo automaticamente. A equipe analisa e converte via
Django Admin (action "Converter em cliente"), gerando um cliente com status
LEAD.

## Services (`apps.clients.services`)

Views e admin não contêm regras de negócio — usam os services:

| Service | Responsabilidade |
|---|---|
| `criar_cliente(...)` | Cria cliente + histórico inicial; valida documento/e-mail |
| `alterar_status(cliente, novo_status)` | Valida transições e registra histórico |
| `ativar_cliente(cliente)` | Transacional: exige PENDENTE + documento válido; cria/atribui tenant, cria onboarding, registra auditoria |
| `converter_lead(lead)` | Converte lead em cliente LEAD (sem tenant/usuário) |

### Ativação transacional

Se qualquer etapa falhar (ex.: erro ao criar tenant), nada é persistido —
o cliente nunca fica parcialmente ativado. Testes cobrem os cenários de
falha (`apps/clients/tests/test_services.py`).

## Django Admin

- `ClientePlataformaAdmin`: filtros por status/tipo/origem/data, busca por
  nome/documento/e-mail, inlines de histórico e onboarding, actions de
  aprovação (em análise, pendente, ativar, suspender, cancelar).
- `LeadContatoAdmin`: actions de conversão e descarte.

## Segurança

- Acesso restrito à equipe da plataforma (`is_staff`) — usuários de tenant
  recebem 302/403 em `/admin/clients/...`.
- LGPD: documento armazenado sem máscara, exibição controlada pelo admin;
  logs de auditoria usam UUID do cliente, nunca documento completo.
