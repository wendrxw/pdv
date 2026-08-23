"""Views do PDV, histórico de vendas e caixas.

Views apenas orquestram: regras de negócio vivem em services.py. O
isolamento multi-tenant é garantido filtrando sempre pelo tenant do
usuário autenticado — nunca por parâmetros do frontend.
"""

from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render

from apps.financial.models import FormaPagamento
from apps.printing.models import ConfiguracaoImpressao, PrintJob
from apps.printing.services import (
    PrintingError,
    criar_print_job,
    reativar_print_job,
)
from apps.products.models import Produto

from .forms import (
    AbrirCaixaForm,
    FecharCaixaForm,
    MovimentacaoCaixaForm,
    PagamentoVendaForm,
)
from .models import Caixa, ItemVenda, Venda
from .services import (
    SalesError,
    abrir_caixa,
    abrir_venda,
    adicionar_item,
    adicionar_pagamento,
    aplicar_desconto,
    cancelar_venda,
    fechar_caixa,
    finalizar_venda,
    remover_item,
    sangria,
    suprimento,
)

ITENS_POR_PAGINA = 25


def _tenant_atual(request, modulo="PDV"):
    tenant = request.user.get_tenant()
    if tenant is None:
        messages.info(
            request,
            f"Usuário da plataforma não possui tenant para operar o {modulo}.",
        )
    return tenant


def _decimal(valor):
    try:
        return Decimal(str(valor).replace(",", "."))
    except (InvalidOperation, TypeError, ValueError):
        return None


# ---------------------------------------------------------------------------
# PDV (/app/pdv/)
# ---------------------------------------------------------------------------


@login_required
def pdv_home(request):
    """Tela do operador: caixas abertos e abertura de novo caixa."""
    tenant = _tenant_atual(request)
    if tenant is None:
        return redirect("dashboard")
    caixas_abertos = (
        Caixa.objects.for_tenant(tenant)
        .filter(status=Caixa.Status.ABERTO)
        .select_related("operador", "conta_financeira")
    )
    vendas_abertas = Venda.objects.for_tenant(tenant).filter(
        status=Venda.Status.ABERTA
    ).select_related("caixa", "operador")
    if request.method == "POST":
        form = AbrirCaixaForm(request.POST)
        if form.is_valid():
            try:
                abrir_caixa(
                    tenant,
                    operador=request.user,
                    saldo_inicial=form.cleaned_data.get("saldo_inicial") or Decimal("0"),
                )
                messages.success(request, "Caixa aberto.")
                return redirect("sales:pdv")
            except SalesError as exc:
                messages.error(request, str(exc))
    else:
        form = AbrirCaixaForm()
    return render(
        request,
        "sales/pdv.html",
        {
            "form": form,
            "caixas_abertos": caixas_abertos,
            "vendas_abertas": vendas_abertas,
        },
    )


@login_required
def nova_venda(request, caixa_uuid=None):
    """Cria uma venda no caixa informado (ou abre um caixa automaticamente
    com a conta principal) e abre a tela de venda."""
    tenant = _tenant_atual(request)
    if tenant is None:
        return redirect("dashboard")
    if caixa_uuid:
        caixa = get_object_or_404(Caixa, tenant=tenant, uuid=caixa_uuid)
    else:
        caixa = (
            Caixa.objects.for_tenant(tenant)
            .filter(operador=request.user, status=Caixa.Status.ABERTO)
            .order_by("-data_abertura")
            .first()
        )
        if caixa is None:
            try:
                caixa = abrir_caixa(tenant, operador=request.user)
                messages.success(request, "Caixa aberto automaticamente.")
            except SalesError as exc:
                messages.error(request, str(exc))
                return redirect("sales:pdv")
    venda = abrir_venda(caixa)
    return redirect("sales:venda_tela", uuid=venda.uuid)


