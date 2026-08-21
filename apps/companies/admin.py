import django.contrib.admin as admin

from .models import Tenant


@admin.register(Tenant)
class TenantAdmin(admin.ModelAdmin):
    list_display = ("nome", "slug", "status", "data_criacao", "data_atualizacao")
    list_filter = ("status",)
    search_fields = ("nome", "slug")
    ordering = ("nome",)
    readonly_fields = ("uuid", "data_criacao", "data_atualizacao")
    actions = ("ativar_selecionados", "suspender_selecionados", "cancelar_selecionados")

    @admin.action(description="Ativar selecionados")
    def ativar_selecionados(self, request, queryset):
        queryset.update(status=Tenant.Status.ATIVO)

    @admin.action(description="Suspender selecionados")
    def suspender_selecionados(self, request, queryset):
        queryset.update(status=Tenant.Status.SUSPENSO)

    @admin.action(description="Cancelar selecionados")
    def cancelar_selecionados(self, request, queryset):
        queryset.update(status=Tenant.Status.CANCELADO)
