"""Auditoria básica de operações importantes.

Registra quem fez o quê, quando e sobre qual entidade, preservando
histórico para operações críticas (ativação, suspensão, cancelamento,
operações financeiras futuras etc.).
"""

import uuid

from django.conf import settings
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db import models


class AuditLog(models.Model):
    uuid = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="registros_auditoria",
        verbose_name="usuário",
    )
    tenant = models.ForeignKey(
        "companies.Tenant",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="registros_auditoria",
        verbose_name="tenant",
    )
    acao = models.CharField("ação", max_length=100)
    content_type = models.ForeignKey(
        ContentType,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    object_id = models.CharField(max_length=64, blank=True)
    entidade = GenericForeignKey("content_type", "object_id")
    descricao = models.TextField("descrição", blank=True)
    dados = models.JSONField("dados adicionais", default=dict, blank=True)
    data = models.DateTimeField("data", auto_now_add=True, db_index=True)

    class Meta:
        verbose_name = "registro de auditoria"
        verbose_name_plural = "registros de auditoria"
        ordering = ["-data"]

    def __str__(self):
        return f"{self.acao} — {self.data:%d/%m/%Y %H:%M}"


def registrar(
    acao,
    entidade=None,
    usuario=None,
    tenant=None,
    descricao="",
    dados=None,
):
    """Registra uma entrada de auditoria.

    Nunca deve interromper a operação principal por falha de auditoria.
    """
    try:
        AuditLog.objects.create(
            usuario=usuario,
            tenant=tenant,
            acao=acao,
            entidade=entidade,
            descricao=descricao,
            dados=dados or {},
        )
    except Exception:  # noqa: BLE001 - auditoria não pode quebrar a operação
        import logging

        logging.getLogger("pdv.audit").exception(
            "Falha ao registrar auditoria: %s", acao
        )
