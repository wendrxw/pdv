"""Serviços de domínio do módulo financeiro.

Regras de ouro (docs/general.md §67):
- saldo nunca muda sem MovimentacaoFinanceira correspondente;
- operação que já ocorreu nunca é apagada — cancela-se ou estorna-se;
- toda operação financeira é transacional e trava a conta
  (select_for_update) para concorrência;
- backend é autoridade em cálculos; frontend apenas exibe.
"""

from calendar import monthrange
from decimal import ROUND_HALF_UP, Decimal

from django.db import transaction
from django.utils import timezone

from .models import (
    CategoriaFinanceira,
    ContaFinanceira,
    ContaReceber,
    Entrada,
    FormaPagamento,
    MovimentacaoFinanceira,
    ParcelaReceber,
    Saida,
)

CENTAVO = Decimal("0.01")
ZERO = Decimal("0.00")

_DIRECAO_POR_TIPO = {
    MovimentacaoFinanceira.Tipo.ENTRADA: "+",
    MovimentacaoFinanceira.Tipo.ESTORNO_SAIDA: "+",
    MovimentacaoFinanceira.Tipo.SAIDA: "-",
    MovimentacaoFinanceira.Tipo.ESTORNO_ENTRADA: "-",
}


class FinancialError(Exception):
    """Violação de regra financeira."""


def _lock_conta(conta_id):
    return ContaFinanceira.objects.select_for_update().get(pk=conta_id)


def _aplicar_movimentacao(
    conta,
    *,
    tipo,
    valor,
    data,
    origem,
    referencia_uuid=None,
    descricao="",
    usuario=None,
    estorno_de=None,
):
    """Aplica uma movimentação à conta sob lock, validando saldo.

    Retorna a movimentação criada. Deve ser chamada dentro de transação.
    """
    if valor <= ZERO:
        raise FinancialError("Valor da movimentação deve ser positivo.")
    conta = _lock_conta(conta.pk)
    direcao = _DIRECAO_POR_TIPO[tipo]
    novo_saldo = (
        conta.saldo_atual + valor if direcao == "+" else conta.saldo_atual - valor
    )
    if (
        direcao == "-"
        and novo_saldo < ZERO
        and not conta.permitir_saldo_negativo
    ):
        raise FinancialError(
            f"Saldo insuficiente na conta {conta.nome} "
            f"(saldo {conta.saldo_atual}, tentativa de {valor})."
        )
    movimentacao = MovimentacaoFinanceira.objects.create(
        tenant=conta.tenant,
        conta_financeira=conta,
        tipo=tipo,
        valor=valor,
        data=data,
        origem=origem,
        referencia_uuid=referencia_uuid,
        estorno_de=estorno_de,
        descricao=descricao,
        usuario=usuario,
    )
    conta.saldo_atual = novo_saldo
    conta.save(update_fields=["saldo_atual"])
    return movimentacao


# ---------------------------------------------------------------------------
# Categorias / contas / formas de pagamento
# ---------------------------------------------------------------------------


def criar_categoria(tenant, *, nome, tipo, categoria_pai=None, usuario=None):
    if categoria_pai is not None:
        if categoria_pai.tenant_id != tenant.pk:
            raise FinancialError("Categoria pai pertence a outro tenant.")
        if categoria_pai.categoria_pai_id is not None:
            raise FinancialError("Hierarquia limitada a um nível.")
    categoria = CategoriaFinanceira(
        tenant=tenant,
        nome=nome.strip(),
        tipo=tipo,
        categoria_pai=categoria_pai,
    )
    categoria.full_clean()
    categoria.save()
    return categoria


def criar_conta(tenant, *, nome, tipo, saldo_inicial=ZERO, usuario=None):
    conta = ContaFinanceira(
        tenant=tenant,
        nome=nome.strip(),
        tipo=tipo,
        saldo_inicial=saldo_inicial,
        saldo_atual=saldo_inicial,
    )
    conta.full_clean()
    conta.save()
    return conta


