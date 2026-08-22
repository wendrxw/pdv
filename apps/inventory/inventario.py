"""InventarioService: ciclo de vida do inventário físico.

Fluxo de status (docs/general.md §25):
    ABERTO → EM_CONTAGEM → EM_REVISAO → FINALIZADO
    ABERTO/EM_CONTAGEM/EM_REVISAO → CANCELADO

A finalização é transacional: para cada item contado, o saldo é ajustado
para a quantidade física via EstoqueService (movimentação INVENTARIO).
Itens sem contagem são ignorados. Após FINALIZADO/CANCELADO nenhuma
alteração é permitida.
"""

from django.db import transaction
from django.utils import timezone

from apps.audit.models import registrar
from apps.products.models import Produto

from .models import Estoque, Inventario, InventarioItem
from .services import ajustar_estoque


class InventarioError(Exception):
    """Erro de domínio do módulo de inventário."""


_TRANSICOES = {
    Inventario.Status.ABERTO: {
        Inventario.Status.EM_CONTAGEM,
        Inventario.Status.CANCELADO,
    },
    Inventario.Status.EM_CONTAGEM: {
        Inventario.Status.EM_REVISAO,
        Inventario.Status.CANCELADO,
    },
    Inventario.Status.EM_REVISAO: {
        Inventario.Status.FINALIZADO,
        Inventario.Status.CANCELADO,
    },
}


def _mudar_status(inventario, novo_status):
    atual = inventario.status
    if novo_status == atual:
        return inventario
    if novo_status not in _TRANSICOES.get(atual, set()):
        raise InventarioError(
            f"Transição inválida: {atual} → {novo_status}."
        )
    inventario.status = novo_status
    inventario.save(update_fields=["status"])
    return inventario


def _garantir_editavel(inventario):
    if inventario.status in (
        Inventario.Status.FINALIZADO,
        Inventario.Status.CANCELADO,
    ):
        raise InventarioError(
            "Inventário finalizado ou cancelado não pode ser alterado."
        )


@transaction.atomic
def iniciar_inventario(*, tenant, descricao, produtos=None, usuario=None):
    """Cria o inventário e congela o saldo de referência por produto."""
    inventario = Inventario(
        tenant=tenant, descricao=descricao, usuario_criacao=usuario
    )
    inventario.full_clean()
    inventario.save()

    if produtos is None:
        produtos = Produto.objects.for_tenant(tenant).filter(ativo=True)
    for produto in produtos:
        if produto.tenant_id != tenant.id:
            raise InventarioError("Produto não pertence ao tenant.")
        estoque = Estoque.objects.filter(
            tenant=tenant, produto=produto
        ).first()
        saldo = estoque.quantidade if estoque else 0
        InventarioItem.objects.create(
            inventario=inventario,
            produto=produto,
            quantidade_sistema=saldo,
        )
    registrar(
        "INVENTARIO_INICIADO",
        entidade=inventario,
        usuario=usuario,
        tenant=tenant,
        descricao=f"Inventário {inventario.descricao} iniciado com "
        f"{inventario.itens.count()} item(ns).",
    )
    return inventario


@transaction.atomic
def iniciar_contagem(inventario, *, usuario=None):
    _garantir_editavel(inventario)
    return _mudar_status(inventario, Inventario.Status.EM_CONTAGEM)


@transaction.atomic
def registrar_contagem(inventario, contagens, *, usuario=None):
    """Registra quantidades físicas.

    ``contagens``: dict {item_uuid: quantidade}. Somente em EM_CONTAGEM.
    """
    _garantir_editavel(inventario)
    if inventario.status != Inventario.Status.EM_CONTAGEM:
        raise InventarioError(
            "Contagens só podem ser registradas com status EM_CONTAGEM."
        )
    itens = {
        str(item.uuid): item
        for item in inventario.itens.select_related("produto")
    }
    for item_uuid, quantidade in contagens.items():
        item = itens.get(item_uuid)
        if item is None:
            raise InventarioError(f"Item {item_uuid} não pertence ao inventário.")
        item.quantidade_contada = quantidade
        item.save(update_fields=["quantidade_contada"])
    registrar(
        "INVENTARIO_CONTAGEM_REGISTRADA",
        entidade=inventario,
        usuario=usuario,
        tenant=inventario.tenant,
        dados={"itens": len(contagens)},
    )
    return inventario


@transaction.atomic
def enviar_para_revisao(inventario, *, usuario=None):
    _garantir_editavel(inventario)
    return _mudar_status(inventario, Inventario.Status.EM_REVISAO)


@transaction.atomic
def cancelar(inventario, *, usuario=None, motivo=""):
    """Cancela sem gerar ajustes; saldos permanecem intactos."""
    _garantir_editavel(inventario)
    _mudar_status(inventario, Inventario.Status.CANCELADO)
    registrar(
        "INVENTARIO_CANCELADO",
        entidade=inventario,
        usuario=usuario,
        tenant=inventario.tenant,
        descricao=motivo or "Inventário cancelado.",
    )
    return inventario


@transaction.atomic
def finalizar(inventario, *, usuario=None):
    """Aplica os ajustes de saldo dos itens contados.

    Para cada item com contagem registrada, gera movimentação INVENTARIO
    levando o saldo à quantidade física. Itens sem contagem são ignorados.
    """
    if inventario.status != Inventario.Status.EM_REVISAO:
        raise InventarioError(
            "Somente inventários EM_REVISAO podem ser finalizados."
        )
    itens = list(
        inventario.itens.select_related("produto").filter(
            quantidade_contada__isnull=False
        )
    )
    for item in itens:
        ajustar_estoque(
            item.produto,
            novo_saldo=item.quantidade_contada,
            usuario=usuario,
            motivo=f"Inventário: {inventario.descricao}",
            referencia=f"inventario:{inventario.uuid}",
            tipo_inventario=True,
        )
    inventario.status = Inventario.Status.FINALIZADO
    inventario.usuario_finalizacao = usuario
    inventario.data_finalizacao = timezone.now()
    inventario.save(
        update_fields=[
            "status",
            "usuario_finalizacao",
            "data_finalizacao",
        ]
    )
    divergentes = sum(1 for item in itens if item.tem_divergencia)
    registrar(
        "INVENTARIO_FINALIZADO",
        entidade=inventario,
        usuario=usuario,
        tenant=inventario.tenant,
        descricao=(
            f"Inventário finalizado: {len(itens)} contado(s), "
            f"{divergentes} divergente(s)."
        ),
    )
    return inventario
