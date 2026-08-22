import django.contrib.admin as admin

from .models import AuditLog


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ("acao", "usuario", "tenant", "entidade", "data")
    list_filter = ("acao", "tenant", "data")
    search_fields = ("acao", "descricao", "usuario__username")
    readonly_fields = (
        "uuid",
        "usuario",
        "tenant",
        "acao",
        "content_type",
        "object_id",
        "entidade",
        "descricao",
        "dados",
        "data",
    )
    date_hierarchy = "data"

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
