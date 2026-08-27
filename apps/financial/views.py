import json
from datetime import timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from apps.accounts.models import User
from apps.audit.models import registrar
from apps.products.models import Categoria as CategoriaProduto
from apps.sales.models import Caixa, Venda

from .forms import (
    ContaFinanceiraForm,
    ContaReceberForm,
    EntradaForm,
    SaidaForm,
)
from .models import (
    CategoriaFinanceira,
    ContaFinanceira,
    ContaReceber,
    Entrada,
    FormaPagamento,
    ParcelaReceber,
    Saida,
)
from .services import (
    FinancialError,
    cancelar_conta_receber,
    cancelar_entrada,
    cancelar_saida,
    criar_categoria,
    criar_conta,
    criar_conta_receber,
    criar_entrada,
    criar_saida,
    estornar_pagamento_saida,
    estornar_recebimento_entrada,
    pagar_saida,
    receber_entrada,
    receber_parcela,
    resumo_controle,
)

ITENS_POR_PAGINA = 25


def _tenant_atual(request, modulo="financeiro"):
    tenant = request.user.get_tenant()
    if tenant is None:
        messages.info(
            request,
            f"Usuário da plataforma não possui tenant para operar o {modulo}.",
        )
    return tenant


def _periodo(request):
    """Datas do GET com padrão: últimos 30 dias."""
    hoje = timezone.localdate()
    padrao_inicio = hoje - timedelta(days=30)
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


PRESETS_PERIODO = {
    "hoje": "Hoje",
    "ontem": "Ontem",
    "semana": "Esta semana",
    "mes": "Este mês",
    "7d": "Últimos 7 dias",
    "30d": "Últimos 30 dias",
    "personalizado": "Período personalizado",
}


def _periodo_controle(request):
    """Período do dashboard: presets ou intervalo personalizado."""
    hoje = timezone.localdate()
    periodo = request.GET.get("periodo", "30d")
    inicio_semana = hoje - timedelta(days=hoje.weekday())
    primeiro_mes = hoje.replace(day=1)
    intervalos = {
        "hoje": (hoje, hoje),
        "ontem": (hoje - timedelta(days=1), hoje - timedelta(days=1)),
        "semana": (inicio_semana, hoje),
        "mes": (primeiro_mes, hoje),
        "7d": (hoje - timedelta(days=6), hoje),
        "30d": (hoje - timedelta(days=29), hoje),
    }
    if periodo == "personalizado":
        inicio, fim = _periodo(request)
    else:
        inicio, fim = intervalos.get(periodo, intervalos["30d"])
        if periodo not in intervalos:
            periodo = "30d"
    return inicio, fim, periodo


def _filtros_controle(request, tenant):
    """Filtros opcionais do dashboard, sempre validados contra o tenant."""
    forma_uuid = request.GET.get("forma_pagamento", "").strip()
    categoria_pk = request.GET.get("categoria", "").strip()
    operador_pk = request.GET.get("operador", "").strip()
    caixa_uuid = request.GET.get("caixa", "").strip()
    status = request.GET.get("status", Venda.Status.FINALIZADA)
    if status not in (Venda.Status.FINALIZADA, Venda.Status.CANCELADA, "TODAS"):
        status = Venda.Status.FINALIZADA
    return {
        "forma_pagamento": (
            FormaPagamento.objects.for_tenant(tenant).filter(uuid=forma_uuid).first()
            if forma_uuid
            else None
        ),
        "categoria": (
            CategoriaProduto.objects.for_tenant(tenant)
            .filter(pk=categoria_pk)
            .first()
            if categoria_pk
            else None
        ),
        "operador": (
            User.objects.filter(tenant=tenant, pk=operador_pk).first()
            if operador_pk
            else None
        ),
        "caixa": (
            Caixa.objects.for_tenant(tenant).filter(uuid=caixa_uuid).first()
            if caixa_uuid
            else None
        ),
        "status": status,
        "forma_uuid": forma_uuid,
        "categoria_pk": categoria_pk,
        "operador_pk": operador_pk,
        "caixa_uuid": caixa_uuid,
    }


