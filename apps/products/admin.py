from django.contrib import admin

from .models import Categoria, Marca, Produto
from .services import desativar_produto, reativar_produto


@admin.register(Categoria)
class CategoriaAdmin(admin.ModelAdmin):
    list_display = ("nome", "tenant", "ativo", "data_cadastro")
    list_filter = ("tenant", "ativo")
    search_fields = ("nome",)
    ordering = ("nome",)


@admin.register(Marca)
class MarcaAdmin(admin.ModelAdmin):
    list_display = ("nome", "tenant", "ativo", "data_cadastro")
    list_filter = ("tenant", "ativo")
    search_fields = ("nome",)
    ordering = ("nome",)


@admin.action(description="Desativar selecionados")
def desativar_produtos(modeladmin, request, queryset):
    for produto in queryset.filter(ativo=True):
        desativar_produto(produto, usuario=request.user)


@admin.action(description="Reativar selecionados")
def reativar_produtos(modeladmin, request, queryset):
    for produto in queryset.filter(ativo=False):
        reativar_produto(produto, usuario=request.user)


@admin.register(Produto)
class ProdutoAdmin(admin.ModelAdmin):
    list_display = (
        "nome",
        "sku",
        "tenant",
        "categoria",
        "marca",
        "unidade_medida",
        "ncm",
        "preco_venda",
        "ativo",
        "data_cadastro",
    )
    list_filter = ("tenant", "ativo", "categoria", "marca", "unidade_medida")
    search_fields = ("nome", "sku", "codigo_barras", "ncm", "uuid")
    ordering = ("nome",)
    readonly_fields = ("uuid", "data_cadastro", "data_atualizacao")
    actions = [desativar_produtos, reativar_produtos]
