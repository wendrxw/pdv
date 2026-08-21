from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404, redirect, render

from .forms import ProdutoForm
from .models import Categoria, Marca, Produto
from .services import (
    ProductServiceError,
    alterar_produto,
    buscar_produtos,
    criar_produto,
    desativar_produto,
    reativar_produto,
)

PRODUTOS_POR_PAGINA = 25


def _tenant_atual(request):
    """Retorna o tenant do usuário ou redireciona para o dashboard."""
    tenant = request.user.get_tenant()
    if tenant is None:
        messages.info(
            request,
            "Usuário da plataforma não possui tenant para operar produtos.",
        )
        return None
    return tenant


@login_required
def lista(request):
    tenant = _tenant_atual(request)
    if tenant is None:
        return redirect("dashboard")

    termo = request.GET.get("q", "").strip()
    categoria_id = request.GET.get("categoria", "")
    marca_id = request.GET.get("marca", "")
    status = request.GET.get("status", "")

    queryset = buscar_produtos(
        tenant,
        termo=termo,
        categoria=categoria_id or None,
        marca=marca_id or None,
        status=status,
    )
    paginador = Paginator(queryset, PRODUTOS_POR_PAGINA)
    pagina = paginador.get_page(request.GET.get("page"))

    contexto = {
        "pagina": pagina,
        "termo": termo,
        "status": status,
        "categorias": Categoria.objects.for_tenant(tenant).filter(ativo=True),
        "marcas": Marca.objects.for_tenant(tenant).filter(ativo=True),
        "categoria_selecionada": categoria_id,
        "marca_selecionada": marca_id,
    }
    return render(request, "products/lista.html", contexto)


@login_required
def novo(request):
    tenant = _tenant_atual(request)
    if tenant is None:
        return redirect("dashboard")

    if request.method == "POST":
        form = ProdutoForm(request.POST, tenant=tenant)
        if form.is_valid():
            try:
                produto = criar_produto(
                    tenant=tenant, usuario=request.user, **form.cleaned_data
                )
                messages.success(request, f"Produto {produto.nome} criado.")
                return redirect("products:detalhe", uuid=produto.uuid)
            except ProductServiceError as exc:
                messages.error(request, str(exc))
    else:
        form = ProdutoForm(tenant=tenant)
    return render(
        request,
        "products/formulario.html",
        {"form": form, "titulo": "Novo produto"},
    )


@login_required
def detalhe(request, uuid):
    tenant = _tenant_atual(request)
    if tenant is None:
        return redirect("dashboard")
    produto = get_object_or_404(Produto, tenant=tenant, uuid=uuid)
    return render(request, "products/detalhe.html", {"produto": produto})


@login_required
def editar(request, uuid):
    tenant = _tenant_atual(request)
    if tenant is None:
        return redirect("dashboard")
    produto = get_object_or_404(Produto, tenant=tenant, uuid=uuid)

    if request.method == "POST":
        form = ProdutoForm(request.POST, instance=produto, tenant=tenant)
        if form.is_valid():
            try:
                alterar_produto(
                    produto, usuario=request.user, **form.cleaned_data
                )
                messages.success(request, f"Produto {produto.nome} atualizado.")
                return redirect("products:detalhe", uuid=produto.uuid)
            except ProductServiceError as exc:
                messages.error(request, str(exc))
    else:
        form = ProdutoForm(instance=produto, tenant=tenant)
    return render(
        request,
        "products/formulario.html",
        {"form": form, "produto": produto, "titulo": f"Editar {produto.nome}"},
    )


@login_required
def alternar_status(request, uuid):
    """Ativa/desativa conforme estado atual (POST apenas)."""
    tenant = _tenant_atual(request)
    if tenant is None:
        return redirect("dashboard")
    produto = get_object_or_404(Produto, tenant=tenant, uuid=uuid)
    if request.method == "POST":
        if produto.ativo:
            desativar_produto(produto, usuario=request.user)
            messages.success(request, f"Produto {produto.nome} desativado.")
        else:
            reativar_produto(produto, usuario=request.user)
            messages.success(request, f"Produto {produto.nome} reativado.")
    return redirect("products:detalhe", uuid=produto.uuid)
