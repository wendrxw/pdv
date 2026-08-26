"""Models do módulo de etiquetas (Elgin L42 Pro Full).

A bobina física tem DUAS etiquetas lado a lado por fileira. O sistema
trata cada fileira como unidade: organiza uma lista linear de etiquetas
e a agrupa em pares; posição ímpar fica vazia (regra fundamental da
task). O servidor NUNCA toca a impressora: gera EtiquetaJobs que o Local
Print Agent (máquina da loja) consome por polling, como os comprovantes.
"""

import uuid
from decimal import Decimal

from django.conf import settings
from django.db import models

from apps.companies.models import Tenant
from apps.core.tenancy import TenantAwareModel

ZERO = Decimal("0")

# Valores de fábrica do rolo padrão da Elgin L42 Pro Full (mm, 203 DPI).
ETIQUETA_PADRAO = {
    "largura_etiqueta": "40",
    "altura_etiqueta": "30",
    "gap_horizontal": "2",
    "gap_vertical": "2",
    "margem_esquerda": "2",
    "margem_superior": "1",
    "offset_horizontal": "0",
    "offset_vertical": "0",
}


class ConfiguracaoEtiqueta(TenantAwareModel):
    """Dimensões e ajustes da impressora de etiquetas por tenant (1:1).

    Valores em milímetros; a conversão para dots (DPI) acontece no agente
    local, que conhece o hardware. Não assumir dimensões: tudo ajustável.
    """

    uuid = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    tenant = models.OneToOneField(
        Tenant, on_delete=models.PROTECT, related_name="configuracao_etiqueta"
    )
    nome_impressora = models.CharField(
        "impressora", max_length=80, default="Elgin L42 Pro Full"
    )
    dpi = models.PositiveIntegerField("DPI", default=203)
    largura_etiqueta = models.DecimalField(
        "largura da etiqueta (mm)",
        max_digits=6,
        decimal_places=1,
        default=Decimal(ETIQUETA_PADRAO["largura_etiqueta"]),
    )
    altura_etiqueta = models.DecimalField(
        "altura da etiqueta (mm)",
        max_digits=6,
        decimal_places=1,
        default=Decimal(ETIQUETA_PADRAO["altura_etiqueta"]),
    )
    gap_horizontal = models.DecimalField(
        "espaço horizontal entre etiquetas (mm)",
        max_digits=6,
        decimal_places=1,
        default=Decimal(ETIQUETA_PADRAO["gap_horizontal"]),
    )
    gap_vertical = models.DecimalField(
        "espaço vertical entre fileiras (mm)",
        max_digits=6,
        decimal_places=1,
        default=Decimal(ETIQUETA_PADRAO["gap_vertical"]),
    )
    margem_esquerda = models.DecimalField(
        "margem esquerda (mm)",
        max_digits=6,
        decimal_places=1,
        default=Decimal(ETIQUETA_PADRAO["margem_esquerda"]),
    )
    margem_superior = models.DecimalField(
        "margem superior (mm)",
        max_digits=6,
        decimal_places=1,
        default=Decimal(ETIQUETA_PADRAO["margem_superior"]),
    )
    offset_horizontal = models.DecimalField(
        "offset horizontal (mm)",
        max_digits=6,
        decimal_places=1,
        default=Decimal(ETIQUETA_PADRAO["offset_horizontal"]),
    )
    offset_vertical = models.DecimalField(
        "offset vertical (mm)",
        max_digits=6,
        decimal_places=1,
        default=Decimal(ETIQUETA_PADRAO["offset_vertical"]),
    )
    mostrar_texto_codigo = models.BooleanField(
        "exibir o valor abaixo do código de barras", default=True
    )
    quantidade_padrao = models.PositiveIntegerField(
        "quantidade padrão de etiquetas", default=1
    )
    data_atualizacao = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "configuração de etiqueta"
        verbose_name_plural = "configurações de etiqueta"

    def __str__(self):
        return f"Etiquetas · {self.tenant}"

    @classmethod
    def carregar(cls, tenant: "Tenant") -> "ConfiguracaoEtiqueta":
        obj, _criado = cls.objects.get_or_create(tenant=tenant)
        return obj

    def dimensoes_mm(self) -> dict:
        """Dicionário com as dimensões (str, para o payload JSON)."""
        return {
            "largura_etiqueta": str(self.largura_etiqueta),
            "altura_etiqueta": str(self.altura_etiqueta),
            "gap_horizontal": str(self.gap_horizontal),
            "gap_vertical": str(self.gap_vertical),
            "margem_esquerda": str(self.margem_esquerda),
            "margem_superior": str(self.margem_superior),
            "offset_horizontal": str(self.offset_horizontal),
            "offset_vertical": str(self.offset_vertical),
            "dpi": self.dpi,
        }


class EtiquetaJob(TenantAwareModel):
    """Trabalho de impressão de etiquetas para o Local Print Agent.

    ``uuid`` é a chave de idempotência (dedupe local no agente). O
    payload guarda as fileiras exatamente como o preview apresentou
    (mesma estrutura usada na tela e na impressão).
    """

    class Status(models.TextChoices):
        PENDING = "PENDING", "Pendente"
        RETRYING = "RETRYING", "Aguardando retry"
        PROCESSING = "PROCESSING", "Imprimindo"
        PRINTED = "PRINTED", "Impresso"
        FAILED = "FAILED", "Falhou"

    uuid = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    tenant = models.ForeignKey(
        Tenant, on_delete=models.PROTECT, related_name="etiqueta_jobs"
    )
    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="etiqueta_jobs",
    )
    estacao = models.ForeignKey(
        "printing.EstacaoImpressao",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="etiqueta_jobs",
        help_text="Estação que assumiu o trabalho.",
    )
    status = models.CharField(
        "status", max_length=12, choices=Status.choices, default=Status.PENDING
    )
    payload = models.JSONField("payload", default=dict)
    tentativa = models.PositiveIntegerField("tentativa", default=0)
    tentativas_maximas = models.PositiveIntegerField("tentativas máximas", default=5)
    erro = models.TextField("erro", blank=True)
    data_criacao = models.DateTimeField(auto_now_add=True)
    data_processamento = models.DateTimeField(null=True, blank=True)
    data_impressao = models.DateTimeField(null=True, blank=True)
    proxima_tentativa = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "trabalho de etiquetas"
        verbose_name_plural = "trabalhos de etiquetas"
        ordering = ["-data_criacao"]
        indexes = [
            models.Index(fields=["tenant", "status"]),
        ]

    def __str__(self):
        return f"EtiquetaJob {self.uuid} · {self.get_status_display()}"