def criar_forma_pagamento(
    tenant, *, nome, codigo, taxa_percentual=ZERO, gera_conta_receber=False
):
    forma = FormaPagamento(
        tenant=tenant,
        nome=nome.strip(),
        codigo=codigo,
        taxa_percentual=taxa_percentual,
        gera_conta_receber=gera_conta_receber,
    )
    forma.full_clean()
    forma.save()
    return forma


def obter_ou_criar_conta_principal(tenant):
    """Conta principal do tenant, usada pelo PDV ao abrir o caixa.

    Procura uma conta CAIXA ativa; se não existir, cria "Caixa Principal".
    """
    conta = (
        ContaFinanceira.objects.for_tenant(tenant)
        .filter(tipo=ContaFinanceira.Tipo.CAIXA, ativo=True)
        .order_by("data_cadastro")
        .first()
    )
    if conta is None:
        conta = criar_conta(
            tenant, nome="Caixa Principal", tipo=ContaFinanceira.Tipo.CAIXA
        )
    return conta


def obter_ou_criar_forma_dinheiro(tenant):
    """Forma de pagamento padrão do PDV (Dinheiro), criada se necessário."""
    forma = (
        FormaPagamento.objects.for_tenant(tenant)
        .filter(codigo=FormaPagamento.Codigo.DINHEIRO, ativo=True)
        .first()
    )
    if forma is None:
        forma = criar_forma_pagamento(
            tenant, nome="Dinheiro", codigo=FormaPagamento.Codigo.DINHEIRO
        )
    return forma


_FORMAS_PADRAO_PDV = (
    {
        "nome": "Dinheiro",
        "codigo": FormaPagamento.Codigo.DINHEIRO,
        "gera_conta_receber": False,
    },
    {
        "nome": "Cartão de crédito",
        "codigo": FormaPagamento.Codigo.CREDITO,
        "gera_conta_receber": True,
    },
    {
        "nome": "Cartão de débito",
        "codigo": FormaPagamento.Codigo.DEBITO,
        "gera_conta_receber": True,
    },
    {
        "nome": "PIX",
        "codigo": FormaPagamento.Codigo.PIX,
        "gera_conta_receber": True,
    },
)


def obter_ou_criar_formas_padrao_pdv(tenant):
    """Garante as formas de pagamento padrão do PDV.

    Dinheiro, cartão de crédito, cartão de débito e PIX. Cartão e PIX são
    recebidos via maquininha (sem conexão com o sistema), portanto geram
    ContaReceber em vez de entrada imediata no caixa.
    """
    formas = []
    for dados in _FORMAS_PADRAO_PDV:
        forma = (
            FormaPagamento.objects.for_tenant(tenant)
            .filter(codigo=dados["codigo"])
            .first()
        )
        if forma is None:
            forma = criar_forma_pagamento(
                tenant,
                nome=dados["nome"],
                codigo=dados["codigo"],
                gera_conta_receber=dados["gera_conta_receber"],
            )
        formas.append(forma)
    return formas


# ---------------------------------------------------------------------------
# Entradas
# ---------------------------------------------------------------------------


def criar_entrada(
    tenant,
    *,
    descricao,
    valor,
    conta_financeira,
    data_competencia,
    categoria=None,
    forma_pagamento=None,
    data_prevista=None,
    status=Entrada.Status.PENDENTE,
    observacao="",
    usuario=None,
):
    _validar_lancamento_tenant(
        tenant,
        conta_financeira=conta_financeira,
        categoria=categoria,
        forma_pagamento=forma_pagamento,
    )
    if valor <= ZERO:
        raise FinancialError("Valor da entrada deve ser positivo.")
    entrada = Entrada(
        tenant=tenant,
        descricao=descricao.strip(),
        valor=valor,
        categoria=categoria,
        conta_financeira=conta_financeira,
        forma_pagamento=forma_pagamento,
        data_competencia=data_competencia,
        data_prevista=data_prevista,
        status=status,
        observacao=observacao,
        usuario_criacao=usuario,
    )
    entrada.full_clean(exclude={"usuario_criacao"})
    entrada.save()
    return entrada