# ---------------------------------------------------------------------------
# Análise
# ---------------------------------------------------------------------------


@login_required
def analise(request):
    tenant = _tenant_atual(request)
    if tenant is None:
        return redirect("dashboard")
    inicio, fim, periodo = _periodo_controle(request)
    filtros = _filtros_controle(request, tenant)
    try:
        controle = resumo_controle(
            tenant,
            inicio=inicio,
            fim=fim,
            forma_pagamento=filtros["forma_pagamento"],
            categoria=filtros["categoria"],
            operador=filtros["operador"],
            caixa=filtros["caixa"],
            status=filtros["status"],
        )
    except FinancialError as exc:
        messages.error(request, str(exc))
        controle = resumo_controle(tenant, inicio=fim, fim=fim)

    serie_json = json.dumps(
        [
            {"data": linha["data"].strftime("%d/%m/%Y"), "total": float(linha["total"])}
            for linha in controle["serie"]
        ],
        ensure_ascii=False,
    )
    por_forma_json = json.dumps(
        [
            {
                "nome": linha["nome"],
                "total": float(linha["total"]),
                "pct": float(linha["pct"]),
            }
            for linha in controle["por_forma"]
        ],
        ensure_ascii=False,
    )
    contexto = {
        "inicio": inicio,
        "fim": fim,
        "periodo": periodo,
        "presets_periodo": PRESETS_PERIODO,
        "status": filtros["status"],
        "statuses_controle": [
            (Venda.Status.FINALIZADA, "Finalizadas"),
            (Venda.Status.CANCELADA, "Canceladas"),
            ("TODAS", "Todas"),
        ],
        "forma_uuid": filtros["forma_uuid"],
        "categoria_pk": filtros["categoria_pk"],
        "operador_pk": filtros["operador_pk"],
        "caixa_uuid": filtros["caixa_uuid"],
        "formas": FormaPagamento.objects.for_tenant(tenant).filter(ativo=True),
        "categorias": CategoriaProduto.objects.for_tenant(tenant).filter(ativo=True),
        "operadores": User.objects.filter(tenant=tenant, is_active=True),
        "caixas": Caixa.objects.for_tenant(tenant),
        "serie_json": serie_json,
        "por_forma_json": por_forma_json,
        "resumo_dia": controle["resumo_dia"][::-1][:5],
        "por_categoria": controle["por_categoria"],
        **controle,
    }
    return render(request, "financial/dashboard.html", contexto)


# ---------------------------------------------------------------------------
# Entradas
# ---------------------------------------------------------------------------


@login_required
def entradas(request):
    tenant = _tenant_atual(request)
    if tenant is None:
        return redirect("dashboard")
    lancamentos = Entrada.objects.for_tenant(tenant).select_related(
        "categoria", "conta_financeira"
    )
    status = request.GET.get("status", "")
    busca = request.GET.get("q", "")
    if status:
        lancamentos = lancamentos.filter(status=status)
    if busca:
        lancamentos = lancamentos.filter(descricao__icontains=busca)
    paginador = Paginator(lancamentos, ITENS_POR_PAGINA)
    pagina = paginador.get_page(request.GET.get("page"))
    return render(
        request,
        "financial/lancamento_lista.html",
        {
            "tipo": "entrada",
            "pagina": pagina,
            "status": status,
            "busca": busca,
            "statuses": Entrada.Status.choices,
        },
    )


