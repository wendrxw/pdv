"""Tenant: ambiente isolado utilizado por um cliente da plataforma.

Não confundir Tenant com Cliente da plataforma (apps.clients) nem com
Usuário (apps.accounts). Um cliente pode possuir um tenant; o tenant é o
ambiente operacional isolado onde vivem produtos, estoque, financeiro etc.
"""

import uuid

from django.db import models
from django.utils.text import slugify


class Tenant(models.Model):
    class Status(models.TextChoices):
        PENDENTE = "PENDENTE", "Pendente"
        ATIVO = "ATIVO", "Ativo"
        SUSPENSO = "SUSPENSO", "Suspenso"
        CANCELADO = "CANCELADO", "Cancelado"

    uuid = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    nome = models.CharField("nome", max_length=255)
    slug = models.SlugField("slug", max_length=255, unique=True, blank=True)
    status = models.CharField(
        "status",
        max_length=20,
        choices=Status.choices,
        default=Status.PENDENTE,
        db_index=True,
    )
    observacao = models.TextField("observação", blank=True)
    permitir_estoque_negativo = models.BooleanField(
        "permitir estoque negativo",
        default=False,
        help_text=(
            "Quando desabilitado, saídas que deixarem o saldo negativo "
            "são rejeitadas com erro de domínio."
        ),
    )
    data_criacao = models.DateTimeField("criado em", auto_now_add=True)
    data_atualizacao = models.DateTimeField("atualizado em", auto_now=True)

    class Meta:
        verbose_name = "tenant"
        verbose_name_plural = "tenants"
        ordering = ["nome"]

    def __str__(self):
        return self.nome

    def save(self, *args, **kwargs):
        if not self.slug:
            base_slug = slugify(self.nome)[:240] or "tenant"
            slug = base_slug
            counter = 1
            while Tenant.objects.filter(slug=slug).exclude(pk=self.pk).exists():
                counter += 1
                slug = f"{base_slug}-{counter}"
            self.slug = slug
        super().save(*args, **kwargs)

    @property
    def is_operacional(self):
        """Indica se o tenant pode operar normalmente."""
        return self.status == self.Status.ATIVO
