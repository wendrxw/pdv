"""Views do módulo de clientes do tenant."""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404, redirect, render

from .forms import ClienteForm
from .models import Cliente
from .services import (
    CustomerError,
    alterar_cliente,
    buscar_clientes,
    criar_cliente,
    desativar_cliente,
    reativar_cliente,
)

CLIENTES_POR_PAGINA = 25


def _tenant_atual(request):
    tenant = request.user.get_tenant()
    if tenant is None:
        messages.info(
            request,
            "Usuário da plataforma não possui tenant para operar clientes.",
        )
        return None
    return tenant


@login_required
def lista(request):
    tenant = _tenant_atual(request)
    if tenant is None:
        return redirect("dashboard")

    termo = request.GET.get("q", "").strip()
    status = request.GET.get("status", "")
    queryset = buscar_clientes(tenant, termo=termo, status=status)
    paginador = Paginator(queryset, CLIENTES_POR_PAGINA)
    pagina = paginador.get_page(request.GET.get("page"))
    return render(
        request,
        "customers/lista.html",
        {"pagina": pagina, "termo": termo, "status": status},
    )


@login_required
def novo(request):
    tenant = _tenant_atual(request)
    if tenant is None:
        return redirect("dashboard")

    if request.method == "POST":
        form = ClienteForm(request.POST)
        if form.is_valid():
            try:
                cliente = criar_cliente(
                    tenant=tenant, usuario=request.user, **form.cleaned_data
                )
                messages.success(request, f"Cliente {cliente.nome} criado.")
                return redirect("customers:detalhe", uuid=cliente.uuid)
            except CustomerError as exc:
                messages.error(request, str(exc))
    else:
        form = ClienteForm()
    return render(
        request,
        "customers/formulario.html",
        {"form": form, "titulo": "Novo cliente"},
    )


@login_required
def detalhe(request, uuid):
    tenant = _tenant_atual(request)
    if tenant is None:
        return redirect("dashboard")
    cliente = get_object_or_404(Cliente, tenant=tenant, uuid=uuid)
    return render(request, "customers/detalhe.html", {"cliente": cliente})


@login_required
def editar(request, uuid):
    tenant = _tenant_atual(request)
    if tenant is None:
        return redirect("dashboard")
    cliente = get_object_or_404(Cliente, tenant=tenant, uuid=uuid)

    if request.method == "POST":
        form = ClienteForm(request.POST, instance=cliente)
        if form.is_valid():
            try:
                alterar_cliente(cliente, usuario=request.user, **form.cleaned_data)
                messages.success(request, f"Cliente {cliente.nome} atualizado.")
                return redirect("customers:detalhe", uuid=cliente.uuid)
            except CustomerError as exc:
                messages.error(request, str(exc))
    else:
        form = ClienteForm(instance=cliente)
    return render(
        request,
        "customers/formulario.html",
        {"form": form, "cliente": cliente, "titulo": f"Editar {cliente.nome}"},
    )


@login_required
def alternar_status(request, uuid):
    """Ativa/desativa conforme estado atual (POST apenas)."""
    tenant = _tenant_atual(request)
    if tenant is None:
        return redirect("dashboard")
    cliente = get_object_or_404(Cliente, tenant=tenant, uuid=uuid)
    if request.method == "POST":
        if cliente.ativo:
            desativar_cliente(cliente, usuario=request.user)
            messages.success(request, f"Cliente {cliente.nome} desativado.")
        else:
            reativar_cliente(cliente, usuario=request.user)
            messages.success(request, f"Cliente {cliente.nome} reativado.")
    return redirect("customers:detalhe", uuid=cliente.uuid)
