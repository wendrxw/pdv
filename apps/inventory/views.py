from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import DecimalField, F, Q, Sum
from django.shortcuts import get_object_or_404, redirect, render

from apps.audit.models import registrar
from apps.products.models import Produto

from .forms import EntradaEstoqueForm, SaidaEstoqueForm
from .models import Estoque, MovimentacaoEstoque
from .services import (
    EstoqueError,
    adicionar_estoque,
    obter_ou_criar_estoque,
    remover_estoque,
)

ITENS_POR_PAGINA = 25


def _tenant_atual(request):
    tenant = request.user.get_tenant()
    if tenant is None:
        messages.info(
            request,
            "Usuário da plataforma não possui tenant para operar o estoque.",
        )
    return tenant


@login_required
def dashboard(request):
    tenant = _tenant_atual(request)
    if tenant is None:
        return redirect("dashboard")

    estoques = (
        Estoque.objects.for_tenant(tenant)
        .select_related("produto", "produto__categoria")
        .order_by("produto__nome")
    )
    agregados = estoques.aggregate(
        valor_custo=Sum(
            F("quantidade") * F("produto__preco_custo"), output_field=DecimalField()
        ),
        valor_venda=Sum(
            F("quantidade") * F("produto__preco_venda"), output_field=DecimalField()
        ),
    )
    produtos = Produto.objects.for_tenant(tenant)
    com_estoque = {e.produto_id: e for e in estoques}
    sem_estoque = sum(
        1
        for e in estoques
        if e.situacao == Estoque.Situacao.SEM_ESTOQUE
    )
    estoque_baixo = sum(
        1
        for e in estoques
        if e.situacao == Estoque.Situacao.ESTOQUE_BAIXO
    )

    ultimas_movimentacoes = MovimentacaoEstoque.objects.for_tenant(
        tenant
    ).select_related("produto", "usuario")[:10]
    ultimos_produtos = produtos.order_by("-data_cadastro")[:5]

    contexto = {
        "total_produtos": produtos.count(),
        "produtos_ativos": produtos.filter(ativo=True).count(),
        "sem_estoque": sem_estoque,
        "estoque_baixo": estoque_baixo,
        "valor_custo": agregados["valor_custo"] or Decimal("0"),
        "valor_venda": agregados["valor_venda"] or Decimal("0"),
        "ultimas_movimentacoes": ultimas_movimentacoes,
        "ultimos_produtos": ultimos_produtos,
        "com_estoque": com_estoque,
    }
    return render(request, "inventory/dashboard.html", contexto)


@login_required
def entrada(request):
    tenant = _tenant_atual(request)
    if tenant is None:
        return redirect("inventory:dashboard")

    if request.method == "POST":
        form = EntradaEstoqueForm(request.POST, tenant=tenant)
        if form.is_valid():
            dados = form.cleaned_data
            try:
                movimentacao = adicionar_estoque(
                    dados["produto"],
                    dados["quantidade"],
                    usuario=request.user,
                    motivo=dados["motivo"],
                    referencia=dados["referencia"],
                    fornecedor=dados["fornecedor"],
                    custo_unitario=dados["custo_unitario"],
                )
                messages.success(
                    request,
                    f"Entrada registrada: {movimentacao.quantidade} de "
                    f"{movimentacao.produto.nome}.",
                )
                return redirect("inventory:movimentacoes")
            except EstoqueError as exc:
                messages.error(request, str(exc))
    else:
        form = EntradaEstoqueForm(tenant=tenant)
    return render(
        request,
        "inventory/form_movimentacao.html",
        {"form": form, "titulo": "Entrada de mercadoria"},
    )


@login_required
def saida(request):
    tenant = _tenant_atual(request)
    if tenant is None:
        return redirect("inventory:dashboard")

    if request.method == "POST":
        form = SaidaEstoqueForm(request.POST, tenant=tenant)
        if form.is_valid():
            dados = form.cleaned_data
            try:
                movimentacao = remover_estoque(
                    dados["produto"],
                    dados["quantidade"],
                    usuario=request.user,
                    motivo=dados["motivo"],
                )
                messages.success(
                    request,
                    f"Saída registrada: {movimentacao.quantidade} de "
                    f"{movimentacao.produto.nome}.",
                )
                return redirect("inventory:movimentacoes")
            except EstoqueError as exc:
                messages.error(request, str(exc))
    else:
        form = SaidaEstoqueForm(tenant=tenant)
    return render(
        request,
        "inventory/form_movimentacao.html",
        {"form": form, "titulo": "Saída de mercadoria"},
    )


@login_required
def movimentacoes(request):
    tenant = _tenant_atual(request)
    if tenant is None:
        return redirect("inventory:dashboard")

    queryset = MovimentacaoEstoque.objects.for_tenant(tenant).select_related(
        "produto", "usuario", "fornecedor"
    )
    tipo = request.GET.get("tipo", "")
    produto_id = request.GET.get("produto", "")
    if tipo:
        queryset = queryset.filter(tipo=tipo)
    if produto_id:
        queryset = queryset.filter(produto_id=produto_id)

    paginador = Paginator(queryset, ITENS_POR_PAGINA)
    pagina = paginador.get_page(request.GET.get("page"))

    contexto = {
        "pagina": pagina,
        "tipos": MovimentacaoEstoque.Tipo.choices,
        "tipo_selecionado": tipo,
        "produtos": Produto.objects.for_tenant(tenant).order_by("nome"),
        "produto_selecionado": produto_id,
    }
    return render(request, "inventory/movimentacoes.html", contexto)


@login_required
def saldos(request):
    """Listagem de saldos por produto com situação visual."""
    tenant = _tenant_atual(request)
    if tenant is None:
        return redirect("inventory:dashboard")

    termo = request.GET.get("q", "").strip()
    estoques = (
        Estoque.objects.for_tenant(tenant)
        .select_related("produto")
        .order_by("produto__nome")
    )
    if termo:
        estoques = estoques.filter(
            Q(produto__nome__icontains=termo) | Q(produto__sku__icontains=termo)
        )
    paginador = Paginator(estoques, ITENS_POR_PAGINA)
    pagina = paginador.get_page(request.GET.get("page"))
    return render(
        request,
        "inventory/saldos.html",
        {"pagina": pagina, "termo": termo},
    )


@login_required
def detalhe_produto(request, produto_uuid):
    """Histórico completo de um produto (integridade §42)."""
    tenant = _tenant_atual(request)
    if tenant is None:
        return redirect("inventory:dashboard")
    produto = get_object_or_404(Produto, tenant=tenant, uuid=produto_uuid)
    estoque = obter_ou_criar_estoque(produto)
    movimentacoes_produto = (
        MovimentacaoEstoque.objects.for_tenant(tenant)
        .filter(produto=produto)
        .select_related("usuario", "fornecedor")
    )
    paginador = Paginator(movimentacoes_produto, ITENS_POR_PAGINA)
    pagina = paginador.get_page(request.GET.get("page"))
    registrar(
        "ESTOQUE_HISTORICO_CONSULTADO",
        entidade=produto,
        usuario=request.user,
        tenant=tenant,
    )
    return render(
        request,
        "inventory/historico_produto.html",
        {"produto": produto, "estoque": estoque, "pagina": pagina},
    )