def receber_entrada(entrada, *, conta_financeira=None, data=None, usuario=None):
    """Registra recebimento efetivo: movimentação + saldo, atômico."""
    with transaction.atomic():
        entrada = Entrada.objects.select_for_update().get(pk=entrada.pk)
        if entrada.status == Entrada.Status.RECEBIDA:
            raise FinancialError("Entrada já foi recebida.")
        if entrada.status != Entrada.Status.PENDENTE:
            raise FinancialError(
                f"Somente entradas pendentes podem ser recebidas "
                f"(status atual: {entrada.get_status_display()})."
            )
        conta = conta_financeira or entrada.conta_financeira
        if conta.tenant_id != entrada.tenant_id:
            raise FinancialError("Conta pertence a outro tenant.")
        data = data or timezone.localdate()
        _aplicar_movimentacao(
            conta,
            tipo=MovimentacaoFinanceira.Tipo.ENTRADA,
            valor=entrada.valor,
            data=data,
            origem=MovimentacaoFinanceira.Origem.ENTRADA,
            referencia_uuid=entrada.uuid,
            descricao=f"Recebimento: {entrada.descricao}",
            usuario=usuario,
        )
        entrada.conta_financeira = conta
        entrada.status = Entrada.Status.RECEBIDA
        entrada.data_recebimento = data
        entrada.save()
    return entrada


def cancelar_entrada(entrada, *, usuario=None):
    with transaction.atomic():
        entrada = Entrada.objects.select_for_update().get(pk=entrada.pk)
        if entrada.status == Entrada.Status.CANCELADA:
            raise FinancialError("Entrada já está cancelada.")
        if entrada.status == Entrada.Status.RECEBIDA:
            raise FinancialError(
                "Entrada recebida não pode ser cancelada; utilize estorno."
            )
        entrada.status = Entrada.Status.CANCELADA
        entrada.save()
    return entrada


def estornar_recebimento_entrada(entrada, *, motivo, usuario=None):
    """Estorno auditável: movimentação inversa referenciando a original."""
    if not motivo or not motivo.strip():
        raise FinancialError("Estorno exige justificativa.")
    with transaction.atomic():
        entrada = Entrada.objects.select_for_update().get(pk=entrada.pk)
        if entrada.status != Entrada.Status.RECEBIDA:
            raise FinancialError("Somente entradas recebidas podem ser estornadas.")
        original = (
            MovimentacaoFinanceira.objects.filter(
                referencia_uuid=entrada.uuid,
                tipo=MovimentacaoFinanceira.Tipo.ENTRADA,
            )
            .order_by("-data_criacao")
            .first()
        )
        if original is None:
            raise FinancialError("Movimentação original não encontrada.")
        if original.estornos.exists():
            raise FinancialError("Este recebimento já foi estornado.")
        _aplicar_movimentacao(
            entrada.conta_financeira,
            tipo=MovimentacaoFinanceira.Tipo.ESTORNO_ENTRADA,
            valor=entrada.valor,
            data=timezone.localdate(),
            origem=MovimentacaoFinanceira.Origem.ENTRADA,
            referencia_uuid=entrada.uuid,
            descricao=f"Estorno: {motivo.strip()}",
            usuario=usuario,
            estorno_de=original,
        )
        entrada.status = Entrada.Status.CANCELADA
        entrada.data_recebimento = None
        entrada.save()
    return entrada


# ---------------------------------------------------------------------------
# Saídas
# ---------------------------------------------------------------------------


