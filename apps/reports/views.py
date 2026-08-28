"""Relatórios operacionais do PDV.

Tudo é somente leitura e isolado pelo tenant do usuário autenticado.
Agregações SQL são usadas para suportar grandes volumes sem carregar
vendas individualmente.
"""

from datetime import timedelta
from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Count, Sum
from django.shortcuts import redirect, render
from django.utils import timezone

from apps.accounts.models import User
from apps.financial.models import FormaPagamento, MovimentacaoFinanceira
from apps.inventory.models import Estoque
from apps.products.models import Categoria, Produto
from apps.sales.models import Caixa, ItemVenda, PagamentoVenda, Venda

ZERO = Decimal("0.00")
LIMITE_LINHAS = 50


def _centavo(valor):
    """Normaliza valores agregados para 2 casas decimais."""
    return (valor or ZERO).quantize(Decimal("0.01"))


def _tenant_atual(request):
    tenant = request.user.get_tenant()
    if tenant is None:
        messages.info(
            request,
            "Usuário da plataforma não possui tenant para consultar relatórios.",
        )
        return None
    return tenant


def _periodo(request):
    hoje = timezone.localdate()
    padrao_inicio = hoje - timedelta(days=29)
    try:
        inicio = timezone.datetime.strptime(
            request.GET.get("inicio", ""), "%Y-%m-%d"
        ).date() if request.GET.get("inicio") else padrao_inicio
        fim = timezone.datetime.strptime(
            request.GET.get("fim", ""), "%Y-%m-%d"
        ).date() if request.GET.get("fim") else hoje
    except ValueError:
        inicio, fim = padrao_inicio, hoje
    if inicio > fim:
        inicio, fim = fim, inicio
    return inicio, fim


def _filtros(request, tenant):
    """Resolve filtros do GET contra o tenant (nunca confiar no frontend)."""
    produto_id = request.GET.get("produto", "").strip()
    categoria_id = request.GET.get("categoria", "").strip()
    operador_id = request.GET.get("operador", "").strip()
    caixa_uuid = request.GET.get("caixa", "").strip()
    forma_uuid = request.GET.get("forma_pagamento", "").strip()
    return {
        "produto": (
            Produto.objects.for_tenant(tenant).filter(pk=produto_id).first()
            if produto_id
            else None
        ),
        "categoria": (
            Categoria.objects.for_tenant(tenant).filter(pk=categoria_id).first()
            if categoria_id
            else None
        ),
        "operador": (
            User.objects.filter(tenant=tenant, pk=operador_id).first()
            if operador_id
            else None
        ),
        "caixa": (
            Caixa.objects.for_tenant(tenant).filter(uuid=caixa_uuid).first()
            if caixa_uuid
            else None
        ),
        "forma_pagamento": (
            FormaPagamento.objects.for_tenant(tenant).filter(uuid=forma_uuid).first()
            if forma_uuid
            else None
        ),
        "produto_id": produto_id,
        "categoria_id": categoria_id,
        "operador_id": operador_id,
        "caixa_uuid": caixa_uuid,
        "forma_uuid": forma_uuid,
    }


def _vendas_periodo(tenant, inicio, fim, filtros):
    vendas = Venda.objects.for_tenant(tenant).filter(
        status=Venda.Status.FINALIZADA,
        data_finalizacao__date__range=(inicio, fim),
    )
    if filtros["operador"] is not None:
        vendas = vendas.filter(operador=filtros["operador"])
    if filtros["caixa"] is not None:
        vendas = vendas.filter(caixa=filtros["caixa"])
    if filtros["produto"] is not None:
        vendas = vendas.filter(itens__produto=filtros["produto"])
    if filtros["categoria"] is not None:
        vendas = vendas.filter(itens__produto__categoria=filtros["categoria"])
    if filtros["forma_pagamento"] is not None:
        vendas = vendas.filter(
            pagamentos__forma_pagamento=filtros["forma_pagamento"]
        )
    return vendas.distinct()


