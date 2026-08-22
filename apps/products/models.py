"""Models do módulo de produtos.

Todos os models herdam de TenantAwareModel: os dados pertencem a um tenant
e o isolamento é garantido no backend. SKU e nome de categoria são únicos
dentro do tenant — nunca globalmente.
"""

import uuid
from decimal import Decimal

from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import Q

from apps.companies.models import Tenant
from apps.core.tenancy import TenantAwareModel

ZERO = Decimal("0")


class Categoria(TenantAwareModel):
    uuid = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    tenant = models.ForeignKey(
        Tenant,
        on_delete=models.PROTECT,
        related_name="categorias",
        verbose_name="tenant",
    )
    nome = models.CharField("nome", max_length=100)
    descricao = models.TextField("descrição", blank=True)
    ativo = models.BooleanField("ativo", default=True, db_index=True)
    data_cadastro = models.DateTimeField("criado em", auto_now_add=True)
    data_atualizacao = models.DateTimeField("atualizado em", auto_now=True)

    class Meta:
        verbose_name = "categoria"
        verbose_name_plural = "categorias"
        ordering = ["nome"]
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "nome"],
                name="unique_categoria_nome_per_tenant",
            ),
        ]
        indexes = [
            models.Index(fields=["tenant", "ativo"]),
        ]

    def __str__(self):
        return self.nome


class Marca(TenantAwareModel):
    uuid = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    tenant = models.ForeignKey(
        Tenant,
        on_delete=models.PROTECT,
        related_name="marcas",
        verbose_name="tenant",
    )
    nome = models.CharField("nome", max_length=100)
    ativo = models.BooleanField("ativo", default=True, db_index=True)
    data_cadastro = models.DateTimeField("criado em", auto_now_add=True)
    data_atualizacao = models.DateTimeField("atualizado em", auto_now=True)

    class Meta:
        verbose_name = "marca"
        verbose_name_plural = "marcas"
        ordering = ["nome"]
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "nome"],
                name="unique_marca_nome_per_tenant",
            ),
        ]
        indexes = [
            models.Index(fields=["tenant", "ativo"]),
        ]

    def __str__(self):
        return self.nome


class Produto(TenantAwareModel):
    """Produto cadastrado pelo tenant.

    Identificadores distintos (docs/general.md §7):
    - uuid: identificador técnico global;
    - sku: código interno/comercial, único dentro do tenant;
    - codigo_barras: código de leitura no PDV (implementado na task de
      barcode), único dentro do tenant.
    """

    class UnidadeMedida(models.TextChoices):
        UN = "UN", "Unidade"
        KG = "KG", "Quilograma"
        G = "G", "Gramas"
        L = "L", "Litros"
        ML = "ML", "Mililitros"
        CX = "CX", "Caixa"
        PCT = "PCT", "Pacote"

    uuid = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    tenant = models.ForeignKey(
        Tenant,
        on_delete=models.PROTECT,
        related_name="produtos",
        verbose_name="tenant",
    )
    nome = models.CharField("nome", max_length=200)
    sku = models.CharField("SKU", max_length=60, blank=True)
    codigo_barras = models.CharField(
        "código de barras",
        max_length=13,
        blank=True,
        help_text=(
            "EAN-13. Códigos gerados pelo sistema usam o prefixo 2 "
            "(faixa interna de uso da loja), não são GTIN registrados."
        ),
    )
    descricao = models.TextField("descrição", blank=True)
    tamanho = models.CharField("tamanho", max_length=50, blank=True)
    unidade_medida = models.CharField(
        "unidade de medida",
        max_length=3,
        choices=UnidadeMedida.choices,
        default=UnidadeMedida.UN,
    )
    categoria = models.ForeignKey(
        Categoria,
        on_delete=models.SET_NULL,
        related_name="produtos",
        null=True,
        blank=True,
        verbose_name="categoria",
    )
    marca = models.ForeignKey(
        Marca,
        on_delete=models.SET_NULL,
        related_name="produtos",
        null=True,
        blank=True,
        verbose_name="marca",
    )
    preco_custo = models.DecimalField(
        "preço de custo",
        max_digits=12,
        decimal_places=2,
        default=ZERO,
        validators=[MinValueValidator(ZERO)],
    )
    preco_venda = models.DecimalField(
        "preço de venda",
        max_digits=12,
        decimal_places=2,
        default=ZERO,
        validators=[MinValueValidator(ZERO)],
    )
    estoque_minimo = models.DecimalField(
        "estoque mínimo",
        max_digits=12,
        decimal_places=3,
        default=ZERO,
        validators=[MinValueValidator(ZERO)],
    )
    estoque_maximo = models.DecimalField(
        "estoque máximo",
        max_digits=12,
        decimal_places=3,
        null=True,
        blank=True,
        validators=[MinValueValidator(ZERO)],
    )
    ativo = models.BooleanField("ativo", default=True, db_index=True)
    observacao = models.TextField("observação", blank=True)
    data_cadastro = models.DateTimeField("criado em", auto_now_add=True)
    data_atualizacao = models.DateTimeField("atualizado em", auto_now=True)

    class Meta:
        verbose_name = "produto"
        verbose_name_plural = "produtos"
        ordering = ["nome"]
        constraints = [
            # SKU é opcional; quando informado, é único dentro do tenant.
            models.UniqueConstraint(
                fields=["tenant", "sku"],
                condition=~Q(sku=""),
                name="unique_produto_sku_per_tenant",
            ),
            # Código de barras opcional; único dentro do tenant quando
            # informado. Não reutilizado após exclusão lógica (a constraint
            # considera todos os produtos, ativos ou não).
            models.UniqueConstraint(
                fields=["tenant", "codigo_barras"],
                condition=~Q(codigo_barras=""),
                name="unique_produto_codigo_barras_per_tenant",
            ),
        ]
        indexes = [
            models.Index(fields=["tenant", "nome"]),
            models.Index(fields=["tenant", "ativo"]),
            models.Index(fields=["tenant", "codigo_barras"]),
        ]

    def __str__(self):
        return self.nome