def criar_saida(
    tenant,
    *,
    descricao,
    valor,
    conta_financeira,
    data_competencia,
    data_vencimento,
    categoria=None,
    data_pagamento=None,
    status=Saida.Status.PENDENTE,
    observacao="",
    usuario=None,
):
    _validar_lancamento_tenant(
        tenant, conta_financeira=conta_financeira, categoria=categoria
    )
    if valor <= ZERO:
        raise FinancialError("Valor da saída deve ser positivo.")
    saida = Saida(
        tenant=tenant,
        descricao=descricao.strip(),
        valor=valor,
        categoria=categoria,
        conta_financeira=conta_financeira,
        data_competencia=data_competencia,
        data_vencimento=data_vencimento,
        data_pagamento=data_pagamento,
        status=status,
        observacao=observacao,
        usuario_criacao=usuario,
    )
    saida.full_clean(exclude={"usuario_criacao"})
    saida.save()
    return saida


def pagar_saida(saida, *, conta_financeira=None, data=None, usuario=None):
    with transaction.atomic():
        saida = Saida.objects.select_for_update().get(pk=saida.pk)
        if saida.status == Saida.Status.PAGA:
            raise FinancialError("Saída já foi paga.")
        if saida.status != Saida.Status.PENDENTE:
            raise FinancialError(
                f"Somente saídas pendentes podem ser pagas "
                f"(status atual: {saida.get_status_display()})."
            )
        conta = conta_financeira or saida.conta_financeira
        if conta.tenant_id != saida.tenant_id:
            raise FinancialError("Conta pertence a outro tenant.")
        data = data or timezone.localdate()
        _aplicar_movimentacao(
            conta,
            tipo=MovimentacaoFinanceira.Tipo.SAIDA,
            valor=saida.valor,
            data=data,
            origem=MovimentacaoFinanceira.Origem.SAIDA,
            referencia_uuid=saida.uuid,
            descricao=f"Pagamento: {saida.descricao}",
            usuario=usuario,
        )
        saida.conta_financeira = conta
        saida.status = Saida.Status.PAGA
        saida.data_pagamento = data
        saida.save()
    return saida


def cancelar_saida(saida, *, usuario=None):
    with transaction.atomic():
        saida = Saida.objects.select_for_update().get(pk=saida.pk)
        if saida.status == Saida.Status.CANCELADA:
            raise FinancialError("Saída já está cancelada.")
        if saida.status == Saida.Status.PAGA:
            raise FinancialError(
                "Saída paga não pode ser cancelada; utilize estorno."
            )
        saida.status = Saida.Status.CANCELADA
        saida.save()
    return saida


def estornar_pagamento_saida(saida, *, motivo, usuario=None):
    if not motivo or not motivo.strip():
        raise FinancialError("Estorno exige justificativa.")
    with transaction.atomic():
        saida = Saida.objects.select_for_update().get(pk=saida.pk)
        if saida.status != Saida.Status.PAGA:
            raise FinancialError("Somente saídas pagas podem ser estornadas.")
        original = (
            MovimentacaoFinanceira.objects.filter(
                referencia_uuid=saida.uuid,
                tipo=MovimentacaoFinanceira.Tipo.SAIDA,
            )
            .order_by("-data_criacao")
            .first()
        )
        if original is None:
            raise FinancialError("Movimentação original não encontrada.")
        if original.estornos.exists():
            raise FinancialError("Este pagamento já foi estornado.")
        _aplicar_movimentacao(
            saida.conta_financeira,
            tipo=MovimentacaoFinanceira.Tipo.ESTORNO_SAIDA,
            valor=saida.valor,
            data=timezone.localdate(),
            origem=MovimentacaoFinanceira.Origem.SAIDA,
            referencia_uuid=saida.uuid,
            descricao=f"Estorno: {motivo.strip()}",
            usuario=usuario,
            estorno_de=original,
        )
        saida.status = Saida.Status.PENDENTE
        saida.data_pagamento = None
        saida.save()
    return saida


# ---------------------------------------------------------------------------
# Contas a receber
# ---------------------------------------------------------------------------


