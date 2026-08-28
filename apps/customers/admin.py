from django.contrib import admin

from .models import Cliente
from .services import desativar_cliente, reativar_cliente


@admin.action(description="Desativar selecionados")
def desativar_clientes(modeladmin, request, queryset):
    for cliente in queryset.filter(ativo=True):
        desativar_cliente(cliente, usuario=request.user)


@admin.action(description="Reativar selecionados")
def reativar_clientes(modeladmin, request, queryset):
    for cliente in queryset.filter(ativo=False):
        reativar_cliente(cliente, usuario=request.user)


@admin.register(Cliente)
class ClienteAdmin(admin.ModelAdmin):
    list_display = (
        "nome",
        "cpf_cnpj",
        "email",
        "telefone",
        "cidade",
        "estado",
        "tenant",
        "ativo",
        "data_cadastro",
    )
    list_filter = ("tenant", "ativo", "estado")
    search_fields = ("nome", "cpf_cnpj", "email", "telefone", "uuid")
    ordering = ("nome",)
    readonly_fields = ("uuid", "data_cadastro", "data_atualizacao")
    actions = [desativar_clientes, reativar_clientes]
