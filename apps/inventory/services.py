"""EstoqueService: único caminho para alterar saldo de estoque.

Garantias (docs/general.md §16–19, 41):
- toda alteração gera MovimentacaoEstoque na mesma transação;
- o saldo é atualizado sob lock pessimista (select_for_update), tornando
  operações concorrentes consistentes;
- a regra de estoque negativo é avaliada por tenant dentro da transação.
"""

from decimal import Decimal

from django.db import transaction

from apps.audit.models import registrar

from .models import Estoque, MovimentacaoEstoque

ENTRADA = "+"
SAIDA = "-"

_DIRECAO_POR_TIPO = {
    MovimentacaoEstoque.Tipo.ENTRADA: ENTRADA,
    MovimentacaoEstoque.Tipo.DEVOLUCAO: ENTRADA,
    MovimentacaoEstoque.Tipo.CANCELAMENTO_VENDA: ENTRADA,
    MovimentacaoEstoque.Tipo.AJUSTE_POSITIVO: ENTRADA,
    MovimentacaoEstoque.Tipo.SAIDA: SAIDA,
    MovimentacaoEstoque.Tipo.VENDA: SAIDA,
    MovimentacaoEstoque.Tipo.AJUSTE_NEGATIVO: SAIDA,
}


class EstoqueError(Exception):
    """Erro de domínio do módulo de estoque."""


def _quantidade_valida(quantidade) -> Decimal:
    quantidade = Decimal(quantidade)
    if quantidade <= 0:
        raise EstoqueError("Quantidade deve ser maior que zero.")
    return quantidade


def _lock_estoque(produto) -> Estoque:
    """Obtém (criando se necessário) o estoque do produto sob lock."""
    estoque, _ = Estoque.objects.get_or_create(
        tenant=produto.tenant, produto=produto
    )
    return Estoque.objects.select_for_update().get(pk=estoque.pk)


@transaction.atomic
def _aplicar_movimentacao(
    produto,
    *,
    tipo,
    quantidade,
    usuario=None,
    motivo="",
    referencia="",
    fornecedor=None,
    custo_unitario=None,
    direcao=None,
):
    """Aplica uma movimentação ao saldo com lock e histórico.

    ``direcao`` permite explicitar o sentido para tipos neutros
    (ex.: INVENTARIO); por padrão é derivada do tipo.
    """
    tenant = produto.tenant
    quantidade = _quantidade_valida(quantidade)
    if direcao is None:
        direcao = _DIRECAO_POR_TIPO[tipo]

    estoque = _lock_estoque(produto)
    saldo_anterior = estoque.quantidade
    saldo_posterior = (
        saldo_anterior + quantidade
        if direcao == ENTRADA
        else saldo_anterior - quantidade
    )
    if saldo_posterior < 0 and not tenant.permitir_estoque_negativo:
        raise EstoqueError(
            f"Saldo insuficiente para {produto.nome}: "
            f"disponível {saldo_anterior}, solicitado {quantidade}."
        )

    estoque.quantidade = saldo_posterior
    estoque.save(update_fields=["quantidade", "data_atualizacao"])

    movimentacao = MovimentacaoEstoque.objects.create(
        tenant=tenant,
        produto=produto,
        tipo=tipo,
        quantidade=quantidade,
        saldo_anterior=saldo_anterior,
        saldo_posterior=saldo_posterior,
        custo_unitario=custo_unitario,
        fornecedor=fornecedor,
        motivo=motivo,
        referencia=referencia,
        usuario=usuario,
    )
    registrar(
        "ESTOQUE_MOVIMENTADO",
        entidade=movimentacao,
        usuario=usuario,
        tenant=tenant,
        descricao=(
            f"{movimentacao.get_tipo_display()} de {quantidade} em "
            f"{produto.nome}: {saldo_anterior} → {saldo_posterior}."
        ),
    )
    return movimentacao


def adicionar_estoque(
    produto,
    quantidade,
    *,
    usuario=None,
    motivo="",
    referencia="",
    fornecedor=None,
    custo_unitario=None,
):
    """Entrada de mercadoria."""
    if fornecedor is not None and fornecedor.tenant_id != produto.tenant_id:
        raise EstoqueError("Fornecedor não pertence ao tenant do produto.")
    return _aplicar_movimentacao(
        produto,
        tipo=MovimentacaoEstoque.Tipo.ENTRADA,
        quantidade=quantidade,
        usuario=usuario,
        motivo=motivo,
        referencia=referencia,
        fornecedor=fornecedor,
        custo_unitario=custo_unitario,
    )


def remover_estoque(produto, quantidade, *, usuario=None, motivo="", referencia=""):
    """Saída manual de mercadoria (perda, consumo interno etc.)."""
    return _aplicar_movimentacao(
        produto,
        tipo=MovimentacaoEstoque.Tipo.SAIDA,
        quantidade=quantidade,
        usuario=usuario,
        motivo=motivo,
        referencia=referencia,
    )


def ajustar_estoque(
    produto,
    *,
    novo_saldo,
    usuario=None,
    motivo="",
    referencia="",
    tipo_inventario=False,
):
    """Ajusta o saldo para um valor absoluto gerando movimentação.

    A direção é derivada do sinal da diferença. Com ``tipo_inventario``
    a movimentação é registrada como INVENTARIO (usado na finalização).
    """
    novo_saldo = Decimal(novo_saldo)
    with transaction.atomic():
        estoque = _lock_estoque(produto)
        saldo_atual = estoque.quantidade
        diferenca = novo_saldo - saldo_atual
        if diferenca == 0:
            return None
        tipo = (
            MovimentacaoEstoque.Tipo.INVENTARIO
            if tipo_inventario
            else (
                MovimentacaoEstoque.Tipo.AJUSTE_POSITIVO
                if diferenca > 0
                else MovimentacaoEstoque.Tipo.AJUSTE_NEGATIVO
            )
        )
        return _aplicar_movimentacao(
            produto,
            tipo=tipo,
            quantidade=abs(diferenca),
            usuario=usuario,
            motivo=motivo or "Ajuste de estoque.",
            referencia=referencia,
            direcao=ENTRADA if diferenca > 0 else SAIDA,
        )


def registrar_venda(produto, quantidade, *, usuario=None, referencia=""):
    """Baixa de estoque por venda (usado pelo PDV no futuro)."""
    return _aplicar_movimentacao(
        produto,
        tipo=MovimentacaoEstoque.Tipo.VENDA,
        quantidade=quantidade,
        usuario=usuario,
        motivo="Venda.",
        referencia=referencia,
    )


def registrar_devolucao(produto, quantidade, *, usuario=None, referencia=""):
    """Devolução de venda devolve itens ao estoque."""
    return _aplicar_movimentacao(
        produto,
        tipo=MovimentacaoEstoque.Tipo.DEVOLUCAO,
        quantidade=quantidade,
        usuario=usuario,
        motivo="Devolução de venda.",
        referencia=referencia,
    )


def obter_ou_criar_estoque(produto) -> Estoque:
    estoque, _ = Estoque.objects.get_or_create(
        tenant=produto.tenant, produto=produto
    )
    return estoque