def dividir_em_parcelas(valor_total, quantidade):
    """Divide um valor em parcelas sem perda de centavos.

    As primeiras parcelas recebem o piso; a última absorve o resíduo.
    Ex.: 100.00/3 → [33.33, 33.33, 33.34].
    """
    if quantidade < 1:
        raise FinancialError("Quantidade de parcelas deve ser >= 1.")
    if valor_total <= ZERO:
        raise FinancialError("Valor total deve ser positivo.")
    base = (valor_total / quantidade).quantize(CENTAVO, rounding=ROUND_HALF_UP)
    parcelas = [base] * (quantidade - 1)
    parcelas.append(valor_total - sum(parcelas))
    if any(p <= ZERO for p in parcelas):
        raise FinancialError(
            "Valor muito baixo para a quantidade de parcelas informada."
        )
    return parcelas


def _validar_lancamento_tenant(
    tenant, *, conta_financeira=None, categoria=None, forma_pagamento=None
):
    if conta_financeira is not None and conta_financeira.tenant_id != tenant.pk:
        raise FinancialError("Conta financeira pertence a outro tenant.")
    if categoria is not None and categoria.tenant_id != tenant.pk:
        raise FinancialError("Categoria pertence a outro tenant.")
    if forma_pagamento is not None and forma_pagamento.tenant_id != tenant.pk:
        raise FinancialError("Forma de pagamento pertence a outro tenant.")


def _somar_meses(data, meses):
    """Adiciona meses clampando o dia ao último do mês (31/01+1=28/02)."""
    mes_total = data.month - 1 + meses
    ano = data.year + mes_total // 12
    mes = mes_total % 12 + 1
    dia = min(data.day, monthrange(ano, mes)[1])
    return data.replace(year=ano, month=mes, day=dia)


def criar_conta_receber(
    tenant,
    *,
    descricao,
    valor_total,
    parcelas,
    cliente_nome="",
    data_competencia=None,
    vencimentos=None,
    origem=ContaReceber.Origem.MANUAL,
    referencia_uuid=None,
    observacao="",
    usuario=None,
):
    """Cria conta com N parcelas; vencimentos mensais por padrão."""
    valores = dividir_em_parcelas(valor_total, parcelas)
    competencia = data_competencia or timezone.localdate()
    if vencimentos is None:
        primeiro = timezone.localdate()
        vencimentos = [_somar_meses(primeiro, i) for i in range(parcelas)]
    if len(vencimentos) != parcelas:
        raise FinancialError(
            "Quantidade de vencimentos difere da quantidade de parcelas."
        )
    with transaction.atomic():
        conta = ContaReceber(
            tenant=tenant,
            cliente_nome=cliente_nome.strip(),
            descricao=descricao.strip(),
            valor_total=valor_total,
            data_competencia=competencia,
            origem=origem,
            referencia_uuid=referencia_uuid,
            observacao=observacao,
        )
        conta.full_clean()
        conta.save()
        for numero, (valor, vencimento) in enumerate(
            zip(valores, vencimentos, strict=True), start=1
        ):
            ParcelaReceber.objects.create(
                tenant=tenant,
                conta_receber=conta,
                numero=numero,
                valor=valor,
                data_vencimento=vencimento,
            )
    return conta


def receber_parcela(parcela, *, conta_financeira, data=None, usuario=None):
    with transaction.atomic():
        parcela = ParcelaReceber.objects.select_for_update().get(pk=parcela.pk)
        if parcela.status == ParcelaReceber.Status.RECEBIDA:
            raise FinancialError("Parcela já foi recebida.")
        if parcela.status == ParcelaReceber.Status.CANCELADA:
            raise FinancialError("Parcela cancelada não pode ser recebida.")
        if conta_financeira.tenant_id != parcela.tenant_id:
            raise FinancialError("Conta pertence a outro tenant.")
        data = data or timezone.localdate()
        _aplicar_movimentacao(
            conta_financeira,
            tipo=MovimentacaoFinanceira.Tipo.ENTRADA,
            valor=parcela.valor,
            data=data,
            origem=MovimentacaoFinanceira.Origem.PARCELA,
            referencia_uuid=parcela.uuid,
            descricao=(
                f"Recebimento parcela {parcela.numero}: "
                f"{parcela.conta_receber.descricao}"
            ),
            usuario=usuario,
        )
        parcela.status = ParcelaReceber.Status.RECEBIDA
        parcela.data_recebimento = data
        parcela.conta_financeira = conta_financeira
        parcela.save()

        conta_receber = (
            ContaReceber.objects.select_for_update().get(pk=parcela.conta_receber_id)
        )
        pendentes = conta_receber.parcelas.filter(
            status=ParcelaReceber.Status.PENDENTE
        ).exists()
        if pendentes:
            conta_receber.status = ContaReceber.Status.PARCIAL
        else:
            conta_receber.status = ContaReceber.Status.RECEBIDA
        conta_receber.save()
    return parcela


