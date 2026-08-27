"""Serviços de domínio do PDV: caixa e vendas.

Regras (tasks/TSK_00007.md, docs/context-pdv.md §15–16):
- venda só existe com caixa ABERTO do operador/tenant;
- o PDV não altera estoque: o caixa apenas registra produtos e contabiliza
  vendas (o controle de estoque é feito à parte, no módulo de estoque);
- preço unitário é congelado do Produto.preco_venda no momento;
- backend é autoridade: frontend envia produto+quantidade, nunca totais;
- finalização transacional exige pagamentos somando exatamente o total;
- pagamentos à vista geram MovimentacaoFinanceira ENTRADA na conta do
  caixa; formas marcadas com gera_conta_receber geram ContaReceber;
- cancelamento nunca apaga registros e estorna o financeiro da venda;
- fechamento calcula o esperado a partir das movimentações referenciadas
  ao caixa (abertura + suprimentos/sangrias + entradas de vendas).

Decisões documentadas:
- saldo inicial do caixa é lançado como ENTRADA origem ABERTURA_CAIXA
  referenciando o caixa, tornando o esperado auditável pelo financeiro;
- pagamento fiado gera ContaReceber com uma parcela (estrutura pronta
  para parcelamento futuro por forma de pagamento);
- o PDV não baixa estoque: vender com saldo zero é permitido.
"""

from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from apps.audit.models import registrar
from apps.financial.models import (
    ContaFinanceira,
    ContaReceber,
    MovimentacaoFinanceira,
)
from apps.financial.services import (
    FinancialError,
    _aplicar_movimentacao,
    cancelar_conta_receber,
    criar_conta_receber,
    obter_ou_criar_conta_principal,
    obter_ou_criar_formas_padrao_pdv,
)

from .models import Caixa, ItemVenda, MovimentacaoCaixa, PagamentoVenda, Venda

ZERO = Decimal("0.00")


class SalesError(Exception):
    """Violação de regra de negócio do PDV."""


# ---------------------------------------------------------------------------
# Caixa
# ---------------------------------------------------------------------------


def _movimentos_do_caixa(caixa):
    """Movimentações financeiras causadas por este caixa.

    Referências usadas: uuid do caixa (abertura), uuid das
    MovimentacaoCaixa (suprimento/sangria) e uuid das vendas finalizadas.
    """
    refs = [caixa.uuid]
    refs += list(caixa.movimentacoes.values_list("uuid", flat=True))
    refs += list(
        caixa.vendas.filter(status=Venda.Status.FINALIZADA).values_list(
            "uuid", flat=True
        )
    )
    return MovimentacaoFinanceira.objects.filter(referencia_uuid__in=refs)


def saldo_esperado_caixa(caixa) -> Decimal:
    """Esperado = abertura + suprimentos + entradas − sangrias."""
    total = ZERO
    for mov in _movimentos_do_caixa(caixa):
        if mov.tipo in (
            MovimentacaoFinanceira.Tipo.ENTRADA,
            MovimentacaoFinanceira.Tipo.ESTORNO_SAIDA,
        ):
            total += mov.valor
        else:
            total -= mov.valor
    return total


