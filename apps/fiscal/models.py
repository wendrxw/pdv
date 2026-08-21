"""Models do módulo fiscal NFC-e (SEFAZ-SP, homologação).

Status fiscal NUNCA se mistura com status da venda (apps.sales). O resto
do sistema só fala com o módulo através de FiscalService (service.py).
"""

import uuid

from django.conf import settings
from django.db import models
from django.db.models import Q

from apps.companies.models import Tenant
from apps.core.tenancy import TenantAwareModel


class Emitente(TenantAwareModel):
    """Estabelecimento emissor (1:1 com tenant)."""

    class Crt(models.TextChoices):
        SIMPLES_NACIONAL = "1", "Simples Nacional (CSOSN)"
        SIMPLES_EXCESSO = "2", "Simples Nacional — excesso de sublimite"
        REGIME_NORMAL = "3", "Regime normal (CST)"

    uuid = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    tenant = models.OneToOneField(
        Tenant, on_delete=models.PROTECT, related_name="emitente"
    )
    cnpj = models.CharField("CNPJ", max_length=14)
    razao_social = models.CharField("razão social", max_length=120)
    nome_fantasia = models.CharField("nome fantasia", max_length=120, blank=True)
    ie = models.CharField("inscrição estadual", max_length=20)
    crt = models.CharField(
        "CRT", max_length=1, choices=Crt.choices, default=Crt.SIMPLES_NACIONAL
    )
    x_lgr = models.CharField("logradouro", max_length=60)
    nro = models.CharField("número", max_length=60)
    x_cpl = models.CharField("complemento", max_length=60, blank=True)
    x_bairro = models.CharField("bairro", max_length=60)
    codigo_municipio_ibge = models.CharField("código IBGE do município", max_length=7)
    x_municipio = models.CharField("município", max_length=60)
    uf = models.CharField("UF", max_length=2, default="SP")
    cep = models.CharField("CEP", max_length=8)
    fone = models.CharField("telefone", max_length=12, blank=True)
    data_cadastro = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "emitente"
        verbose_name_plural = "emitentes"

    def __str__(self):
        return self.razao_social


class ConfiguracaoFiscal(TenantAwareModel):
    """Configuração fiscal por tenant (1:1). Série/numeração ficam aqui e
    são reservadas sob lock na emissão."""

    class Ambiente(models.TextChoices):
        HOMOLOGACAO = "HOMOLOGACAO", "Homologação"
        PRODUCAO = "PRODUCAO", "Produção"

    uuid = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    tenant = models.OneToOneField(
        Tenant, on_delete=models.PROTECT, related_name="configuracao_fiscal"
    )
    ambiente = models.CharField(
        "ambiente",
        max_length=15,
        choices=Ambiente.choices,
        default=Ambiente.HOMOLOGACAO,
    )
    serie = models.PositiveIntegerField("série NFC-e", default=1)
    proximo_numero = models.PositiveIntegerField("próximo número", default=1)
    token_csc = models.CharField(
        "token CSC", max_length=64, blank=True
    )
    id_csc = models.CharField("identificador CSC", max_length=6, blank=True)
    data_atualizacao = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "configuração fiscal"
        verbose_name_plural = "configurações fiscais"

    def __str__(self):
        return f"{self.tenant} · {self.get_ambiente_display()}"

    @classmethod
    def carregar(cls, tenant: "Tenant") -> "ConfiguracaoFiscal":
        """Retorna a configuração fiscal do tenant (cria se faltar)."""
        obj, _criado = cls.objects.get_or_create(tenant=tenant)
        return obj


class CertificadoDigital(TenantAwareModel):
    """Certificado A1 do emitente.

    A senha vive APENAS em env (`SEFAZ_CERTIFICATE_PASSWORD`) — nunca no
    banco, nunca em logs. Upload é privado (media protegida fora de /static).
    """

    uuid = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    tenant = models.ForeignKey(
        Tenant, on_delete=models.PROTECT, related_name="certificados_digitais"
    )
    arquivo = models.FileField(upload_to="fiscal/certificados/%Y/%m/")
    validade = models.DateField("validade")
    ativo = models.BooleanField(default=True)
    data_upload = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "certificado digital"
        verbose_name_plural = "certificados digitais"

    def __str__(self):
        return f"Certificado {self.tenant} · válido até {self.validade}"

    @classmethod
    def pegar_ativo(cls, tenant: "Tenant") -> "CertificadoDigital | None":
        """Certificado ativo mais recente do tenant (nome evita colisão
        com o campo BooleanField `ativo`)."""
        return (
            cls.objects.for_tenant(tenant)
            .filter(ativo=True)
            .order_by("-data_upload")
            .first()
        )