def cancelar_conta_receber(conta_receber, *, usuario=None):
    with transaction.atomic():
        conta_receber = ContaReceber.objects.select_for_update().get(
            pk=conta_receber.pk
        )
        if conta_receber.status in (
            ContaReceber.Status.CANCELADA,
            ContaReceber.Status.RECEBIDA,
        ):
            raise FinancialError(
                "Conta cancelada ou totalmente recebida não pode ser cancelada."
            )
        if conta_receber.parcelas.filter(
            status=ParcelaReceber.Status.RECEBIDA
        ).exists():
            raise FinancialError(
                "Conta com parcelas recebidas não pode ser cancelada."
            )
        conta_receber.parcelas.filter(
            status=ParcelaReceber.Status.PENDENTE
        ).update(status=ParcelaReceber.Status.CANCELADA)
        conta_receber.status = ContaReceber.Status.CANCELADA
        conta_receber.save()
    return conta_receber


# ---------------------------------------------------------------------------
# Análise financeira
# ---------------------------------------------------------------------------


def resumo_analise(tenant, *, inicio, fim, modo="CAIXA"):
    """Indicadores do período. modo: CAIXA (recebido/pago) ou
    COMPETENCIA (lançamentos pela data de competência)."""
    if inicio > fim:
        raise FinancialError("Data inicial posterior à final.")

    if modo == "CAIXA":
        movs = MovimentacaoFinanceira.objects.for_tenant(tenant).filter(
            data__range=(inicio, fim)
        )
        entradas = _soma(movs, MovimentacaoFinanceira.Tipo.ENTRADA)
        saidas = _soma(movs, MovimentacaoFinanceira.Tipo.SAIDA)
    elif modo == "COMPETENCIA":
        entradas_q = (
            Entrada.objects.for_tenant(tenant)
            .exclude(status__in=[Entrada.Status.CANCELADA])
            .filter(data_competencia__range=(inicio, fim))
            .aggregate(total=models_sum("valor"))
        )
        saidas_q = (
            Saida.objects.for_tenant(tenant)
            .exclude(status__in=[Saida.Status.CANCELADA])
            .filter(data_competencia__range=(inicio, fim))
            .aggregate(total=models_sum("valor"))
        )
        entradas = entradas_q["total"] or ZERO
        saidas = saidas_q["total"] or ZERO
    else:
        raise FinancialError(f"Modo desconhecido: {modo}")

    hoje = timezone.localdate()
    parcelas_abertas = ParcelaReceber.objects.for_tenant(tenant).filter(
        status=ParcelaReceber.Status.PENDENTE
    )
    vencidas = parcelas_abertas.filter(data_vencimento__lt=hoje).aggregate(
        total=models_sum("valor")
    )["total"] or ZERO
    a_vencer = parcelas_abertas.filter(data_vencimento__gte=hoje).aggregate(
        total=models_sum("valor")
    )["total"] or ZERO

    fluxo = _fluxo_por_dia(tenant, inicio, fim, modo)
    categorias_entradas = _por_categoria(tenant, inicio, fim, "ENTRADA", modo)
    categorias_saidas = _por_categoria(tenant, inicio, fim, "SAIDA", modo)
    contas = list(
        ContaFinanceira.objects.for_tenant(tenant)
        .filter(ativo=True)
        .values("nome", "tipo", "saldo_atual")
    )

    return {
        "entradas": entradas,
        "saidas": saidas,
        "resultado": entradas - saidas,
        "vencido": vencidas,
        "a_vencer": a_vencer,
        "fluxo": fluxo,
        "categorias_entradas": categorias_entradas,
        "categorias_saidas": categorias_saidas,
        "contas": contas,
    }


