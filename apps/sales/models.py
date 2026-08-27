"""Models de vendas e caixa do PDV.

O caixa é a unidade operacional: toda venda pertence a um caixa aberto.
Itens congelam o preço no momento da venda. Status da venda nunca se
mistura com status fiscal (módulo fiscal separado).
"""

import uuid
from decimal import Decimal

from django.conf import settings
from django.db import models

from apps.companies.models import Tenant
from apps.core.tenancy import TenantAwareModel

ZERO = Decimal("0.00")


class Caixa(TenantAwareModel):
    class Status(models.TextChoices):
        ABERTO = "ABERTO", "Aberto"
        FECHADO = "FECHADO", "Fechado"

    uuid = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    tenant = models.ForeignKey(
        Tenant, on_delete=models.PROTECT, related_name="caixas"
    )
    operador = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="caixas_operados",
    )
    conta_financeira = models.ForeignKey(
        "financial.ContaFinanceira",
        on_delete=models.PROTECT,
        related_name="caixas_pdv",
        help_text="Conta onde entradas, suprimentos e sangrias são lançados.",
    )
    status = models.CharField(
        max_length=10, choices=Status.choices, default=Status.ABERTO
    )
    saldo_inicial = models.DecimalField(
        max_digits=14, decimal_places=2, default=ZERO
    )
    saldo_final_esperado = models.DecimalField(
        max_digits=14, decimal_places=2, null=True, blank=True
    )
    saldo_final_informado = models.DecimalField(
        max_digits=14, decimal_places=2, null=True, blank=True
    )
    observacao_fechamento = models.TextField(blank=True)
    data_abertura = models.DateTimeField(auto_now_add=True)
    data_fechamento = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "caixa"
        ordering = ["-data_abertura"]
        indexes = [
            models.Index(fields=["tenant", "status"]),
        ]

    @property
    def diferenca(self):
        if self.saldo_final_esperado is None or self.saldo_final_informado is None:
            return None
        return self.saldo_final_informado - self.saldo_final_esperado

    def __str__(self):
        return f"Caixa {self.uuid} · {self.get_status_display()}"


class MovimentacaoCaixa(TenantAwareModel):
    """Suprimentos e sangrias durante o turno."""

    class Tipo(models.TextChoices):
        SUPRIMENTO = "SUPRIMENTO", "Suprimento"
        SANGRIA = "SANGRIA", "Sangria"

    uuid = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    tenant = models.ForeignKey(
        Tenant, on_delete=models.PROTECT, related_name="movimentacoes_caixa"
    )
    caixa = models.ForeignKey(
        Caixa, on_delete=models.CASCADE, related_name="movimentacoes"
    )
    tipo = models.CharField(max_length=12, choices=Tipo.choices)
    valor = models.DecimalField(max_digits=14, decimal_places=2)
    motivo = models.CharField(max_length=255, blank=True)
    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        on_delete=models.SET_NULL,
        related_name="movimentacoes_caixa_pdv",
    )
    data_criacao = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "movimentação de caixa"
        verbose_name_plural = "movimentações de caixa"
        ordering = ["data_criacao"]


class Venda(TenantAwareModel):
    class Status(models.TextChoices):
        ABERTA = "ABERTA", "Aberta"
        FINALIZADA = "FINALIZADA", "Finalizada"
        CANCELADA = "CANCELADA", "Cancelada"

    uuid = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    tenant = models.ForeignKey(
        Tenant, on_delete=models.PROTECT, related_name="vendas"
    )
    numero = models.PositiveIntegerField()
    caixa = models.ForeignKey(
        Caixa, on_delete=models.PROTECT, related_name="vendas"
    )
    operador = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        on_delete=models.SET_NULL,
        related_name="vendas_realizadas",
    )
    cliente = models.ForeignKey(
        "customers.Cliente",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="vendas",
        help_text="Cliente cadastrado associado à venda (opcional).",
    )
    cliente_nome = models.CharField(
        max_length=200,
        blank=True,
        help_text="Nome do cliente congelado no momento da venda.",
    )
    status = models.CharField(
        max_length=10, choices=Status.choices, default=Status.ABERTA
    )
    subtotal = models.DecimalField(max_digits=14, decimal_places=2, default=ZERO)
    desconto = models.DecimalField(max_digits=14, decimal_places=2, default=ZERO)
    total = models.DecimalField(max_digits=14, decimal_places=2, default=ZERO)
    observacao = models.TextField(blank=True)
    data_abertura = models.DateTimeField(auto_now_add=True)
    data_finalizacao = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "venda"
        ordering = ["-data_abertura"]
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "numero"],
                name="unique_venda_numero_per_tenant",
            ),
        ]
        indexes = [
            models.Index(fields=["tenant", "status"]),
        ]

    def __str__(self):
        return f"Venda {self.numero} · {self.total}"


class ItemVenda(TenantAwareModel):
    uuid = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    tenant = models.ForeignKey(
        Tenant, on_delete=models.PROTECT, related_name="itens_venda"
    )
    venda = models.ForeignKey(Venda, on_delete=models.CASCADE, related_name="itens")
    produto = models.ForeignKey(
        "products.Produto", on_delete=models.PROTECT, related_name="itens_venda"
    )
    quantidade = models.DecimalField(max_digits=12, decimal_places=3)
    preco_unitario = models.DecimalField(max_digits=14, decimal_places=2)
    subtotal = models.DecimalField(max_digits=14, decimal_places=2)
    data_criacao = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "item de venda"
        verbose_name_plural = "itens de venda"
        ordering = ["data_criacao"]
        constraints = [
            models.UniqueConstraint(
                fields=["venda", "produto"],
                name="unique_item_produto_por_venda",
            ),
            models.CheckConstraint(
                condition=models.Q(quantidade__gt=0),
                name="item_venda_quantidade_positiva",
            ),
        ]

    def __str__(self):
        return f"{self.produto} × {self.quantidade}"


class PagamentoVenda(TenantAwareModel):
    uuid = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    tenant = models.ForeignKey(
        Tenant, on_delete=models.PROTECT, related_name="pagamentos_venda"
    )
    venda = models.ForeignKey(
        Venda, on_delete=models.CASCADE, related_name="pagamentos"
    )
    forma_pagamento = models.ForeignKey(
        "financial.FormaPagamento",
        on_delete=models.PROTECT,
        related_name="pagamentos_venda",
    )
    valor = models.DecimalField(max_digits=14, decimal_places=2)
    valor_bruto = models.DecimalField(max_digits=14, decimal_places=2, default=ZERO)
    taxa = models.DecimalField(max_digits=14, decimal_places=2, default=ZERO)
    valor_liquido = models.DecimalField(max_digits=14, decimal_places=2, default=ZERO)
    data_criacao = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "pagamento de venda"
        verbose_name_plural = "pagamentos de venda"
        ordering = ["data_criacao"]