def abrir_caixa(tenant, *, operador, conta_financeira=None, saldo_inicial=ZERO):
    """Abre um caixa para o operador. Multi-caixa permitido; apenas um
    ABERTO por operador. Lança a abertura no financeiro quando há troco
    inicial.

    Sem conta informada, usa automaticamente a conta principal do tenant
    (criando-a se necessário) e garante as formas de pagamento padrão do
    PDV, deixando o caixa pronto para vender.
    """
    if conta_financeira is None:
        conta_financeira = obter_ou_criar_conta_principal(tenant)
        obter_ou_criar_formas_padrao_pdv(tenant)
    if conta_financeira.tenant_id != tenant.pk:
        raise SalesError("Conta financeira pertence a outro tenant.")
    if saldo_inicial < ZERO:
        raise SalesError("Saldo inicial não pode ser negativo.")
    if Caixa.objects.for_tenant(tenant).filter(
        operador=operador, status=Caixa.Status.ABERTO
    ).exists():
        raise SalesError("Operador já possui um caixa aberto.")
    with transaction.atomic():
        caixa = Caixa.objects.create(
            tenant=tenant,
            operador=operador,
            conta_financeira=conta_financeira,
            saldo_inicial=saldo_inicial,
        )
        if saldo_inicial > ZERO:
            _aplicar_movimento_caixa(
                caixa,
                tipo=MovimentacaoFinanceira.Tipo.ENTRADA,
                origem=MovimentacaoFinanceira.Origem.ABERTURA_CAIXA,
                valor=saldo_inicial,
                referencia_uuid=caixa.uuid,
                descricao=f"Abertura de caixa {caixa.uuid}",
                usuario=operador,
            )
    registrar(
        "abriu caixa",
        entidade=caixa,
        usuario=operador,
        tenant=tenant,
        descricao=f"Caixa aberto com saldo inicial R$ {saldo_inicial}.",
    )
    return caixa


def _aplicar_movimento_caixa(
    caixa,
    *,
    tipo,
    origem,
    valor,
    referencia_uuid=None,
    descricao="",
    usuario=None,
):
    """Aplica movimentação financeira na conta do caixa sob lock."""
    if valor <= ZERO:
        raise SalesError("Valor deve ser positivo.")
    conta = ContaFinanceira.objects.select_for_update().get(
        pk=caixa.conta_financeira_id
    )
    direcao = "+" if tipo in (
        MovimentacaoFinanceira.Tipo.ENTRADA,
        MovimentacaoFinanceira.Tipo.ESTORNO_SAIDA,
    ) else "-"
    novo_saldo = (
        conta.saldo_atual + valor if direcao == "+" else conta.saldo_atual - valor
    )
    if (
        direcao == "-"
        and novo_saldo < ZERO
        and not conta.permitir_saldo_negativo
    ):
        raise SalesError(
            f"Saldo insuficiente na conta {conta.nome} "
            f"(saldo {conta.saldo_atual}, tentativa de {valor})."
        )
    mov = MovimentacaoFinanceira.objects.create(
        tenant=caixa.tenant,
        conta_financeira=conta,
        tipo=tipo,
        valor=valor,
        data=timezone.localdate(),
        origem=origem,
        referencia_uuid=referencia_uuid,
        descricao=descricao,
        usuario=usuario,
    )
    conta.saldo_atual = novo_saldo
    conta.save(update_fields=["saldo_atual"])
    return mov


def suprimento(caixa, *, valor, motivo="", usuario=None):
    """Entrada de dinheiro no caixa durante o turno."""
    with transaction.atomic():
        caixa = Caixa.objects.select_for_update().get(pk=caixa.pk)
        if caixa.status != Caixa.Status.ABERTO:
            raise SalesError("Caixa não está aberto.")
        mov_caixa = MovimentacaoCaixa.objects.create(
            tenant=caixa.tenant,
            caixa=caixa,
            tipo=MovimentacaoCaixa.Tipo.SUPRIMENTO,
            valor=Decimal(valor),
            motivo=motivo,
            usuario=usuario,
        )
        _aplicar_movimento_caixa(
            caixa,
            tipo=MovimentacaoFinanceira.Tipo.ENTRADA,
            origem=MovimentacaoFinanceira.Origem.SUPRIMENTO,
            valor=mov_caixa.valor,
            referencia_uuid=mov_caixa.uuid,
            descricao=f"Suprimento: {motivo or 'sem motivo'}",
            usuario=usuario,
        )
    return mov_caixa