@login_required
def indice(request):
    tenant = _tenant_atual(request)
    if tenant is None:
        return redirect("dashboard")

    inicio, fim = _periodo(request)
    filtros = _filtros(request, tenant)
    vendas = _vendas_periodo(tenant, inicio, fim, filtros)

    # --- Vendas por período ---
    agregado = vendas.aggregate(
        total=Sum("total"), quantidade=Count("id")
    )
    total_periodo = _centavo(agregado["total"])
    quantidade_vendas = agregado["quantidade"] or 0
    ticket_medio = (
        (total_periodo / quantidade_vendas).quantize(Decimal("0.01"))
        if quantidade_vendas
        else ZERO
    )
    vendas_por_dia = list(
        vendas.values("data_finalizacao__date")
        .annotate(total=Sum("total"), quantidade=Count("id"))
        .order_by("-data_finalizacao__date")[:LIMITE_LINHAS]
    )
    for linha in vendas_por_dia:
        linha["total"] = _centavo(linha["total"])
        linha["ticket_medio"] = (
            (linha["total"] / linha["quantidade"]).quantize(Decimal("0.01"))
            if linha["quantidade"]
            else ZERO
        )

    # --- Vendas por produto / categoria / operador / forma de pagamento ---
    vendas_por_produto = list(
        ItemVenda.objects.for_tenant(tenant)
        .filter(venda__in=vendas)
        .values("produto__nome")
        .annotate(
            quantidade=Sum("quantidade"),
            total=Sum("subtotal"),
        )
        .order_by("-total")[:LIMITE_LINHAS]
    )
    for linha in vendas_por_produto:
        linha["total"] = _centavo(linha["total"])
    vendas_por_categoria = list(
        ItemVenda.objects.for_tenant(tenant)
        .filter(venda__in=vendas)
        .values("produto__categoria__nome")
        .annotate(total=Sum("subtotal"))
        .order_by("-total")[:LIMITE_LINHAS]
    )
    for linha in vendas_por_categoria:
        linha["total"] = _centavo(linha["total"])
    vendas_por_operador = list(
        vendas.values("operador__username", "operador__first_name")
        .annotate(total=Sum("total"), quantidade=Count("id"))
        .order_by("-total")[:LIMITE_LINHAS]
    )
    for linha in vendas_por_operador:
        linha["total"] = _centavo(linha["total"])
    vendas_por_forma = list(
        PagamentoVenda.objects.for_tenant(tenant)
        .filter(venda__in=vendas)
        .values("forma_pagamento__nome")
        .annotate(total=Sum("valor"), quantidade=Count("id"))
        .order_by("-total")[:LIMITE_LINHAS]
    )
    for linha in vendas_por_forma:
        linha["total"] = _centavo(linha["total"])

    # --- Estoque ---
    saldos = list(
        Estoque.objects.for_tenant(tenant)
        .select_related("produto")
        .order_by("produto__nome")
    )
    estoque_baixo = [
        saldo
        for saldo in saldos
        if saldo.produto.estoque_minimo
        and saldo.quantidade <= saldo.produto.estoque_minimo
    ][:LIMITE_LINHAS]

    # --- Fechamentos de caixa ---
    fechamentos = list(
        Caixa.objects.for_tenant(tenant)
        .filter(status=Caixa.Status.FECHADO)
        .select_related("operador", "conta_financeira")
        .order_by("-data_fechamento")[:LIMITE_LINHAS]
    )

    # --- Movimentações financeiras ---
    movimentacoes = list(
        MovimentacaoFinanceira.objects.for_tenant(tenant)
        .filter(data__range=(inicio, fim))
        .select_related("conta_financeira", "usuario")
        .order_by("-data", "-id")[:LIMITE_LINHAS]
    )

    contexto = {
        "inicio": inicio,
        "fim": fim,
        "total_periodo": total_periodo,
        "quantidade_vendas": quantidade_vendas,
        "ticket_medio": ticket_medio,
        "vendas_por_dia": vendas_por_dia,
        "vendas_por_produto": vendas_por_produto,
        "vendas_por_categoria": vendas_por_categoria,
        "vendas_por_operador": vendas_por_operador,
        "vendas_por_forma": vendas_por_forma,
        "saldos": saldos[:LIMITE_LINHAS],
        "estoque_baixo": estoque_baixo,
        "fechamentos": fechamentos,
        "movimentacoes": movimentacoes,
        "produtos": Produto.objects.for_tenant(tenant).order_by("nome"),
        "categorias": Categoria.objects.for_tenant(tenant).filter(ativo=True),
        "operadores": User.objects.filter(tenant=tenant, is_active=True),
        "caixas": Caixa.objects.for_tenant(tenant).order_by("-data_abertura")[:200],
        "formas": FormaPagamento.objects.for_tenant(tenant).filter(ativo=True),
        "produto_id": filtros["produto_id"],
        "categoria_id": filtros["categoria_id"],
        "operador_id": filtros["operador_id"],
        "caixa_uuid": filtros["caixa_uuid"],
        "forma_uuid": filtros["forma_uuid"],
        "uso_filtros": any(
            [
                filtros["produto_id"],
                filtros["categoria_id"],
                filtros["operador_id"],
                filtros["caixa_uuid"],
                filtros["forma_uuid"],
            ]
        ),
    }
    return render(request, "reports/indice.html", contexto)