@login_required
def venda_tela(request, uuid):
    """Tela de venda: carrinho server-side com POSTs rápidos."""
    tenant = _tenant_atual(request)
    if tenant is None:
        return redirect("dashboard")
    venda = get_object_or_404(
        Venda.objects.for_tenant(tenant).select_related("caixa"), uuid=uuid
    )
    if request.method == "POST":
        acao = request.POST.get("acao")
        try:
            _executar_acao_venda(request, venda, acao)
        except SalesError as exc:
            messages.error(request, str(exc))
        venda.refresh_from_db()
        if venda.status != Venda.Status.ABERTA:
            return redirect("sales:venda_detalhe", uuid=venda.uuid)
        return redirect("sales:venda_tela", uuid=venda.uuid)

    formas = FormaPagamento.objects.for_tenant(tenant).filter(ativo=True)
    pago = sum(p.valor for p in venda.pagamentos.all())
    return render(
        request,
        "sales/venda.html",
        {
            "venda": venda,
            "itens": venda.itens.select_related("produto"),
            "pagamentos": venda.pagamentos.select_related("forma_pagamento"),
            "formas": formas,
            "pago": pago,
            "falta": venda.total - pago,
            "pagamento_form": PagamentoVendaForm(tenant=tenant),
        },
    )


def _executar_acao_venda(request, venda, acao):
    usuario = request.user
    if acao == "add_item":
        produto_uuid = request.POST.get("produto", "").strip()
        quantidade = _decimal(request.POST.get("quantidade") or 1)
        produto = Produto.objects.for_tenant(venda.tenant).filter(
            uuid=produto_uuid
        ).first()
        if produto is None:
            raise SalesError("Produto não encontrado neste tenant.")
        if quantidade is None:
            raise SalesError("Quantidade inválida.")
        adicionar_item(venda, produto, quantidade, usuario=usuario)
    elif acao == "remover_item":
        item = get_object_or_404(
            ItemVenda, venda=venda, uuid=request.POST.get("item", "")
        )
        remover_item(venda, item, usuario=usuario)
    elif acao == "desconto":
        desconto = _decimal(request.POST.get("desconto"))
        if desconto is None:
            raise SalesError("Desconto inválido.")
        aplicar_desconto(venda, desconto, usuario=usuario)
    elif acao == "pagamento":
        pagamento_form = PagamentoVendaForm(request.POST, tenant=venda.tenant)
        valor = _decimal(request.POST.get("valor"))
        if not pagamento_form.is_valid() or valor is None:
            raise SalesError("Pagamento inválido.")
        adicionar_pagamento(
            venda, pagamento_form.cleaned_data["forma_pagamento"], valor
        )
    elif acao == "finalizar":
        forma = None
        forma_uuid = request.POST.get("forma_pagamento", "").strip()
        if forma_uuid:
            forma = (
                FormaPagamento.objects.for_tenant(venda.tenant)
                .filter(uuid=forma_uuid)
                .first()
            )
            if forma is None:
                raise SalesError("Forma de pagamento inválida.")
        finalizar_venda(venda, usuario=usuario, forma_pagamento=forma)
        venda.refresh_from_db()
        messages.success(request, f"Venda {venda.numero} finalizada.")
        # Impressão OBRIGATÓRIA: ao confirmar o pagamento (finalização da
        # venda) o comprovante é sempre enfileirado. Falha de impressão
        # nunca bloqueia a venda — apenas avisa o operador.
        try:
            criar_print_job(venda, usuario=usuario)
        except PrintingError as exc:
            messages.warning(request, f"Impressão: {exc}")
    elif acao == "cancelar":
        motivo = request.POST.get("motivo", "")
        cancelar_venda(venda, motivo=motivo, usuario=usuario)
        messages.success(request, f"Venda {venda.numero} cancelada.")
    else:
        raise SalesError(f"Ação desconhecida: {acao}")