def sangria(caixa, *, valor, motivo="", usuario=None):
    """Retirada de dinheiro do caixa durante o turno."""
    with transaction.atomic():
        caixa = Caixa.objects.select_for_update().get(pk=caixa.pk)
        if caixa.status != Caixa.Status.ABERTO:
            raise SalesError("Caixa não está aberto.")
        mov_caixa = MovimentacaoCaixa.objects.create(
            tenant=caixa.tenant,
            caixa=caixa,
            tipo=MovimentacaoCaixa.Tipo.SANGRIA,
            valor=Decimal(valor),
            motivo=motivo,
            usuario=usuario,
        )
        _aplicar_movimento_caixa(
            caixa,
            tipo=MovimentacaoFinanceira.Tipo.SAIDA,
            origem=MovimentacaoFinanceira.Origem.SANGRIA,
            valor=mov_caixa.valor,
            referencia_uuid=mov_caixa.uuid,
            descricao=f"Sangria: {motivo or 'sem motivo'}",
            usuario=usuario,
        )
    return mov_caixa


def fechar_caixa(caixa, *, saldo_informado, observacao="", usuario=None):
    """Fecha o caixa calculando o esperado das movimentações."""
    if saldo_informado < ZERO:
        raise SalesError("Saldo informado não pode ser negativo.")
    with transaction.atomic():
        caixa = Caixa.objects.select_for_update().get(pk=caixa.pk)
        if caixa.status != Caixa.Status.ABERTO:
            raise SalesError("Caixa não está aberto.")
        if caixa.vendas.filter(status=Venda.Status.ABERTA).exists():
            raise SalesError(
                "Existem vendas abertas neste caixa; finalize ou cancele."
            )
        caixa.saldo_final_esperado = saldo_esperado_caixa(caixa)
        caixa.saldo_final_informado = Decimal(saldo_informado)
        caixa.observacao_fechamento = observacao
        caixa.status = Caixa.Status.FECHADO
        caixa.data_fechamento = timezone.now()
        caixa.save()
    registrar(
        "fechou caixa",
        entidade=caixa,
        usuario=usuario,
        tenant=caixa.tenant,
        descricao=(
            f"Esperado R$ {caixa.saldo_final_esperado}, "
            f"informado R$ {caixa.saldo_final_informado}, "
            f"diferença R$ {caixa.diferenca}."
        ),
    )
    return caixa


# ---------------------------------------------------------------------------
# Vendas
# ---------------------------------------------------------------------------


def _venda_aberta(venda):
    if venda.status != Venda.Status.ABERTA:
        raise SalesError(f"Venda {venda.numero} não está aberta.")


@transaction.atomic
def abrir_venda(caixa, *, cliente_nome="", observacao=""):
    """Abre venda no caixa com número sequencial por tenant."""
    caixa = Caixa.objects.select_for_update().get(pk=caixa.pk)
    if caixa.status != Caixa.Status.ABERTO:
        raise SalesError("Só é possível vender com caixa aberto.")
    ultima = (
        Venda.objects.for_tenant(caixa.tenant)
        .select_for_update()
        .order_by("-numero")
        .first()
    )
    numero = (ultima.numero + 1) if ultima else 1
    venda = Venda.objects.create(
        tenant=caixa.tenant,
        numero=numero,
        caixa=caixa,
        operador=caixa.operador,
        cliente_nome=cliente_nome.strip(),
        observacao=observacao,
    )
    return venda


def _recalcular_totais(venda):
    agregado = venda.itens.aggregate(total=models_sum("subtotal"))
    subtotal = agregado["total"] or ZERO
    venda.subtotal = subtotal
    if venda.desconto > subtotal:
        venda.desconto = subtotal
    venda.total = subtotal - venda.desconto
    venda.save(update_fields=["subtotal", "desconto", "total"])
    return venda


def models_sum(campo):
    from django.db.models import Sum

    return Sum(campo)


