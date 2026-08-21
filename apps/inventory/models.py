"""Models de estoque: fornecedores, saldo atual e movimentações.

Regra fundamental (docs/general.md §16): toda alteração de estoque gera
uma MovimentacaoEstoque e passa obrigatoriamente pelo EstoqueService.
Nunca alterar Estoque.quantidade diretamente fora do serviço.
"""

import uuid
from decimal import Decimal

from django.conf import settings
from django.db import models

from apps.companies.models import Tenant
from apps.core.tenancy import TenantAwareModel
from apps.products.models import Produto

ZERO = Decimal("0")


class Fornecedor(TenantAwareModel):
    uuid = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    tenant = models.ForeignKey(
        Tenant,
        on_delete=models.PROTECT,
        related_name="fornecedores",
        verbose_name="tenant",
    )
    razao_social = models.CharField("razão social", max_length=255)
    nome_fantasia = models.CharField("nome fantasia", max_length=255, blank=True)
    documento = models.CharField("CNPJ/CPF", max_length=20, blank=True)
    email = models.EmailField("e-mail", blank=True)
    telefone = models.CharField("telefone", max_length=20, blank=True)
    ativo = models.BooleanField("ativo", default=True)
    observacao = models.TextField("observação", blank=True)
    data_cadastro = models.DateTimeField("criado em", auto_now_add=True)
    data_atualizacao = models.DateTimeField("atualizado em", auto_now=True)

    class Meta:
        verbose_name = "fornecedor"
        verbose_name_plural = "fornecedores"
        ordering = ["razao_social"]
        indexes = [
            models.Index(fields=["tenant", "ativo"]),
        ]

    def __str__(self):
        return self.nome_fantasia or self.razao_social


class Estoque(TenantAwareModel):
    """Saldo atual do produto. Histórico fica em MovimentacaoEstoque."""

    uuid = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    tenant = models.ForeignKey(
        Tenant,
        on_delete=models.PROTECT,
        related_name="estoques",
        verbose_name="tenant",
    )
    produto = models.OneToOneField(
        Produto,
        on_delete=models.PROTECT,
        related_name="estoque",
        verbose_name="produto",
    )
    quantidade = models.DecimalField(
        "quantidade",
        max_digits=12,
        decimal_places=3,
        default=ZERO,
    )
    data_atualizacao = models.DateTimeField("atualizado em", auto_now=True)

    class Meta:
        verbose_name = "estoque"
        verbose_name_plural = "estoques"
        indexes = [
            models.Index(fields=["tenant", "quantidade"]),
        ]

    def __str__(self):
        return f"{self.produto.nome}: {self.quantidade}"

    class Situacao(models.TextChoices):
        SEM_ESTOQUE = "SEM_ESTOQUE", "Sem estoque"
        ESTOQUE_BAIXO = "ESTOQUE_BAIXO", "Estoque baixo"
        EM_ESTOQUE = "EM_ESTOQUE", "Em estoque"

    @property
    def situacao(self):
        """Situação do saldo em relação ao mínimo cadastrado no produto."""
        if self.quantidade <= ZERO:
            return self.Situacao.SEM_ESTOQUE
        if self.quantidade <= self.produto.estoque_minimo:
            return self.Situacao.ESTOQUE_BAIXO
        return self.Situacao.EM_ESTOQUE


class MovimentacaoEstoque(TenantAwareModel):
    """Histórico imutável de alterações de saldo."""

    class Tipo(models.TextChoices):
        ENTRADA = "ENTRADA", "Entrada"
        SAIDA = "SAIDA", "Saída"
        AJUSTE_POSITIVO = "AJUSTE_POSITIVO", "Ajuste positivo"
        AJUSTE_NEGATIVO = "AJUSTE_NEGATIVO", "Ajuste negativo"
        VENDA = "VENDA", "Venda"
        DEVOLUCAO = "DEVOLUCAO", "Devolução"
        CANCELAMENTO_VENDA = "CANCELAMENTO_VENDA", "Cancelamento de venda"
        INVENTARIO = "INVENTARIO", "Inventário"

    uuid = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    tenant = models.ForeignKey(
        Tenant,
        on_delete=models.PROTECT,
        related_name="movimentacoes_estoque",
        verbose_name="tenant",
    )
    produto = models.ForeignKey(
        Produto,
        on_delete=models.PROTECT,
        related_name="movimentacoes",
        verbose_name="produto",
    )
    tipo = models.CharField(
        "tipo",
        max_length=20,
        choices=Tipo.choices,
        db_index=True,
    )
    quantidade = models.DecimalField(
        "quantidade",
        max_digits=12,
        decimal_places=3,
        help_text="Sempre positiva; o sentido vem do tipo.",
    )
    saldo_anterior = models.DecimalField(
        "saldo anterior", max_digits=12, decimal_places=3
    )
    saldo_posterior = models.DecimalField(
        "saldo posterior", max_digits=12, decimal_places=3
    )
    custo_unitario = models.DecimalField(
        "custo unitário",
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
    )
    fornecedor = models.ForeignKey(
        Fornecedor,
        on_delete=models.SET_NULL,
        related_name="movimentacoes",
        null=True,
        blank=True,
        verbose_name="fornecedor",
    )
    motivo = models.CharField("motivo", max_length=200, blank=True)
    referencia = models.CharField("referência", max_length=100, blank=True)
    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="movimentacoes_estoque",
        null=True,
        blank=True,
        verbose_name="usuário",
    )
    data_criacao = models.DateTimeField("criada em", auto_now_add=True)

    class Meta:
        verbose_name = "movimentação de estoque"
        verbose_name_plural = "movimentações de estoque"
        ordering = ["-data_criacao"]
        indexes = [
            models.Index(fields=["tenant", "produto", "-data_criacao"]),
            models.Index(fields=["tenant", "-data_criacao"]),
        ]

    def __str__(self):
        return f"{self.get_tipo_display()} {self.quantidade} — {self.produto.nome}"
