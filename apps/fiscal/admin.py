from django.contrib import admin

from .models import (
    CertificadoDigital,
    ConfiguracaoFiscal,
    Emitente,
    EventoFiscal,
    NFCe,
)


@admin.register(Emitente)
class EmitenteAdmin(admin.ModelAdmin):
    list_display = ("razao_social", "cnpj", "ie", "crt", "uf")
    search_fields = ("razao_social", "cnpj", "nome_fantasia")
    list_filter = ("uf", "crt")


@admin.register(ConfiguracaoFiscal)
class ConfiguracaoFiscalAdmin(admin.ModelAdmin):
    list_display = ("tenant", "ambiente", "serie", "proximo_numero")
    list_filter = ("ambiente",)
    readonly_fields = ("proximo_numero",)


@admin.register(CertificadoDigital)
class CertificadoDigitalAdmin(admin.ModelAdmin):
    list_display = ("tenant", "validade", "ativo", "data_upload")
    list_filter = ("ativo",)
    readonly_fields = ("data_upload",)

    def save_model(self, request, obj, form, change):
        # Senha do certificado NUNCA é exibida/persistida aqui.
        super().save_model(request, obj, form, change)


@admin.register(NFCe)
class NFCeAdmin(admin.ModelAdmin):
    list_display = (
        "chave_acesso",
        "numero",
        "serie",
        "status",
        "valor_total",
        "data_emissao",
    )
    list_filter = ("status", "serie")
    search_fields = ("chave_acesso", "protocolo")
    readonly_fields = (
        "chave_acesso",
        "dv",
        "status",
        "protocolo",
        "data_autorizacao",
        "valor_total",
        "xml_enviado",
        "xml_assinado",
        "xml_autorizado",
        "codigo_rejeicao",
        "motivo_rejeicao",
        "url_qrcode",
        "tentativas_consulta",
        "data_emissao",
    )


@admin.register(EventoFiscal)
class EventoFiscalAdmin(admin.ModelAdmin):
    list_display = ("tipo", "nfce", "sequencia", "status", "usuario",
                    "data_criacao")
    list_filter = ("tipo", "status")
    search_fields = ("nfce__chave_acesso", "justificativa")
    readonly_fields = ("xml_evento", "protocolo", "codigo_rejeicao",
                       "motivo_rejeicao")
