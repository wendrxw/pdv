"""Models do módulo financeiro.

Regras fundamentais (docs/general.md §67): nunca alterar saldo sem a
movimentação correspondente; nunca excluir operação que já ocorreu
(cancelamento lógico + estorno); competência ≠ caixa.
"""

import uuid
from decimal import Decimal

from django.conf import settings
from django.db import models

from apps.companies.models import Tenant
from apps.core.tenancy import TenantAwareModel

ZERO = Decimal("0.00")


class CategoriaFinanceira(TenantAwareModel):
    class Tipo(models.TextChoices):
        ENTRADA = "ENTRADA", "Entrada"
        SAIDA = "SAIDA", "Saída"
        AMBOS = "AMBOS", "Ambos"

    uuid = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    tenant = models.ForeignKey(
        Tenant, on_delete=models.PROTECT, related_name="categorias_financeiras"
    )
    nome = models.CharField(max_length=120)
    tipo = models.CharField(max_length=10, choices=Tipo.choices)
    categoria_pai = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="subcategorias",
    )
    descricao = models.CharField(max_length=255, blank=True)
    ativo = models.BooleanField(default=True)
    data_cadastro = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "categoria financeira"
        verbose_name_plural = "categorias financeiras"
        ordering = ["nome"]
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "nome"],
                condition=models.Q(categoria_pai__isnull=True),
                name="unique_categoria_raiz_per_tenant",
            ),
        ]
        indexes = [
            models.Index(fields=["tenant", "tipo"]),
        ]

    def __str__(self):
        return self.nome


class ContaFinanceira(TenantAwareModel):
    """Onde o dinheiro está. Saldo só muda via MovimentacaoFinanceira."""

    class Tipo(models.TextChoices):
        CAIXA = "CAIXA", "Caixa"
        CONTA_BANCARIA = "CONTA_BANCARIA", "Conta bancária"
        CARTEIRA = "CARTEIRA", "Carteira"
        PIX = "PIX", "PIX"
        OUTRO = "OUTRO", "Outro"

    uuid = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    tenant = models.ForeignKey(
        Tenant, on_delete=models.PROTECT, related_name="contas_financeiras"
    )
    nome = models.CharField(max_length=120)
    tipo = models.CharField(max_length=20, choices=Tipo.choices)
    saldo_inicial = models.DecimalField(
        max_digits=14, decimal_places=2, default=ZERO
    )
    saldo_atual = models.DecimalField(
        max_digits=14, decimal_places=2, default=ZERO
    )
    permitir_saldo_negativo = models.BooleanField(default=False)
    ativo = models.BooleanField(default=True)
    data_cadastro = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "conta financeira"
        verbose_name_plural = "contas financeiras"
        ordering = ["nome"]
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "nome"],
                name="unique_conta_financeira_per_tenant",
            ),
        ]

    def __str__(self):
        return self.nome


class FormaPagamento(TenantAwareModel):
    class Codigo(models.TextChoices):
        DINHEIRO = "DINHEIRO", "Dinheiro"
        PIX = "PIX", "PIX"
        DEBITO = "DEBITO", "Débito"
        CREDITO = "CREDITO", "Crédito"
        BOLETO = "BOLETO", "Boleto"
        TRANSFERENCIA = "TRANSFERENCIA", "Transferência"
        OUTRO = "OUTRO", "Outro"

    uuid = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    tenant = models.ForeignKey(
        Tenant, on_delete=models.PROTECT, related_name="formas_pagamento"
    )
    nome = models.CharField(max_length=120)
    codigo = models.CharField(max_length=20, choices=Codigo.choices)
    taxa_percentual = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=ZERO,
        help_text="Preparado para taxas de cartão (bruto/taxa/líquido).",
    )
    gera_conta_receber = models.BooleanField(
        default=False,
        help_text="Fiado/crediário: gera conta a receber em vez de "
        "entrada imediata.",
    )
    ativo = models.BooleanField(default=True)

    class Meta:
        verbose_name = "forma de pagamento"
        verbose_name_plural = "formas de pagamento"
        ordering = ["nome"]
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "codigo"],
                name="unique_forma_pagamento_per_tenant",
            ),
        ]

    def __str__(self):
        return self.nome


