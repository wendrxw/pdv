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


def _caminho_imagem_produto(instance, filename):
    """Imagem do produto isolada por tenant no armazenamento."""
    return f"produtos/{instance.tenant_id}/{instance.uuid}/{filename}"


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
    codigo = models.CharField(
        "código",
        max_length=20,
        blank=True,
        help_text="Código interno gerado automaticamente pelo sistema.",
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
    ncm = models.CharField(
        "NCM",
        max_length=8,
        blank=True,
        help_text="Nomenclatura Comum do Mercosul (8 dígitos).",
    )
    cest = models.CharField(
        "CEST",
        max_length=7,
        blank=True,
        help_text="Código Especificador da Substituição Tributária (7 dígitos).",
    )
    cfop = models.CharField(
        "CFOP",
        max_length=4,
        blank=True,
        help_text="Código Fiscal de Operações e Prestações (4 dígitos).",
    )
    origem = models.CharField(
        "origem da mercadoria",
        max_length=1,
        choices=[
            ("0", "0 — Nacional"),
            ("1", "1 — Estrangeira — importação direta"),
            ("2", "2 — Estrangeira — adquirida no mercado interno"),
            ("3", "3 — Nacional — conteúdo de importação superior a 40%"),
            ("4", "4 — Nacional — produção conforme processos básicos"),
            ("5", "5 — Nacional — conteúdo de importação inferior a 40%"),
            ("6", "6 — Estrangeira — importação direta sem similar nacional"),
            ("7", "7 — Estrangeira — mercado interno sem similar nacional"),
            ("8", "8 — Nacional — conteúdo de importação superior a 70%"),
        ],
        default="0",
        blank=True,
    )
    imagem = models.FileField(
        "imagem do produto",
        upload_to=_caminho_imagem_produto,
        blank=True,
        help_text="PNG, JPG ou WEBP até 2MB.",
    )
    data_cadastro = models.DateTimeField("criado em", auto_now_add=True)
    data_atualizacao = models.DateTimeField("atualizado em", auto_now=True)

    class Meta:
        verbose_name = "produto"
        verbose_name_plural = "produtos"
        ordering = ["nome"]
        constraints = [
            # Código interno é opcional; quando informado, é único dentro do
            # tenant.
            models.UniqueConstraint(
                fields=["tenant", "codigo"],
                condition=~Q(codigo=""),
                name="unique_produto_codigo_per_tenant",
            ),
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
            models.Index(fields=["tenant", "codigo"]),
        ]

    def __str__(self):
        return self.nome

    @property
    def margem_lucro(self):
        """Margem sobre o preço de venda, em percentual (calculada)."""
        if not self.preco_venda or self.preco_venda <= ZERO:
            return ZERO
        return (
            (self.preco_venda - self.preco_custo)
            / self.preco_venda
            * Decimal("100")
        ).quantize(Decimal("0.01"))
