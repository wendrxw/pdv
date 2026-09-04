from django.contrib import admin

from .models import ConfiguracaoImpressao, EstacaoImpressao, PrintJob


@admin.register(ConfiguracaoImpressao)
class ConfiguracaoImpressaoAdmin(admin.ModelAdmin):
    list_display = (
        "tenant",
        "largura",
        "impressora_fiscal",
        "estacao_padrao",
        "tentativas_maximas",
        "data_atualizacao",
    )
    list_filter = ("largura",)
    search_fields = ("tenant__nome", "nome_loja", "cnpj", "impressora_fiscal")


@admin.register(EstacaoImpressao)
class EstacaoImpressaoAdmin(admin.ModelAdmin):
    list_display = (
        "nome",
        "tenant",
        "status",
        "pareada",
        "ultima_atividade",
        "data_pareamento",
    )
    list_filter = ("status",)
    search_fields = ("nome", "tenant__nome")
    readonly_fields = (
        "token_hash",
        "codigo_pareamento",
        "ultima_atividade",
        "data_pareamento",
    )

    def has_add_permission(self, request):
        return False


@admin.register(PrintJob)
class PrintJobAdmin(admin.ModelAdmin):
    list_display = (
        "uuid",
        "status",
        "tentativa",
        "venda",
        "estacao",
        "tenant",
        "data_criacao",
        "data_impressao",
    )
    list_filter = ("status", "tenant")
    search_fields = ("=uuid", "=venda__numero", "tenant__nome")
    date_hierarchy = "data_criacao"
    readonly_fields = (
        "uuid",
        "tenant",
        "venda",
        "estacao",
        "status",
        "payload",
        "tentativa",
        "tentativas_maximas",
        "erro",
        "data_criacao",
        "data_processamento",
        "data_impressao",
        "proxima_tentativa",
    )

    def has_add_permission(self, request):
        return False