class Entrada(TenantAwareModel):
    class Status(models.TextChoices):
        PREVISTA = "PREVISTA", "Prevista"
        PENDENTE = "PENDENTE", "Pendente"
        RECEBIDA = "RECEBIDA", "Recebida"
        CANCELADA = "CANCELADA", "Cancelada"

    uuid = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    tenant = models.ForeignKey(
        Tenant, on_delete=models.PROTECT, related_name="entradas"
    )
    descricao = models.CharField(max_length=200)
    valor = models.DecimalField(max_digits=14, decimal_places=2)
    categoria = models.ForeignKey(
        CategoriaFinanceira,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="entradas",
    )
    conta_financeira = models.ForeignKey(
        ContaFinanceira, on_delete=models.PROTECT, related_name="entradas"
    )
    forma_pagamento = models.ForeignKey(
        FormaPagamento,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="entradas",
    )
    data_competencia = models.DateField()
    data_prevista = models.DateField(null=True, blank=True)
    data_recebimento = models.DateField(null=True, blank=True)
    status = models.CharField(
        max_length=12, choices=Status.choices, default=Status.PENDENTE
    )
    observacao = models.TextField(blank=True)
    usuario_criacao = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        on_delete=models.SET_NULL,
        related_name="entradas_criadas",
    )
    data_criacao = models.DateTimeField(auto_now_add=True)
    data_atualizacao = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "entrada"
        ordering = ["-data_competencia", "-data_criacao"]
        indexes = [
            models.Index(fields=["tenant", "status"]),
            models.Index(fields=["tenant", "data_competencia"]),
        ]

    def __str__(self):
        return f"{self.descricao} — {self.valor}"


class Saida(TenantAwareModel):
    class Status(models.TextChoices):
        PREVISTA = "PREVISTA", "Prevista"
        PENDENTE = "PENDENTE", "Pendente"
        PAGA = "PAGA", "Paga"
        CANCELADA = "CANCELADA", "Cancelada"

    uuid = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    tenant = models.ForeignKey(Tenant, on_delete=models.PROTECT, related_name="saidas")
    descricao = models.CharField(max_length=200)
    valor = models.DecimalField(max_digits=14, decimal_places=2)
    categoria = models.ForeignKey(
        CategoriaFinanceira,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="saidas",
    )
    conta_financeira = models.ForeignKey(
        ContaFinanceira, on_delete=models.PROTECT, related_name="saidas"
    )
    data_competencia = models.DateField()
    data_vencimento = models.DateField()
    data_pagamento = models.DateField(null=True, blank=True)
    status = models.CharField(
        max_length=12, choices=Status.choices, default=Status.PENDENTE
    )
    observacao = models.TextField(blank=True)
    usuario_criacao = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        on_delete=models.SET_NULL,
        related_name="saidas_criadas",
    )
    data_criacao = models.DateTimeField(auto_now_add=True)
    data_atualizacao = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "saída"
        ordering = ["-data_vencimento", "-data_criacao"]
        indexes = [
            models.Index(fields=["tenant", "status"]),
            models.Index(fields=["tenant", "data_vencimento"]),
        ]

    @property
    def vencida(self):
        from django.utils import timezone

        return (
            self.status == self.Status.PENDENTE
            and self.data_vencimento < timezone.localdate()
        )

    def __str__(self):
        return f"{self.descricao} — {self.valor}"


class ContaReceber(TenantAwareModel):
    """Direito de recebimento (ex.: venda fiado parcelada)."""

    class Origem(models.TextChoices):
        MANUAL = "MANUAL", "Manual"
        VENDA = "VENDA", "Venda"
        OUTRO = "OUTRO", "Outro"

    class Status(models.TextChoices):
        ABERTA = "ABERTA", "Aberta"
        PARCIAL = "PARCIAL", "Parcialmente recebida"
        RECEBIDA = "RECEBIDA", "Recebida"
        CANCELADA = "CANCELADA", "Cancelada"

    uuid = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    tenant = models.ForeignKey(
        Tenant, on_delete=models.PROTECT, related_name="contas_receber"
    )
    cliente_nome = models.CharField(max_length=200, blank=True)
    descricao = models.CharField(max_length=200)
    valor_total = models.DecimalField(max_digits=14, decimal_places=2)
    data_competencia = models.DateField()
    origem = models.CharField(
        max_length=10, choices=Origem.choices, default=Origem.MANUAL
    )
    referencia_uuid = models.UUIDField(null=True, blank=True)
    status = models.CharField(
        max_length=10, choices=Status.choices, default=Status.ABERTA
    )
    observacao = models.TextField(blank=True)
    data_criacao = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "conta a receber"
        verbose_name_plural = "contas a receber"
        ordering = ["-data_competencia"]
        indexes = [
            models.Index(fields=["tenant", "status"]),
        ]

    @property
    def valor_recebido(self) -> Decimal:
        return (
            self.parcelas.filter(status=ParcelaReceber.Status.RECEBIDA).aggregate(
                total=models.Sum("valor")
            )["total"]
            or ZERO
        )

    @property
    def valor_pendente(self) -> Decimal:
        return self.valor_total - self.valor_recebido

    def __str__(self):
        return f"{self.descricao} — {self.valor_total}"


