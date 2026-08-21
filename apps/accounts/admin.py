import django.contrib.admin as admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin

from .models import User


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    list_display = (
        "username",
        "email",
        "first_name",
        "last_name",
        "tenant",
        "is_staff",
        "is_active",
    )
    list_filter = ("is_staff", "is_active", "tenant")
    search_fields = ("username", "first_name", "last_name", "email")
    ordering = ("username",)
    fieldsets = (
        (None, {"fields": ("username", "password")}),
        (
            "Informações pessoais",
            {"fields": ("first_name", "last_name", "email")},
        ),
        (
            "Permissões e tenant",
            {
                "fields": (
                    "tenant",
                    "is_active",
                    "is_staff",
                    "is_superuser",
                    "groups",
                    "user_permissions",
                ),
            },
        ),
        ("Datas importantes", {"fields": ("last_login", "date_joined")}),
    )
    readonly_fields = ("uuid", "last_login", "date_joined")
    list_select_related = ("tenant",)