@login_required
def entrada_nova(request):
    tenant = _tenant_atual(request)
    if tenant is None:
        return redirect("dashboard")
    if request.method == "POST":
        form = EntradaForm(request.POST, tenant=tenant)
        if form.is_valid():
            acao = request.POST.get("acao", "pendente")
            status = (
                Entrada.Status.PREVISTA
                if acao == "prevista"
                else Entrada.Status.PENDENTE
            )
            try:
                entrada = criar_entrada(
                    tenant,
                    **{
                        campo: form.cleaned_data[campo]
                        for campo in (
                            "descricao",
                            "valor",
                            "categoria",
                            "conta_financeira",
                            "forma_pagamento",
                            "data_competencia",
                            "data_prevista",
                            "observacao",
                        )
                    },
                    status=status,
                    usuario=request.user,
                )
                if acao == "recebido":
                    receber_entrada(entrada, usuario=request.user)
                messages.success(request, "Entrada registrada.")
                registrar(
                    "criou entrada financeira",
                    entidade=entrada,
                    usuario=request.user,
                    tenant=tenant,
                    dados={"uuid": str(entrada.uuid), "valor": str(entrada.valor)},
                )
                return redirect("financial:entrada_detalhe", uuid=entrada.uuid)
            except FinancialError as exc:
                messages.error(request, str(exc))
    else:
        form = EntradaForm(tenant=tenant)
    return render(
        request,
        "financial/lancamento_formulario.html",
        {"tipo": "entrada", "form": form},
    )


def _obter(model, tenant, uuid):
    return get_object_or_404(model, tenant=tenant, uuid=uuid)


@login_required
def entrada_detalhe(request, uuid):
    tenant = _tenant_atual(request)
    if tenant is None:
        return redirect("dashboard")
    entrada = _obter(Entrada, tenant, uuid)
    movimentacoes = []
    if request.method == "POST":
        acao = request.POST.get("acao")
        motivo = request.POST.get("motivo", "").strip()
        conta_id = request.POST.get("conta_financeira")
        conta = None
        if conta_id:
            conta = ContaFinanceira.objects.for_tenant(tenant).filter(
                pk=conta_id
            ).first()
        try:
            if acao == "receber":
                receber_entrada(
                    entrada, conta_financeira=conta, usuario=request.user
                )
                messages.success(request, "Recebimento registrado.")
            elif acao == "cancelar":
                cancelar_entrada(entrada, usuario=request.user)
                messages.success(request, "Entrada cancelada.")
            elif acao == "estornar":
                estornar_recebimento_entrada(
                    entrada, motivo=motivo, usuario=request.user
                )
                messages.success(request, "Recebimento estornado.")
        except FinancialError as exc:
            messages.error(request, str(exc))
        return redirect("financial:entrada_detalhe", uuid=uuid)
    movimentacoes = _movimentacoes_de(entrada)
    contas = ContaFinanceira.objects.for_tenant(tenant).filter(ativo=True)
    return render(
        request,
        "financial/lancamento_detalhe.html",
        {
            "tipo": "entrada",
            "lancamento": entrada,
            "movimentacoes": movimentacoes,
            "contas": contas,
        },
    )


def _movimentacoes_de(lancamento):
    from .models import MovimentacaoFinanceira

    return MovimentacaoFinanceira.objects.for_tenant(
        lancamento.tenant
    ).filter(referencia_uuid=lancamento.uuid)


# ---------------------------------------------------------------------------
# Saídas
# ---------------------------------------------------------------------------


@login_required
def saidas(request):
    tenant = _tenant_atual(request)
    if tenant is None:
        return redirect("dashboard")
    lancamentos = Saida.objects.for_tenant(tenant).select_related(
        "categoria", "conta_financeira"
    )
    status = request.GET.get("status", "")
    busca = request.GET.get("q", "")
    if status:
        lancamentos = lancamentos.filter(status=status)
    if busca:
        lancamentos = lancamentos.filter(descricao__icontains=busca)
    paginador = Paginator(lancamentos, ITENS_POR_PAGINA)
    pagina = paginador.get_page(request.GET.get("page"))
    return render(
        request,
        "financial/lancamento_lista.html",
        {
            "tipo": "saida",
            "pagina": pagina,
            "status": status,
            "busca": busca,
            "statuses": Saida.Status.choices,
        },
    )