class ParcelaReceber(TenantAwareModel):
    class Status(models.TextChoices):
        PENDENTE = "PENDENTE", "Pendente"
        RECEBIDA = "RECEBIDA", "Recebida"
        CANCELADA = "CANCELADA", "Cancelada"

    uuid = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    tenant = models.ForeignKey(
        Tenant, on_delete=models.PROTECT, related_name="parcelas_receber"
    )
    conta_receber = models.ForeignKey(
        ContaReceber, on_delete=models.CASCADE, related_name="parcelas"
    )
    numero = models.PositiveIntegerField()
    valor = models.DecimalField(max_digits=14, decimal_places=2)
    data_vencimento = models.DateField()
    data_recebimento = models.DateField(null=True, blank=True)
    status = models.CharField(
        max_length=10, choices=Status.choices, default=Status.PENDENTE
    )
    conta_financeira = models.ForeignKey(
        ContaFinanceira,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="parcelas_recebidas",
    )
    observacao = models.CharField(max_length=255, blank=True)

    class Meta:
        verbose_name = "parcela a receber"
        verbose_name_plural = "parcelas a receber"
        ordering = ["conta_receber", "numero"]
        constraints = [
            models.UniqueConstraint(
                fields=["conta_receber", "numero"],
                name="unique_parcela_numero_por_conta",
            ),
        ]
        indexes = [
            models.Index(fields=["tenant", "status"]),
            models.Index(fields=["tenant", "data_vencimento"]),
        ]

    @property
    def vencida(self):
        from django.utils import timezone

        return (
            self.status == self.Status.PENDENTE
            and self.data_vencimento < timezone.localdate()
        )

    def __str__(self):
        return f"{self.conta_receber} · parcela {self.numero} — {self.valor}"


class MovimentacaoFinanceira(TenantAwareModel):
    """Movimento efetivo de caixa/conta — fonte auditável do saldo."""

    class Tipo(models.TextChoices):
        ENTRADA = "ENTRADA", "Entrada"
        SAIDA = "SAIDA", "Saída"
        ESTORNO_ENTRADA = "ESTORNO_ENTRADA", "Estorno de entrada"
        ESTORNO_SAIDA = "ESTORNO_SAIDA", "Estorno de saída"

    class Origem(models.TextChoices):
        ENTRADA = "ENTRADA", "Entrada avulsa"
        SAIDA = "SAIDA", "Saída avulsa"
        PARCELA = "PARCELA", "Parcela a receber"
        VENDA = "VENDA", "Venda do PDV"
        SUPRIMENTO = "SUPRIMENTO", "Suprimento de caixa"
        SANGRIA = "SANGRIA", "Sangria de caixa"
        ABERTURA_CAIXA = "ABERTURA_CAIXA", "Abertura de caixa"
        MANUAL = "MANUAL", "Manual"

    uuid = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    tenant = models.ForeignKey(
        Tenant, on_delete=models.PROTECT, related_name="movimentacoes_financeiras"
    )
    conta_financeira = models.ForeignKey(
        ContaFinanceira, on_delete=models.PROTECT, related_name="movimentacoes"
    )
    tipo = models.CharField(max_length=20, choices=Tipo.choices)
    valor = models.DecimalField(max_digits=14, decimal_places=2)
    data = models.DateField()
    origem = models.CharField(max_length=20, choices=Origem.choices)
    referencia_uuid = models.UUIDField(null=True, blank=True)
    estorno_de = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="estornos",
    )
    descricao = models.CharField(max_length=255, blank=True)
    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        on_delete=models.SET_NULL,
        related_name="movimentacoes_financeiras",
    )
    data_criacao = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "movimentação financeira"
        verbose_name_plural = "movimentações financeiras"
        ordering = ["-data", "-data_criacao"]
        indexes = [
            models.Index(fields=["tenant", "data"]),
            models.Index(fields=["conta_financeira", "data"]),
        ]

    def __str__(self):
        return f"{self.get_tipo_display()} {self.valor} · {self.conta_financeira}"
