"""Regras de negócio do módulo de clientes do tenant.

Views e admin apenas orquestram; as regras vivem aqui. Toda consulta é
isolada pelo tenant do usuário autenticado.
"""

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q

from apps.audit.models import registrar

from .models import Cliente


class CustomerError(Exception):
    """Erro de domínio do módulo de clientes."""


def buscar_clientes(tenant, *, termo="", status=""):
    """Queryset de clientes com filtros opcionais.

    status: "" (todos), "ativos", "inativos".
    """
    queryset = Cliente.objects.for_tenant(tenant)
    if termo:
        queryset = queryset.filter(
            Q(nome__icontains=termo)
            | Q(cpf_cnpj__icontains=termo)
            | Q(email__icontains=termo)
            | Q(telefone__icontains=termo)
        )
    if status == "ativos":
        queryset = queryset.filter(ativo=True)
    elif status == "inativos":
        queryset = queryset.filter(ativo=False)
    return queryset.distinct()


@transaction.atomic
def criar_cliente(*, tenant, usuario=None, **dados):
    """Cria um cliente validando os dados antes de persistir."""
    cliente = Cliente(tenant=tenant, **dados)
    try:
        cliente.full_clean()
    except ValidationError as exc:
        raise CustomerError(f"Dados inválidos: {exc.message_dict}") from exc
    cliente.save()
    registrar(
        "CLIENTE_CRIADO",
        entidade=cliente,
        usuario=usuario,
        tenant=tenant,
        descricao=f"Cliente {cliente.nome} criado.",
    )
    return cliente


@transaction.atomic
def alterar_cliente(cliente, *, usuario=None, **dados):
    """Altera um cliente mantendo o tenant original."""
    alteravel = [campo for campo in dados if campo != "tenant"]
    for campo, valor in dados.items():
        setattr(cliente, campo, valor)
    try:
        cliente.full_clean()
    except ValidationError as exc:
        raise CustomerError(f"Dados inválidos: {exc.message_dict}") from exc
    cliente.save(update_fields=[*alteravel, "data_atualizacao"])
    registrar(
        "CLIENTE_ALTERADO",
        entidade=cliente,
        usuario=usuario,
        tenant=cliente.tenant,
        descricao=f"Cliente {cliente.nome} alterado.",
        dados={"campos": sorted(alteravel)},
    )
    return cliente


@transaction.atomic
def desativar_cliente(cliente, *, usuario=None):
    cliente.ativo = False
    cliente.save(update_fields=["ativo", "data_atualizacao"])
    registrar(
        "CLIENTE_DESATIVADO",
        entidade=cliente,
        usuario=usuario,
        tenant=cliente.tenant,
        descricao=f"Cliente {cliente.nome} desativado.",
    )
    return cliente


@transaction.atomic
def reativar_cliente(cliente, *, usuario=None):
    cliente.ativo = True
    cliente.save(update_fields=["ativo", "data_atualizacao"])
    registrar(
        "CLIENTE_REATIVADO",
        entidade=cliente,
        usuario=usuario,
        tenant=cliente.tenant,
        descricao=f"Cliente {cliente.nome} reativado.",
    )
    return cliente