@login_required
def produto_busca(request):
    """Busca JSON para o PDV: nome, SKU ou código de barras.

    Compatível com leitor USB HID (código completo + Enter).
    """
    tenant = request.user.get_tenant()
    if tenant is None:
        return JsonResponse({"resultados": []})
    termo = request.GET.get("q", "").strip()
    produtos = Produto.objects.for_tenant(tenant).filter(ativo=True)
    if termo:
        from django.db.models import Q

        produtos = produtos.filter(
            Q(nome__icontains=termo)
            | Q(sku__iexact=termo)
            | Q(codigo_barras__iexact=termo)
        )
    resultados = [
        {
            "uuid": str(p.uuid),
            "nome": p.nome,
            "sku": p.sku,
            "codigo_barras": p.codigo_barras,
            "preco": str(p.preco_venda),
            "estoque": str(
                getattr(getattr(p, "estoque", None), "quantidade", "")
            ),
        }
        for p in produtos.select_related("estoque")[:10]
    ]
    return JsonResponse({"resultados": resultados})


# ---------------------------------------------------------------------------
# Histórico de vendas (/app/vendas/)
# ---------------------------------------------------------------------------


@login_required
def vendas_lista(request):
    tenant = _tenant_atual(request, "histórico de vendas")
    if tenant is None:
        return redirect("dashboard")
    vendas = Venda.objects.for_tenant(tenant).select_related("caixa", "operador")
    status = request.GET.get("status", "")
    busca = request.GET.get("q", "")
    if status:
        vendas = vendas.filter(status=status)
    if busca:
        if busca.isdigit():
            vendas = vendas.filter(numero=int(busca)) | vendas.filter(
                cliente_nome__icontains=busca
            )
        else:
            vendas = vendas.filter(cliente_nome__icontains=busca)
    paginador = Paginator(vendas.order_by("-data_abertura"), ITENS_POR_PAGINA)
    pagina = paginador.get_page(request.GET.get("page"))
    return render(
        request,
        "sales/venda_lista.html",
        {
            "pagina": pagina,
            "status": status,
            "busca": busca,
            "statuses": Venda.Status.choices,
        },
    )


@login_required
def venda_detalhe(request, uuid):
    tenant = _tenant_atual(request, "histórico de vendas")
    if tenant is None:
        return redirect("dashboard")
    venda = get_object_or_404(Venda.objects.for_tenant(tenant), uuid=uuid)
    if request.method == "POST":
        acao = request.POST.get("acao", "cancelar")
        if acao == "imprimir":
            try:
                criar_print_job(venda, usuario=request.user)
                messages.success(request, "Comprovante enviado para impressão.")
            except PrintingError as exc:
                messages.error(request, str(exc))
        elif acao == "tentar_novamente":
            job = (
                PrintJob.objects.for_tenant(tenant)
                .filter(venda=venda)
                .order_by("-data_criacao")
                .first()
            )
            try:
                if job is None:
                    criar_print_job(venda, usuario=request.user)
                else:
                    reativar_print_job(job, usuario=request.user)
                messages.success(request, "Nova tentativa de impressão enviada.")
            except PrintingError as exc:
                messages.error(request, str(exc))
        else:
            try:
                cancelar_venda(
                    venda,
                    motivo=request.POST.get("motivo", ""),
                    usuario=request.user,
                )
                messages.success(request, f"Venda {venda.numero} cancelada.")
            except SalesError as exc:
                messages.error(request, str(exc))
        return redirect("sales:venda_detalhe", uuid=venda.uuid)
    config = ConfiguracaoImpressao.objects.filter(tenant=tenant).first()
    print_job = (
        PrintJob.objects.for_tenant(tenant)
        .filter(venda=venda)
        .order_by("-data_criacao")
        .first()
    )
    return render(
        request,
        "sales/venda_detalhe.html",
        {
            "venda": venda,
            "itens": venda.itens.select_related("produto"),
            "pagamentos": venda.pagamentos.select_related("forma_pagamento"),
            "config_impressao": config,
            "print_job": print_job,
        },
    )


