from django.contrib import admin

from .models import (
    CategoriaFinanceira,
    ContaFinanceira,
    ContaReceber,
    Entrada,
    FormaPagamento,
    MovimentacaoFinanceira,
    ParcelaReceber,
    Saida,
)


@admin.register(CategoriaFinanceira)
class CategoriaFinanceiraAdmin(admin.ModelAdmin):
    list_display = ("nome", "tipo", "categoria_pai", "ativo", "tenant")
    list_filter = ("tipo", "ativo")
    search_fields = ("nome",)
    autocomplete_fields = ("categoria_pai",)


@admin.register(ContaFinanceira)
class ContaFinanceiraAdmin(admin.ModelAdmin):
    list_display = (
        "nome",
        "tipo",
        "saldo_atual",
        "permitir_saldo_negativo",
        "ativo",
        "tenant",
    )
    list_filter = ("tipo", "ativo")
    search_fields = ("nome",)
    readonly_fields = ("saldo_atual", "data_cadastro")


@admin.register(FormaPagamento)
class FormaPagamentoAdmin(admin.ModelAdmin):
    list_display = (
        "nome",
        "codigo",
        "taxa_percentual",
        "gera_conta_receber",
        "ativo",
        "tenant",
    )
    list_filter = ("codigo", "gera_conta_receber", "ativo")


class ParcelaInline(admin.TabularInline):
    model = ParcelaReceber
    extra = 0
    readonly_fields = ("status", "data_recebimento", "conta_financeira")


@admin.register(ContaReceber)
class ContaReceberAdmin(admin.ModelAdmin):
    list_display = (
        "descricao",
        "cliente_nome",
        "valor_total",
        "status",
        "origem",
        "tenant",
    )
    list_filter = ("status", "origem")
    search_fields = ("descricao", "cliente_nome")
    inlines = [ParcelaInline]


class EntradaAdmin(admin.ModelAdmin):
    list_display = (
        "descricao",
        "valor",
        "status",
        "conta_financeira",
        "data_competencia",
        "data_recebimento",
        "tenant",
    )
    list_filter = ("status",)
    search_fields = ("descricao",)
    date_hierarchy = "data_competencia"
    readonly_fields = ("status", "data_recebimento")


admin.site.register(Entrada, EntradaAdmin)


class SaidaAdmin(admin.ModelAdmin):
    list_display = (
        "descricao",
        "valor",
        "status",
        "vencida",
        "conta_financeira",
        "data_vencimento",
        "data_pagamento",
        "tenant",
    )
    list_filter = ("status",)
    search_fields = ("descricao",)
    date_hierarchy = "data_vencimento"
    readonly_fields = ("status", "data_pagamento")


admin.site.register(Saida, SaidaAdmin)


@admin.register(ParcelaReceber)
class ParcelaReceberAdmin(admin.ModelAdmin):
    list_display = (
        "conta_receber",
        "numero",
        "valor",
        "data_vencimento",
        "status",
        "vencida",
        "tenant",
    )
    list_filter = ("status",)
    readonly_fields = ("status", "data_recebimento", "conta_financeira")


@admin.register(MovimentacaoFinanceira)
class MovimentacaoFinanceiraAdmin(admin.ModelAdmin):
    list_display = (
        "data",
        "tipo",
        "valor",
        "conta_financeira",
        "origem",
        "descricao",
        "usuario",
        "tenant",
    )
    list_filter = ("tipo", "origem")
    search_fields = ("descricao",)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
