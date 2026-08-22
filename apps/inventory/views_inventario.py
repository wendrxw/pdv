
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404, redirect, render

from apps.products.models import Produto

from .inventario import (
    InventarioError,
    cancelar,
    enviar_para_revisao,
    finalizar,
    iniciar_contagem,
    iniciar_inventario,
    registrar_contagem,
)
from .models import Inventario


def _tenant_atual(request):
    tenant = request.user.get_tenant()
    if tenant is None:
        messages.info(
            request,
            "Usuário da plataforma não possui tenant para operar inventários.",
        )
    return tenant


def _obter_inventario(tenant, uuid):
    return get_object_or_404(Inventario, tenant=tenant, uuid=uuid)


@login_required
def lista(request):
    tenant = _tenant_atual(request)
    if tenant is None:
        return redirect("dashboard")
    inventarios = Inventario.objects.for_tenant(tenant).select_related(
        "usuario_criacao"
    )
    status = request.GET.get("status", "")
    if status:
        inventarios = inventarios.filter(status=status)
    paginador = Paginator(inventarios, 25)
    pagina = paginador.get_page(request.GET.get("page"))
    return render(
        request,
        "inventory/inventario_lista.html",
        {
            "pagina": pagina,
            "status": status,
            "status_choices": Inventario.Status.choices,
        },
    )


@login_required
def novo(request):
    tenant = _tenant_atual(request)
    if tenant is None:
        return redirect("inventory:lista")

    if request.method == "POST":
        descricao = request.POST.get("descricao", "").strip()
        selecionados = request.POST.getlist("produtos")
        produtos = Produto.objects.for_tenant(tenant).filter(
            pk__in=selecionados, ativo=True
        )
        try:
            inventario = iniciar_inventario(
                tenant=tenant,
                descricao=descricao,
                produtos=produtos if selecionados else None,
                usuario=request.user,
            )
            messages.success(request, f"Inventário {inventario.descricao} criado.")
            return redirect(
                "inventory:inventario_detalhe", uuid=inventario.uuid
            )
        except InventarioError as exc:
            messages.error(request, str(exc))
        except Exception as exc:  # full_clean ValidationError
            messages.error(request, f"Dados inválidos: {exc}")

    produtos = Produto.objects.for_tenant(tenant).filter(ativo=True).order_by("nome")
    paginador = Paginator(produtos, 50)
    pagina = paginador.get_page(request.GET.get("page"))
    return render(
        request,
        "inventory/inventario_novo.html",
        {"pagina": pagina},
    )


@login_required
def detalhe(request, uuid):
    tenant = _tenant_atual(request)
    if tenant is None:
        return redirect("dashboard")
    inventario = _obter_inventario(tenant, uuid)
    itens = inventario.itens.select_related("produto")
    return render(
        request,
        "inventory/inventario_detalhe.html",
        {"inventario": inventario, "itens": itens},
    )


@login_required
def contagem(request, uuid):
    tenant = _tenant_atual(request)
    if tenant is None:
        return redirect("dashboard")
    inventario = _obter_inventario(tenant, uuid)

    if request.method == "POST":
        contagens = {}
        for chave, valor in request.POST.items():
            if not chave.startswith("contagem_"):
                continue
            item_uuid = chave.removeprefix("contagem_")
            if valor.strip() == "":
                continue
            try:
                contagens[item_uuid] = valor.replace(",", ".")
            except ValueError:
                messages.error(request, f"Quantidade inválida para {item_uuid}.")
                return redirect("inventory:inventario_contagem", uuid=uuid)
        try:
            registrar_contagem(
                inventario, contagens, usuario=request.user
            )
            messages.success(request, "Contagem registrada.")
            return redirect("inventory:inventario_detalhe", uuid=uuid)
        except InventarioError as exc:
            messages.error(request, str(exc))

    itens = inventario.itens.select_related("produto")
    return render(
        request,
        "inventory/inventario_contagem.html",
        {"inventario": inventario, "itens": itens},
    )


@login_required
def mudar_status(request, uuid, acao):
    """Aplica transição de status via POST (contagem/revisão/cancelar)."""
    tenant = _tenant_atual(request)
    if tenant is None:
        return redirect("dashboard")
    inventario = _obter_inventario(tenant, uuid)

    if request.method != "POST":
        return redirect("inventory:inventario_detalhe", uuid=uuid)

    try:
        if acao == "iniciar-contagem":
            iniciar_contagem(inventario, usuario=request.user)
            messages.success(request, "Inventário em contagem.")
        elif acao == "revisao":
            enviar_para_revisao(inventario, usuario=request.user)
            messages.success(request, "Inventário enviado para revisão.")
        elif acao == "cancelar":
            cancelar(
                inventario,
                usuario=request.user,
                motivo=request.POST.get("motivo", ""),
            )
            messages.success(request, "Inventário cancelado.")
        else:
            messages.error(request, "Ação desconhecida.")
    except InventarioError as exc:
        messages.error(request, str(exc))
    return redirect("inventory:inventario_detalhe", uuid=uuid)


@login_required
def finalizar_view(request, uuid):
    tenant = _tenant_atual(request)
    if tenant is None:
        return redirect("dashboard")
    inventario = _obter_inventario(tenant, uuid)
    if request.method == "POST":
        try:
            finalizar(inventario, usuario=request.user)
            messages.success(request, "Inventário finalizado com ajustes aplicados.")
        except InventarioError as exc:
            messages.error(request, str(exc))
    return redirect("inventory:inventario_detalhe", uuid=uuid)


@login_required
def divergencias(request, uuid):
    """Itens com diferença entre contagem e referência."""
    tenant = _tenant_atual(request)
    if tenant is None:
        return redirect("dashboard")
    inventario = _obter_inventario(tenant, uuid)
    itens = [
        item
        for item in inventario.itens.select_related("produto")
        if item.tem_divergencia
    ]
    return render(
        request,
        "inventory/inventario_divergencias.html",
        {"inventario": inventario, "itens": itens},
    )