@login_required
def saida_nova(request):
    tenant = _tenant_atual(request)
    if tenant is None:
        return redirect("dashboard")
    if request.method == "POST":
        form = SaidaForm(request.POST, tenant=tenant)
        if form.is_valid():
            acao = request.POST.get("acao", "pendente")
            try:
                saida = criar_saida(
                    tenant,
                    **{
                        campo: form.cleaned_data[campo]
                        for campo in (
                            "descricao",
                            "valor",
                            "categoria",
                            "conta_financeira",
                            "data_competencia",
                            "data_vencimento",
                            "observacao",
                        )
                    },
                    status=(
                        Saida.Status.PREVISTA
                        if acao == "prevista"
                        else Saida.Status.PENDENTE
                    ),
                    usuario=request.user,
                )
                if acao == "pago":
                    pagar_saida(saida, usuario=request.user)
                messages.success(request, "Saída registrada.")
                registrar(
                    "criou saída financeira",
                    entidade=saida,
                    usuario=request.user,
                    tenant=tenant,
                    dados={"uuid": str(saida.uuid), "valor": str(saida.valor)},
                )
                return redirect("financial:saida_detalhe", uuid=saida.uuid)
            except FinancialError as exc:
                messages.error(request, str(exc))
    else:
        form = SaidaForm(tenant=tenant)
    return render(
        request,
        "financial/lancamento_formulario.html",
        {"tipo": "saida", "form": form},
    )


@login_required
def saida_detalhe(request, uuid):
    tenant = _tenant_atual(request)
    if tenant is None:
        return redirect("dashboard")
    saida = _obter(Saida, tenant, uuid)
    if request.method == "POST":
        acao = request.POST.get("acao")
        motivo = request.POST.get("motivo", "").strip()
        conta_id = request.POST.get("conta_financeira")
        conta = None
        if conta_id:
            conta = ContaFinanceira.objects.for_tenant(tenant).filter(
                pk=conta_id
            ).first()
        try:
            if acao == "pagar":
                pagar_saida(saida, conta_financeira=conta, usuario=request.user)
                messages.success(request, "Pagamento registrado.")
            elif acao == "cancelar":
                cancelar_saida(saida, usuario=request.user)
                messages.success(request, "Saída cancelada.")
            elif acao == "estornar":
                estornar_pagamento_saida(
                    saida, motivo=motivo, usuario=request.user
                )
                messages.success(request, "Pagamento estornado.")
        except FinancialError as exc:
            messages.error(request, str(exc))
        return redirect("financial:saida_detalhe", uuid=uuid)
    movimentacoes = _movimentacoes_de(saida)
    contas = ContaFinanceira.objects.for_tenant(tenant).filter(ativo=True)
    return render(
        request,
        "financial/lancamento_detalhe.html",
        {
            "tipo": "saida",
            "lancamento": saida,
            "movimentacoes": movimentacoes,
            "contas": contas,
        },
    )


# ---------------------------------------------------------------------------
# Contas a receber
# ---------------------------------------------------------------------------


@login_required
def receber(request):
    tenant = _tenant_atual(request)
    if tenant is None:
        return redirect("dashboard")
    contas = ContaReceber.objects.for_tenant(tenant)
    status = request.GET.get("status", "")
    busca = request.GET.get("q", "")
    if status:
        contas = contas.filter(status=status)
    if busca:
        contas = contas.filter(
            descricao__icontains=busca
        ) | contas.filter(cliente_nome__icontains=busca)
    paginador = Paginator(contas, ITENS_POR_PAGINA)
    pagina = paginador.get_page(request.GET.get("page"))
    return render(
        request,
        "financial/receber_lista.html",
        {
            "pagina": pagina,
            "status": status,
            "busca": busca,
            "statuses": ContaReceber.Status.choices,
        },
    )


