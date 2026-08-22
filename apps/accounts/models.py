"""Usuários do sistema.

Dois contextos distintos:
- Usuário de plataforma (equipe administradora): is_staff=True, sem tenant.
- Usuário de tenant: vinculado obrigatoriamente a um tenant.

O tenant do usuário é a fonte de verdade para o isolamento multi-tenant.
Nunca confiar em parâmetros enviados pelo frontend.
"""

import uuid

from django.contrib.auth.models import AbstractUser
from django.contrib.auth.models import UserManager as DjangoUserManager
from django.db import models

from apps.core.tenancy import TenantQuerySet


class UserManager(DjangoUserManager.from_queryset(TenantQuerySet)):
    """Manager padrão com métodos de queryset tenant-aware."""


class User(AbstractUser):
    uuid = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    tenant = models.ForeignKey(
        "companies.Tenant",
        on_delete=models.PROTECT,
        related_name="usuarios",
        null=True,
        blank=True,
        verbose_name="tenant",
        help_text=(
            "Tenant do usuário. Equipe da plataforma não possui tenant "
            "(acesso global via Django Admin)."
        ),
    )
    data_criacao = models.DateTimeField("criado em", auto_now_add=True)
    data_atualizacao = models.DateTimeField("atualizado em", auto_now=True)

    class Meta:
        verbose_name = "usuário"
        verbose_name_plural = "usuários"
        indexes = [
            models.Index(fields=["tenant", "username"]),
        ]

    objects = UserManager()

    def __str__(self):
        return self.get_full_name() or self.username

    @property
    def is_plataforma(self):
        """Indica se é usuário da equipe administradora da plataforma."""
        return self.is_staff and self.tenant_id is None

    def get_tenant(self):
        """Retorna o tenant do usuário ou None para equipe da plataforma."""
        return self.tenant