class NFCe(TenantAwareModel):
    """Documento fiscal eletrônico modelo 65.

    Ciclo de vida: PENDENTE → GERADA → ASSINADA → TRANSMITINDO →
    AUTORIZADA | REJEITADA | DENEGADA; pós-eventos: CANCELADA.
    CONTINGENCIA_INATIVO indica que a modalidade está desligada nesta fase.
    """

    class Status(models.TextChoices):
        PENDENTE = "PENDENTE", "Pendente"
        GERADA = "GERADA", "XML gerado"
        ASSINADA = "ASSINADA", "Assinada"
        TRANSMITINDO = "TRANSMITINDO", "Transmitindo"
        AUTORIZADA = "AUTORIZADA", "Autorizada"
        REJEITADA = "REJEITADA", "Rejeitada"
        CANCELADA = "CANCELADA", "Cancelada"
        DENEGADA = "DENEGADA", "Denegada"
        CONTINGENCIA_INATIVO = "CONTINGENCIA_INATIVO", "Contingência inativa"

    # Status que ainda podem evoluir; usados para garantir UMA nota
    # "viva" por venda (idempotência).
    STATUS_ATIVOS = [
        Status.PENDENTE,
        Status.GERADA,
        Status.ASSINADA,
        Status.TRANSMITINDO,
    ]

    uuid = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    tenant = models.ForeignKey(
        Tenant, on_delete=models.PROTECT, related_name="nfces"
    )
    venda = models.ForeignKey(
        "sales.Venda",
        on_delete=models.PROTECT,
        related_name="nfces",
        null=True,
        blank=True,
        help_text="Emissão avulsa futura pode não ter venda.",
    )
    numero = models.PositiveIntegerField()
    serie = models.PositiveIntegerField(default=1)
    chave_acesso = models.CharField(max_length=44, unique=True, db_index=True)
    dv = models.PositiveSmallIntegerField()
    status = models.CharField(
        max_length=25, choices=Status.choices, default=Status.PENDENTE
    )
    protocolo = models.CharField(max_length=20, blank=True)
    data_autorizacao = models.DateTimeField(null=True, blank=True)
    valor_total = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    xml_enviado = models.TextField(blank=True)
    xml_assinado = models.TextField(blank=True)
    xml_autorizado = models.TextField(blank=True)
    codigo_rejeicao = models.CharField(max_length=4, blank=True)
    motivo_rejeicao = models.CharField(max_length=255, blank=True)
    url_qrcode = models.URLField("URL do QR Code", max_length=600, blank=True)
    tentativas_consulta = models.PositiveIntegerField(default=0)
    data_emissao = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "NFC-e"
        verbose_name_plural = "NFC-es"
        ordering = ["-data_emissao"]
        constraints = [
            models.UniqueConstraint(
                fields=["venda"],
                condition=Q(status__in=[
                    "PENDENTE",
                    "GERADA",
                    "ASSINADA",
                    "TRANSMITINDO",
                ]),
                name="unique_nfce_ativa_por_venda",
            ),
        ]
        indexes = [
            models.Index(
                fields=["tenant", "status"], name="nfce_tenant_status_idx"
            ),
        ]

    def __str__(self):
        return f"NFC-e {self.serie}/{self.numero} · {self.status}"


class EventoFiscal(TenantAwareModel):
    """Eventos sobre NFC-e: cancelamento, inutilização etc."""

    class Tipo(models.TextChoices):
        CANCELAMENTO = "CANCELAMENTO", "Cancelamento"
        INUTILIZACAO = "INUTILIZACAO", "Inutilização"

    class Status(models.TextChoices):
        ENVIADO = "ENVIADO", "Enviado"
        HOMOLOGADO = "HOMOLOGADO", "Homologado"
        REJEITADO = "REJEITADO", "Rejeitado"

    uuid = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    tenant = models.ForeignKey(
        Tenant, on_delete=models.PROTECT, related_name="eventos_fiscais"
    )
    nfce = models.ForeignKey(
        NFCe,
        on_delete=models.PROTECT,
        related_name="eventos",
        null=True,
        blank=True,
        help_text="Inutilização não referencia uma NFC-e específica.",
    )
    tipo = models.CharField(max_length=15, choices=Tipo.choices)
    sequencia = models.PositiveSmallIntegerField(default=1)
    justificativa = models.CharField(max_length=255)
    xml_evento = models.TextField(blank=True)
    protocolo = models.CharField(max_length=20, blank=True)
    status = models.CharField(
        max_length=10, choices=Status.choices, default=Status.ENVIADO
    )
    codigo_rejeicao = models.CharField(max_length=4, blank=True)
    motivo_rejeicao = models.CharField(max_length=255, blank=True)
    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        on_delete=models.SET_NULL,
        related_name="eventos_fiscais",
    )
    data_criacao = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "evento fiscal"
        verbose_name_plural = "eventos fiscais"
        ordering = ["-data_criacao"]

    def __str__(self):
        return f"{self.tipo} · {self.nfce or '—'} · {self.status}"
