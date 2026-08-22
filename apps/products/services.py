"""Regras de negócio do módulo de produtos.

Views e admin apenas orquestram; as regras vivem aqui. Toda consulta por
identificador passa obrigatoriamente pelo tenant atual.
"""

from django.core.exceptions import ValidationError
from django.db import transaction

from apps.audit.models import registrar

from .models import Categoria, Marca, Produto


class ProductServiceError(Exception):
    """Erro de domínio do módulo de produtos."""


def _validar_relacoes_tenant(tenant, categoria=None, marca=None):
    """Garante que categoria/marca informadas pertencem ao tenant."""
    if categoria is not None and categoria.tenant_id != tenant.id:
        raise ProductServiceError("Categoria não pertence ao tenant.")
    if marca is not None and marca.tenant_id != tenant.id:
        raise ProductServiceError("Marca não pertence ao tenant.")


def obter_produto(tenant, uuid):
    """Obtém um produto do tenant pelo UUID (isolamento garantido)."""
    return Produto.objects.for_tenant(tenant).get(uuid=uuid)


def buscar_produtos(
    tenant,
    *,
    termo="",
    categoria=None,
    marca=None,
    status="",
):
    """Queryset de listagem com filtros opcionais.

    status: "" (todos), "ativos", "inativos".
    """
    queryset = Produto.objects.for_tenant(tenant).select_related(
        "categoria", "marca"
    )
    if termo:
        from django.db.models import Q

        queryset = queryset.filter(
            Q(nome__icontains=termo)
            | Q(sku__icontains=termo)
            | Q(codigo_barras__icontains=termo)
        )
    if categoria:
        queryset = queryset.filter(categoria=categoria)
    if marca:
        queryset = queryset.filter(marca=marca)
    if status == "ativos":
        queryset = queryset.filter(ativo=True)
    elif status == "inativos":
        queryset = queryset.filter(ativo=False)
    return queryset.distinct()


@transaction.atomic
def criar_categoria(*, tenant, nome, descricao="", usuario=None):
    categoria = Categoria(tenant=tenant, nome=nome, descricao=descricao)
    categoria.full_clean()
    categoria.save()
    registrar(
        "CATEGORIA_CRIADA",
        entidade=categoria,
        usuario=usuario,
        tenant=tenant,
        descricao=f"Categoria {categoria.nome} criada.",
    )
    return categoria


@transaction.atomic
def criar_marca(*, tenant, nome, usuario=None):
    marca = Marca(tenant=tenant, nome=nome)
    marca.full_clean()
    marca.save()
    registrar(
        "MARCA_CRIADA",
        entidade=marca,
        usuario=usuario,
        tenant=tenant,
        descricao=f"Marca {marca.nome} criada.",
    )
    return marca


@transaction.atomic
def criar_produto(*, tenant, usuario=None, **dados):
    """Cria um produto validando relações e dados antes de persistir."""
    categoria = dados.get("categoria")
    marca = dados.get("marca")
    _validar_relacoes_tenant(tenant, categoria=categoria, marca=marca)

    produto = Produto(tenant=tenant, **dados)
    try:
        produto.full_clean()
    except ValidationError as exc:
        raise ProductServiceError(f"Dados inválidos: {exc.message_dict}") from exc
    produto.save()
    registrar(
        "PRODUTO_CRIADO",
        entidade=produto,
        usuario=usuario,
        tenant=tenant,
        descricao=f"Produto {produto.nome} criado.",
    )
    return produto


@transaction.atomic
def alterar_produto(produto, *, usuario=None, **dados):
    """Altera um produto existente mantendo o tenant original."""
    categoria = dados.get("categoria", produto.categoria)
    marca = dados.get("marca", produto.marca)
    _validar_relacoes_tenant(produto.tenant, categoria=categoria, marca=marca)

    alteravel = [f for f in dados if f != "tenant"]
    for campo, valor in dados.items():
        setattr(produto, campo, valor)
    try:
        produto.full_clean()
    except ValidationError as exc:
        raise ProductServiceError(f"Dados inválidos: {exc.message_dict}") from exc
    produto.save(update_fields=[*alteravel, "data_atualizacao"])
    registrar(
        "PRODUTO_ALTERADO",
        entidade=produto,
        usuario=usuario,
        tenant=produto.tenant,
        descricao=f"Produto {produto.nome} alterado.",
        dados={"campos": sorted(alteravel)},
    )
    return produto


@transaction.atomic
def desativar_produto(produto, *, usuario=None, motivo=""):
    """Desativa o produto (soft delete — histórico deve ser preservado)."""
    produto.ativo = False
    produto.save(update_fields=["ativo", "data_atualizacao"])
    registrar(
        "PRODUTO_DESATIVADO",
        entidade=produto,
        usuario=usuario,
        tenant=produto.tenant,
        descricao=motivo or f"Produto {produto.nome} desativado.",
    )
    return produto


@transaction.atomic
def reativar_produto(produto, *, usuario=None):
    produto.ativo = True
    produto.save(update_fields=["ativo", "data_atualizacao"])
    registrar(
        "PRODUTO_REATIVADO",
        entidade=produto,
        usuario=usuario,
        tenant=produto.tenant,
        descricao=f"Produto {produto.nome} reativado.",
    )
    return produto
