from django.contrib import admin

from .models import ConfiguracaoEtiqueta, EtiquetaJob


@admin.register(ConfiguracaoEtiqueta)
class ConfiguracaoEtiquetaAdmin(admin.ModelAdmin):
    list_display = (
        "tenant",
        "nome_impressora",
        "dpi",
        "largura_etiqueta",
        "altura_etiqueta",
        "gap_horizontal",
        "gap_vertical",
        "data_atualizacao",
    )
    list_filter = ("dpi",)
    search_fields = ("tenant__nome", "nome_impressora")


@admin.register(EtiquetaJob)
class EtiquetaJobAdmin(admin.ModelAdmin):
    list_display = (
        "uuid",
        "status",
        "tentativa",
        "estacao",
        "tenant",
        "usuario",
        "data_criacao",
        "data_impressao",
    )
    list_filter = ("status", "tenant")
    search_fields = ("=uuid", "tenant__nome")
    date_hierarchy = "data_criacao"
    readonly_fields = (
        "uuid",
        "tenant",
        "usuario",
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
