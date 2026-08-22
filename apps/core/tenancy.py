"""Infraestrutura de multi-tenancy do projeto.

Regra fundamental: todo dado operacional pertence a um tenant e um tenant
nunca acessa dados de outro. O isolamento é garantido no backend, através
de querysets que exigem o tenant atual.
"""

from django.db import models


class TenantQuerySet(models.QuerySet):
    """QuerySet com filtros obrigatórios de tenant."""

    def for_tenant(self, tenant):
        return self.filter(tenant=tenant)


class TenantManager(models.Manager.from_queryset(TenantQuerySet)):
    """Manager padrão de models tenant-aware."""


class TenantAwareModel(models.Model):
    """Base abstrata para models que pertencem a um tenant.

    Todo model operacional do sistema deve herdar desta base, garantindo:
    - vínculo obrigatório com o tenant;
    - manager com filtro por tenant disponível em todos os herdeiros.
    """

    objects = TenantManager()

    class Meta:
        abstract = True
        base_manager_name = "objects"

    def get_tenant(self):
        return self.tenant
