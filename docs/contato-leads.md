# Pedidos de contato (Leads) — funil de vendas

> Task: `tasks/fix_09_03_2026.md` (item 9).

## Fluxo

```
Visitante (site público)          Equipe da plataforma (ONEMANCOMPANY)
┌────────────────────────┐        ┌──────────────────────────────────┐
│ /contato/  formulário  │  POST  │ Painel → "Pedidos de contato"    │
│   nome, e-mail, tel.,  │───────►│  lista detalhada + filtros       │
│   empresa, mensagem    │        │  detalhe → mensagem completa     │
└────────────────────────┘        │  ações: em atendimento, converter,│
                                  │  descartar                       │
                                  └──────────────────────────────────┘
```

## Modelo de dados

`apps.clients.models.LeadContato` — um contato do site é apenas um LEAD:
**não** cria tenant nem cliente ativo automaticamente.

- `nome`, `email`, `telefone`, `empresa`, `mensagem`;
- `status`: `NOVO` → `EM_ATENDIMENTO` → `CONVERTIDO` (ou `DESCARTADO`);
- `cliente_convertido`: vínculo criado pela ação "Converter em cliente";
- `ip_origem` e `data_criacao` para auditoria.

## Notificação por e-mail

Ao salvar um contato válido, o sistema envia um aviso para a equipe
(configurável via `PDV_CONTATO_EMAIL`). O envio é melhor-esforço e nunca
bloqueia o salvamento do lead (falha é apenas registrada em log).

## Painel da equipe

- `web:contatos` (`/painel/contatos/`) — lista com busca, filtro por
  status e paginação (acesso restrito a `is_staff`).
- `web:contato_detalhe` (`/painel/contatos/<uuid>/`) — mensagem completa,
  dados do contato e ações de gestão do funil.
- Conversão reutiliza `apps.clients.services.converter_lead` (mesmo fluxo
  do Django Admin), preservando a consistência do funil.

O acesso ao Django Admin (`/admin/`, `LeadContato`) permanece disponível;
o painel acima é a interface dedicada e mais simples para o dia a dia.
