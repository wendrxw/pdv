from django.contrib import admin

from .models import Estoque, Fornecedor, MovimentacaoEstoque


@admin.register(Fornecedor)
class FornecedorAdmin(admin.ModelAdmin):
    list_display = (
        "razao_social",
        "nome_fantasia",
        "tenant",
        "documento",
        "telefone",
        "ativo",
    )
    list_filter = ("tenant", "ativo")
    search_fields = ("razao_social", "nome_fantasia", "documento")
    ordering = ("razao_social",)


@admin.register(Estoque)
class EstoqueAdmin(admin.ModelAdmin):
    list_display = (
        "produto",
        "tenant",
        "quantidade",
        "situacao",
        "data_atualizacao",
    )
    list_filter = ("tenant",)
    search_fields = ("produto__nome", "produto__sku")
    readonly_fields = ("uuid", "data_atualizacao")


@admin.register(MovimentacaoEstoque)
class MovimentacaoEstoqueAdmin(admin.ModelAdmin):
    list_display = (
        "produto",
        "tenant",
        "tipo",
        "quantidade",
        "saldo_anterior",
        "saldo_posterior",
        "usuario",
        "data_criacao",
    )
    list_filter = ("tenant", "tipo", "data_criacao")
    search_fields = ("produto__nome", "produto__sku", "referencia", "motivo")
    readonly_fields = [f.name for f in MovimentacaoEstoque._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