def adicionar_item(venda, produto, quantidade, *, usuario=None):
    """Adiciona produto à venda congelando o preço.

    O PDV não altera estoque. Se o produto já está no carrinho, as
    quantidades são somadas (merge).
    """
    if produto.tenant_id != venda.tenant_id:
        raise SalesError("Produto pertence a outro tenant.")
    if not produto.ativo:
        raise SalesError(f"Produto {produto.nome} está inativo.")
    quantidade = Decimal(quantidade)
    if quantidade <= 0:
        raise SalesError("Quantidade deve ser maior que zero.")
    try:
        item = ItemVenda.objects.select_for_update().get(
            venda=venda, produto=produto
        )
    except ItemVenda.DoesNotExist:
        item = None
    with transaction.atomic():
        venda = Venda.objects.select_for_update().get(pk=venda.pk)
        _venda_aberta(venda)
        if item is None:
            item = ItemVenda.objects.create(
                tenant=venda.tenant,
                venda=venda,
                produto=produto,
                quantidade=quantidade,
                preco_unitario=produto.preco_venda,
                subtotal=(produto.preco_venda * quantidade).quantize(
                    Decimal("0.01")
                ),
            )
        else:
            # Merge: soma a quantidade informada à já existente.
            item.quantidade += quantidade
            item.subtotal = (item.preco_unitario * item.quantidade).quantize(
                Decimal("0.01")
            )
            item.save(update_fields=["quantidade", "subtotal"])
        _recalcular_totais(venda)
    return item


def remover_item(venda, item, *, usuario=None):
    """Remove item do carrinho."""
    if item.venda_id != venda.pk:
        raise SalesError("Item não pertence à venda informada.")
    with transaction.atomic():
        venda = Venda.objects.select_for_update().get(pk=venda.pk)
        _venda_aberta(venda)
        item = ItemVenda.objects.select_for_update().get(pk=item.pk)
        item.delete()
        _recalcular_totais(venda)
    return venda


def alterar_quantidade_item(venda, item, quantidade, *, usuario=None):
    """Altera a quantidade de um item do carrinho.

    A quantidade deve ser maior que zero e o subtotal é recalculado a
    partir do preço congelado no item. Nunca confiar no total enviado
    pelo frontend.
    """
    if item.venda_id != venda.pk:
        raise SalesError("Item não pertence à venda informada.")
    quantidade = Decimal(quantidade)
    if quantidade <= 0:
        raise SalesError("Quantidade deve ser maior que zero.")
    with transaction.atomic():
        venda = Venda.objects.select_for_update().get(pk=venda.pk)
        _venda_aberta(venda)
        item = ItemVenda.objects.select_for_update().get(pk=item.pk)
        item.quantidade = quantidade
        item.subtotal = (item.preco_unitario * quantidade).quantize(
            Decimal("0.01")
        )
        item.save(update_fields=["quantidade", "subtotal"])
        _recalcular_totais(venda)
    return item


def associar_cliente(venda, cliente, *, usuario=None):
    """Associa um cliente cadastrado à venda e congela o nome."""
    if cliente is None:
        raise SalesError("Cliente inválido.")
    if cliente.tenant_id != venda.tenant_id:
        raise SalesError("Cliente pertence a outro tenant.")
    with transaction.atomic():
        venda = Venda.objects.select_for_update().get(pk=venda.pk)
        _venda_aberta(venda)
        venda.cliente = cliente
        venda.cliente_nome = cliente.nome
        venda.save(update_fields=["cliente", "cliente_nome"])
    return venda


def definir_cliente_nome(venda, nome, *, usuario=None):
    """Define apenas o nome do cliente (cadastro rápido, sem vínculo)."""
    nome = (nome or "").strip()[:200]
    with transaction.atomic():
        venda = Venda.objects.select_for_update().get(pk=venda.pk)
        _venda_aberta(venda)
        venda.cliente = None
        venda.cliente_nome = nome
        venda.save(update_fields=["cliente", "cliente_nome"])
    return venda


