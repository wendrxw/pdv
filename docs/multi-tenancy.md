# Multi-tenancy

## Objetivo

Este documento descreve como o isolamento entre tenants funciona no PDV,
como o tenant é determinado e como desenvolver novos módulos respeitando
a regra fundamental do projeto.

## Conceitos

| Conceito | Descrição | App |
|---|---|---|
| **Cliente da plataforma** | Pessoa/empresa que contrata o sistema SaaS | `apps.clients` |
| **Tenant** | Ambiente operacional isolado de uma empresa | `apps.companies` |
| **Usuário** | Pessoa com acesso ao sistema | `apps.accounts` |

Relação:

```
ClientePlataforma 1—0..1 Onboarding *—1 Tenant 1—* User
```

Um cliente pode ainda não ter tenant (fase comercial/onboarding). O tenant
é criado na ativação do cliente (`apps.clients.services.ativar_cliente`).

## Regra fundamental

> Um tenant NUNCA acessa dados de outro tenant. O isolamento é garantido no
> backend — nunca por UUID, SKU, código de barras ou parâmetros do frontend.

### Como o tenant é determinado

O tenant vem sempre do contexto autenticado:

```python
tenant = request.user.get_tenant()   # None para equipe da plataforma
```

O frontend nunca informa o tenant. Qualquer parâmetro como `tenant_id`
recebido do frontend deve ser ignorado em decisões de autorização.

## Infraestrutura (`apps.core.tenancy`)

- **`TenantQuerySet`**: queryset com `for_tenant(tenant)`.
- **`TenantManager`**: manager padrão dos models tenant-aware.
- **`TenantAwareModel`**: base abstrata; todo model operacional deve herdar
  dela (ou replicar o padrão), garantindo FK obrigatória `tenant`.

Exemplo de uso em um novo model:

```python
from apps.core.tenancy import TenantAwareModel

class Produto(TenantAwareModel):
    tenant = models.ForeignKey("companies.Tenant", on_delete=models.PROTECT)
    ...
```

Consulta segura (sempre condicionada ao tenant):

```python
Produto.objects.get(uuid=uuid, tenant=request.user.get_tenant())
# ou
Produto.objects.for_tenant(request.user.get_tenant()).get(uuid=uuid)
```

**Nunca** faça `Produto.objects.get(uuid=uuid)` sem filtro de tenant.

## Usuários

- Usuário de tenant: `user.tenant` obrigatório; só enxerga dados do próprio
  tenant.
- Equipe da plataforma: `is_staff=True`, sem tenant (`user.is_plataforma`);
  acesso global via Django Admin.

## Django Admin

O Django Admin opera em perspectiva global (administrador vê todos os
tenants). Todo model tenant-aware registrado no admin deve incluir:

```python
list_filter = ("tenant", ...)   # filtro por tenant
list_display = (..., "tenant", ...)
```

## Checklist para novo código

1. O model é operacional? Deve ter FK `tenant` (herdar `TenantAwareModel`).
2. Toda consulta considera o tenant do usuário autenticado?
3. Nenhum `objects.get()` sem filtro de tenant?
4. Admin registrado com `list_display`, filtros (incluindo tenant) e busca?
5. Testes de isolamento criados (tenant A não acessa tenant B)?

## Testes

Referência: `apps/core/tests/test_tenancy.py`. Cobrem:

- usuário vinculado ao tenant correto;
- equipe da plataforma sem tenant;
- dashboard exibindo apenas dados do tenant do usuário;
- bloqueio de `/admin/` para usuários comuns.