def models_sum(campo):
    from django.db.models import Sum

    return Sum(campo)


def _soma(queryset, tipo):
    return (
        queryset.filter(tipo=tipo).aggregate(total=models_sum("valor"))["total"]
        or ZERO
    )


def _fluxo_por_dia(tenant, inicio, fim, modo):
    """Fluxo de caixa diário no período (modo CAIXA apenas por ora)."""
    dias = {}
    if modo == "CAIXA":
        movs = (
            MovimentacaoFinanceira.objects.for_tenant(tenant)
            .filter(data__range=(inicio, fim))
            .values("data", "tipo")
            .annotate(total=models_sum("valor"))
        )
        for linha in movs:
            entrada = linha["tipo"] in (
                MovimentacaoFinanceira.Tipo.ENTRADA,
                MovimentacaoFinanceira.Tipo.ESTORNO_SAIDA,
            )
            dia = dias.setdefault(
                linha["data"], {"entradas": ZERO, "saidas": ZERO}
            )
            if entrada:
                dia["entradas"] += linha["total"]
            else:
                dia["saidas"] += linha["total"]
    else:
        for linha in (
            Entrada.objects.for_tenant(tenant)
            .exclude(status=Entrada.Status.CANCELADA)
            .filter(data_competencia__range=(inicio, fim))
            .values("data_competencia")
            .annotate(total=models_sum("valor"))
        ):
            dia = dias.setdefault(
                linha["data_competencia"], {"entradas": ZERO, "saidas": ZERO}
            )
            dia["entradas"] += linha["total"]
        for linha in (
            Saida.objects.for_tenant(tenant)
            .exclude(status=Saida.Status.CANCELADA)
            .filter(data_competencia__range=(inicio, fim))
            .values("data_competencia")
            .annotate(total=models_sum("valor"))
        ):
            dia = dias.setdefault(
                linha["data_competencia"], {"entradas": ZERO, "saidas": ZERO}
            )
            dia["saidas"] += linha["total"]

    fluxo = []
    acumulado = ZERO
    for dia in sorted(dias):
        resultado = dias[dia]["entradas"] - dias[dia]["saidas"]
        acumulado += resultado
        fluxo.append(
            {
                "data": dia,
                "entradas": dias[dia]["entradas"],
                "saidas": dias[dia]["saidas"],
                "resultado": resultado,
                "acumulado": acumulado,
            }
        )
    return fluxo


def _por_categoria(tenant, inicio, fim, tipo_lancamento, modo):
    model = Entrada if tipo_lancamento == "ENTRADA" else Saida
    status_cancelado = (
        Entrada.Status.CANCELADA
        if tipo_lancamento == "ENTRADA"
        else Saida.Status.CANCELADA
    )
    qs = (
        model.objects.for_tenant(tenant)
        .exclude(status=status_cancelado)
        .select_related("categoria")
    )
    filtro_data = {"data_competencia__range": (inicio, fim)}
    if modo == "CAIXA":
        tipos_ref = (
            [MovimentacaoFinanceira.Tipo.ENTRADA]
            if tipo_lancamento == "ENTRADA"
            else [MovimentacaoFinanceira.Tipo.SAIDA]
        )
        refs = (
            MovimentacaoFinanceira.objects.for_tenant(tenant)
            .filter(data__range=(inicio, fim), tipo__in=tipos_ref)
            .values_list("referencia_uuid", flat=True)
        )
        qs = qs.filter(uuid__in=list(refs))
    linhas = (
        qs.filter(**filtro_data)
        .values("categoria__nome")
        .annotate(total=models_sum("valor"))
        .order_by("-total")
    )
    return [
        {
            "categoria": linha["categoria__nome"] or "Sem categoria",
            "total": linha["total"],
        }
        for linha in linhas
    ]