def aplicar_desconto(venda, desconto, *, usuario=None):
    """Desconto validado no backend: 0 ≤ desconto ≤ subtotal."""
    desconto = Decimal(desconto)
    if desconto < ZERO:
        raise SalesError("Desconto não pode ser negativo.")
    with transaction.atomic():
        venda = Venda.objects.select_for_update().get(pk=venda.pk)
        _venda_aberta(venda)
        if desconto > venda.subtotal:
            raise SalesError("Desconto maior que o subtotal da venda.")
        venda.desconto = desconto
        venda.total = venda.subtotal - venda.desconto
        venda.save(update_fields=["desconto", "total"])
    return venda


def adicionar_pagamento(venda, forma_pagamento, valor):
    """Registra intenção de pagamento; rejeita excedente ao total."""
    if forma_pagamento.tenant_id != venda.tenant_id:
        raise SalesError("Forma de pagamento pertence a outro tenant.")
    valor = Decimal(valor)
    if valor <= ZERO:
        raise SalesError("Valor do pagamento deve ser positivo.")
    pago = _total_pago(venda)
    if pago + valor > venda.total:
        excedente = pago + valor - venda.total
        raise SalesError(
            f"Pagamento excede o total em R$ {excedente}."
        )
    return PagamentoVenda.objects.create(
        tenant=venda.tenant,
        venda=venda,
        forma_pagamento=forma_pagamento,
        valor=valor,
        valor_bruto=valor,
        taxa=(valor * forma_pagamento.taxa_percentual / 100).quantize(
            Decimal("0.01")
        ),
        valor_liquido=valor,
    )


def _total_pago(venda) -> Decimal:
    return (
        venda.pagamentos.aggregate(total=models_sum("valor"))["total"]
        or ZERO
    )


def finalizar_venda(venda, *, usuario=None, forma_pagamento=None):
    """Finaliza a venda transacionalmente.

    Fluxo padrão do PDV: com ``forma_pagamento`` informada, registra o
    pagamento do valor restante com essa forma e finaliza. Sem forma,
    exige pagamentos somando exatamente o total.

    À vista (Dinheiro) gera entrada na conta do caixa; cartão/PIX geram
    ContaReceber (pagamento via maquininha, sem conexão com o sistema).
    """
    with transaction.atomic():
        venda = Venda.objects.select_for_update().get(pk=venda.pk)
        _venda_aberta(venda)
        if not venda.itens.exists():
            raise SalesError("Venda sem itens não pode ser finalizada.")
        if forma_pagamento is not None:
            if forma_pagamento.tenant_id != venda.tenant_id:
                raise SalesError("Forma de pagamento pertence a outro tenant.")
            pago = _total_pago(venda)
            if pago < venda.total:
                adicionar_pagamento(
                    venda, forma_pagamento, venda.total - pago
                )
        pago = _total_pago(venda)
        if pago == ZERO:
            raise SalesError("Venda sem pagamentos.")
        if pago != venda.total:
            faltante = venda.total - pago
            if faltante > ZERO:
                raise SalesError(
                    f"Falta R$ {faltante} para completar o total."
                )
            raise SalesError("Pagamentos excedem o total da venda.")
        caixa = Caixa.objects.select_for_update().get(pk=venda.caixa_id)
        for pagamento in venda.pagamentos.select_related("forma_pagamento"):
            forma = pagamento.forma_pagamento
            if forma.gera_conta_receber:
                criar_conta_receber(
                    venda.tenant,
                    descricao=(
                        f"Venda {venda.numero} — {forma.nome}"
                    ),
                    valor_total=pagamento.valor,
                    parcelas=1,
                    cliente_nome=venda.cliente_nome,
                    origem=ContaReceber.Origem.VENDA,
                    referencia_uuid=venda.uuid,
                    observacao=f"Pagamento {pagamento.uuid}",
                    usuario=usuario,
                )
            else:
                _aplicar_movimento_caixa(
                    caixa,
                    tipo=MovimentacaoFinanceira.Tipo.ENTRADA,
                    origem=MovimentacaoFinanceira.Origem.VENDA,
                    valor=pagamento.valor,
                    referencia_uuid=venda.uuid,
                    descricao=(
                        f"Venda {venda.numero} — {forma.nome}"
                    ),
                    usuario=usuario,
                )
        venda.status = Venda.Status.FINALIZADA
        venda.data_finalizacao = timezone.now()
        venda.save(update_fields=["status", "data_finalizacao"])
    registrar(
        "finalizou venda",
        entidade=venda,
        usuario=usuario,
        tenant=venda.tenant,
        descricao=(
            f"Venda {venda.numero} finalizada: "
            f"subtotal R$ {venda.subtotal}, desconto R$ {venda.desconto}, "
            f"total R$ {venda.total}."
        ),
        dados={"uuid": str(venda.uuid), "total": str(venda.total)},
    )
    return venda


