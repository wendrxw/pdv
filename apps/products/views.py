from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render

from .barcode import BarcodeError, BarcodeRenderer, BarcodeService
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
        form = ProdutoForm(request.POST, request.FILES, tenant=tenant)
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
        form = ProdutoForm(
            request.POST, request.FILES, instance=produto, tenant=tenant
        )
        if form.is_valid():
            try:
                dados = form.cleaned_data.copy()
                if not dados.get("imagem"):
                    dados.pop("imagem", None)
                alterar_produto(produto, usuario=request.user, **dados)
                messages.success(request, f"Produto {produto.nome} atualizado.")
                return redirect("products:detalhe", uuid=produto.uuid)
            except ProductServiceError as exc:
                messages.error(request, str(exc))
    else:
        form = ProdutoForm(instance=produto, tenant=tenant)

    contexto = {"form": form, "produto": produto, "titulo": f"Editar {produto.nome}"}
    try:
        from apps.inventory.services import obter_ou_criar_estoque

        contexto["estoque_atual"] = obter_ou_criar_estoque(produto).quantidade
    except Exception:
        contexto["estoque_atual"] = None
    return render(request, "products/formulario.html", contexto)


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


@login_required
def busca(request):
    """Busca JSON para a listagem (atualiza a tabela sem recarregar).

    Retorna nome, SKU, código de barras e categoria para montar a linha
    da tabela. Isolado por tenant.
    """
    tenant = _tenant_atual(request)
    if tenant is None:
        return JsonResponse({"resultados": []})
    termo = request.GET.get("q", "").strip()
    produtos = buscar_produtos(tenant, termo=termo)[:50]
    resultados = [
        {
            "uuid": str(produto.uuid),
            "nome": produto.nome,
            "sku": produto.sku,
            "codigo_barras": produto.codigo_barras,
            "categoria": produto.categoria.nome if produto.categoria else "",
            "preco_venda": str(produto.preco_venda),
            "ativo": produto.ativo,
        }
        for produto in produtos
    ]
    return JsonResponse({"resultados": resultados})


@login_required
def gerar_codigo_barras(request):
    """Gera um EAN-13 interno candidato para o tenant (POST/JSON).

    O código definitivo é revalidado no backend ao salvar o formulário.
    """
    tenant = _tenant_atual(request)
    if tenant is None:
        return JsonResponse({"erro": "Tenant não disponível."}, status=403)
    if request.method != "POST":
        return JsonResponse({"erro": "Método não permitido."}, status=405)
    codigo = BarcodeService.generate(tenant)
    return JsonResponse({"codigo": codigo})


@login_required
def codigo_barras_svg(request, uuid):
    """Renderiza o código de barras do produto como SVG."""
    tenant = _tenant_atual(request)
    if tenant is None:
        return HttpResponse(status=403)
    produto = get_object_or_404(Produto, tenant=tenant, uuid=uuid)
    try:
        svg = BarcodeRenderer.to_svg(produto.codigo_barras)
    except BarcodeError:
        return HttpResponse(status=404)
    return HttpResponse(svg, content_type="image/svg+xml")