@login_required
def receber_nova(request):
    tenant = _tenant_atual(request)
    if tenant is None:
        return redirect("dashboard")
    if request.method == "POST":
        form = ContaReceberForm(request.POST)
        if form.is_valid():
            dados = form.cleaned_data
            vencimentos = [
                dados["primeiro_vencimento"]
                + (timedelta(days=30 * i))
                for i in range(dados["quantidade_parcelas"])
            ]
            try:
                conta = criar_conta_receber(
                    tenant,
                    descricao=dados["descricao"],
                    valor_total=dados["valor_total"],
                    parcelas=dados["quantidade_parcelas"],
                    cliente_nome=dados["cliente_nome"],
                    vencimentos=vencimentos,
                    usuario=request.user,
                )
                messages.success(request, "Conta a receber criada.")
                return redirect("financial:receber_detalhe", uuid=conta.uuid)
            except FinancialError as exc:
                messages.error(request, str(exc))
    else:
        form = ContaReceberForm(
            initial={"primeiro_vencimento": timezone.localdate()}
        )
    return render(request, "financial/receber_novo.html", {"form": form})


@login_required
def receber_detalhe(request, uuid):
    tenant = _tenant_atual(request)
    if tenant is None:
        return redirect("dashboard")
    conta = _obter(ContaReceber, tenant, uuid)
    if request.method == "POST":
        acao = request.POST.get("acao")
        try:
            if acao == "cancelar":
                cancelar_conta_receber(conta, usuario=request.user)
                messages.success(request, "Conta cancelada.")
            elif acao == "receber_parcela":
                parcela = get_object_or_404(
                    ParcelaReceber,
                    tenant=tenant,
                    uuid=request.POST.get("parcela_uuid"),
                )
                conta_id = request.POST.get("conta_financeira")
                destino = get_object_or_404(
                    ContaFinanceira, tenant=tenant, pk=conta_id
                )
                receber_parcela(parcela, conta_financeira=destino, usuario=request.user)
                messages.success(request, f"Parcela {parcela.numero} recebida.")
        except FinancialError as exc:
            messages.error(request, str(exc))
        return redirect("financial:receber_detalhe", uuid=uuid)
    parcelas = conta.parcelas.all()
    contas = ContaFinanceira.objects.for_tenant(tenant).filter(ativo=True)
    return render(
        request,
        "financial/receber_detalhe.html",
        {"conta": conta, "parcelas": parcelas, "contas": contas},
    )


# ---------------------------------------------------------------------------
# Contas financeiras e categorias
# ---------------------------------------------------------------------------


@login_required
def contas(request):
    tenant = _tenant_atual(request)
    if tenant is None:
        return redirect("dashboard")
    lista = ContaFinanceira.objects.for_tenant(tenant)
    categorias = CategoriaFinanceira.objects.for_tenant(tenant)
    if request.method == "POST" and request.POST.get("tipo_objeto") == "conta":
        form = ContaFinanceiraForm(request.POST)
        if form.is_valid():
            try:
                criar_conta(
                    tenant,
                    nome=form.cleaned_data["nome"],
                    tipo=form.cleaned_data["tipo"],
                    saldo_inicial=form.cleaned_data["saldo_inicial"],
                    usuario=request.user,
                )
                messages.success(request, "Conta financeira criada.")
                return redirect("financial:contas")
            except FinancialError as exc:
                messages.error(request, str(exc))
    elif request.method == "POST" and request.POST.get("tipo_objeto") == "categoria":
        nome = request.POST.get("nome", "").strip()
        tipo = request.POST.get("tipo_categoria", "AMBOS")
        pai_id = request.POST.get("categoria_pai")
        pai = None
        if pai_id:
            pai = (
                CategoriaFinanceira.objects.for_tenant(tenant)
                .filter(pk=pai_id)
                .first()
            )
        try:
            criar_categoria(
                tenant, nome=nome, tipo=tipo, categoria_pai=pai, usuario=request.user
            )
            messages.success(request, "Categoria criada.")
            return redirect("financial:contas")
        except FinancialError as exc:
            messages.error(request, str(exc))
    return render(
        request,
        "financial/contas.html",
        {"lista": lista, "categorias": categorias, "form_conta": ContaFinanceiraForm()},
    )