def cancelar_venda(venda, *, motivo="", usuario=None):
    """Cancela venda estornando o financeiro.

    - ABERTA: pagamentos ainda não afetaram financeiro, nada a estornar.
    - FINALIZADA: estorna cada ENTRADA da venda com ESTORNO_ENTRADA e
      cancela ContaReceber pendente de origem VENDA.
    Registros nunca são apagados. O PDV não altera estoque.
    """
    if venda.status == Venda.Status.CANCELADA:
        raise SalesError("Venda já está cancelada.")
    if not motivo.strip():
        raise SalesError("Cancelamento exige justificativa.")
    with transaction.atomic():
        venda = Venda.objects.select_for_update().get(pk=venda.pk)
        if venda.status == Venda.Status.CANCELADA:
            raise SalesError("Venda já está cancelada.")
        if venda.status == Venda.Status.FINALIZADA:
            _estornar_entradas_da_venda(venda, motivo, usuario)
            _cancelar_recebiveis_da_venda(venda, usuario)
        venda.status = Venda.Status.CANCELADA
        venda.save(update_fields=["status"])
    registrar(
        "cancelou venda",
        entidade=venda,
        usuario=usuario,
        tenant=venda.tenant,
        descricao=f"Venda {venda.numero} cancelada: {motivo.strip()}",
    )
    return venda


def _estornar_entradas_da_venda(venda, motivo, usuario):
    originais = MovimentacaoFinanceira.objects.filter(
        referencia_uuid=venda.uuid,
        tipo=MovimentacaoFinanceira.Tipo.ENTRADA,
    ).select_related("conta_financeira")
    for original in originais:
        if original.estornos.exists():
            continue
        # Estorno referencia a movimentação original e trava a conta dela.
        _aplicar_movimentacao(
            original.conta_financeira,
            tipo=MovimentacaoFinanceira.Tipo.ESTORNO_ENTRADA,
            valor=original.valor,
            data=timezone.localdate(),
            origem=MovimentacaoFinanceira.Origem.VENDA,
            referencia_uuid=venda.uuid,
            descricao=f"Estorno venda {venda.numero}: {motivo.strip()}",
            usuario=usuario,
            estorno_de=original,
        )


def _cancelar_recebiveis_da_venda(venda, usuario):
    recebiveis = ContaReceber.objects.for_tenant(venda.tenant).filter(
        origem=ContaReceber.Origem.VENDA, referencia_uuid=venda.uuid
    )
    for conta in recebiveis:
        try:
            cancelar_conta_receber(conta, usuario=usuario)
        except FinancialError:
            # Com parcelas recebidas o estorno financeiro manual é tratado
            # fora do escopo automático; mantém histórico intacto.
            continue


__all__ = [
    "SalesError",
    "abrir_caixa",
    "abrir_venda",
    "adicionar_item",
    "adicionar_pagamento",
    "alterar_quantidade_item",
    "aplicar_desconto",
    "associar_cliente",
    "cancelar_venda",
    "definir_cliente_nome",
    "fechar_caixa",
    "finalizar_venda",
    "remover_item",
    "saldo_esperado_caixa",
    "sangria",
    "suprimento",
]