# ---------------------------------------------------------------------------
# Caixas (/app/caixa/)
# ---------------------------------------------------------------------------


@login_required
def caixas_lista(request):
    """Mesma tela do PDV: abertura + lista completa de caixas."""
    tenant = _tenant_atual(request, "caixa")
    if tenant is None:
        return redirect("dashboard")
    if request.method == "POST":
        form = AbrirCaixaForm(request.POST)
        if form.is_valid():
            try:
                abrir_caixa(
                    tenant,
                    operador=request.user,
                    saldo_inicial=form.cleaned_data.get("saldo_inicial") or Decimal("0"),
                )
                messages.success(request, "Caixa aberto.")
                return redirect("sales:caixas")
            except SalesError as exc:
                messages.error(request, str(exc))
    else:
        form = AbrirCaixaForm()
    lista = Caixa.objects.for_tenant(tenant).select_related(
        "operador", "conta_financeira"
    )
    paginador = Paginator(lista.order_by("-data_abertura"), ITENS_POR_PAGINA)
    pagina = paginador.get_page(request.GET.get("page"))
    form = AbrirCaixaForm()
    abertos = lista.filter(status=Caixa.Status.ABERTO)
    return render(
        request,
        "sales/caixa_lista.html",
        {"pagina": pagina, "form": form, "abertos": abertos},
    )


@login_required
def caixa_detalhe(request, uuid):
    """Conferência do caixa: movimentações, vendas e fechamento."""
    tenant = _tenant_atual(request, "caixa")
    if tenant is None:
        return redirect("dashboard")
    caixa = get_object_or_404(Caixa.objects.for_tenant(tenant), uuid=uuid)
    if request.method == "POST":
        form = FecharCaixaForm(request.POST)
        if form.is_valid():
            try:
                fechar_caixa(
                    caixa,
                    saldo_informado=form.cleaned_data["saldo_informado"],
                    observacao=form.cleaned_data["observacao"],
                    usuario=request.user,
                )
                messages.success(request, "Caixa fechado.")
                return redirect("sales:caixa_detalhe", uuid=uuid)
            except SalesError as exc:
                messages.error(request, str(exc))
    else:
        form = FecharCaixaForm()
    from .services import saldo_esperado_caixa

    esperado = (
        saldo_esperado_caixa(caixa)
        if caixa.status == Caixa.Status.ABERTO
        else caixa.saldo_final_esperado
    )
    return render(
        request,
        "sales/caixa_detalhe.html",
        {
            "caixa": caixa,
            "esperado": esperado,
            "movimentacoes": caixa.movimentacoes.select_related("usuario"),
            "vendas": caixa.vendas.order_by("-data_abertura")[:50],
            "form": form,
            "mov_form": MovimentacaoCaixaForm(),
        },
    )


@login_required
def movimentacao_caixa(request, uuid):
    """Suprimento/sangria durante o turno (POST)."""
    tenant = _tenant_atual(request, "caixa")
    if tenant is None:
        return redirect("dashboard")
    caixa = get_object_or_404(Caixa.objects.for_tenant(tenant), uuid=uuid)
    if request.method == "POST":
        form = MovimentacaoCaixaForm(request.POST)
        tipo = request.POST.get("tipo")
        if form.is_valid() and tipo in ("SUPRIMENTO", "SANGRIA"):
            try:
                funcao = suprimento if tipo == "SUPRIMENTO" else sangria
                funcao(
                    caixa,
                    valor=form.cleaned_data["valor"],
                    motivo=form.cleaned_data["motivo"],
                    usuario=request.user,
                )
                messages.success(
                    request, f"{tipo.title()} registrado."
                )
            except SalesError as exc:
                messages.error(request, str(exc))
        else:
            messages.error(request, "Dados inválidos para a movimentação.")
    return redirect("sales:caixa_detalhe", uuid=uuid)
