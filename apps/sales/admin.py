from django.contrib import admin

from .models import (
    Caixa,
    ItemVenda,
    MovimentacaoCaixa,
    PagamentoVenda,
    Venda,
)


class ItemVendaInline(admin.TabularInline):
    model = ItemVenda
    extra = 0
    readonly_fields = ("produto", "quantidade", "preco_unitario", "subtotal")


class PagamentoVendaInline(admin.TabularInline):
    model = PagamentoVenda
    extra = 0
    readonly_fields = ("forma_pagamento", "valor")


@admin.register(Venda)
class VendaAdmin(admin.ModelAdmin):
    list_display = (
        "numero",
        "status",
        "subtotal",
        "desconto",
        "total",
        "caixa",
        "operador",
        "cliente_nome",
        "data_abertura",
        "tenant",
    )
    list_filter = ("status",)
    search_fields = ("cliente_nome", "=caixa__uuid")
    date_hierarchy = "data_abertura"
    readonly_fields = (
        "numero",
        "subtotal",
        "desconto",
        "total",
        "data_finalizacao",
    )
    inlines = [ItemVendaInline, PagamentoVendaInline]


class MovimentacaoCaixaInline(admin.TabularInline):
    model = MovimentacaoCaixa
    extra = 0
    readonly_fields = ("tipo", "valor", "motivo", "usuario", "data_criacao")

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Caixa)
class CaixaAdmin(admin.ModelAdmin):
    list_display = (
        "data_abertura",
        "operador",
        "status",
        "saldo_inicial",
        "saldo_final_esperado",
        "saldo_final_informado",
        "tenant",
    )
    list_filter = ("status",)
    inlines = [MovimentacaoCaixaInline]


@admin.register(MovimentacaoCaixa)
class MovimentacaoCaixaAdmin(admin.ModelAdmin):
    list_display = (
        "tipo",
        "valor",
        "motivo",
        "caixa",
        "usuario",
        "data_criacao",
        "tenant",
    )
    list_filter = ("tipo",)

    def has_change_permission(self, request, obj=None):
        return False
