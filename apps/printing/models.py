"""Models do módulo de impressão de comprovantes.

O servidor remoto NUNCA toca a impressora física: ele apenas produz
PrintJobs com o snapshot serializável da venda. Quem imprime é o Local
Print Agent, executado na máquina da loja, que faz polling nesta API.

A impressão é OBRIGATÓRIA ao final de cada venda (confirmação do
pagamento): a view de finalização sempre enfileira um PrintJob.

Cada estação (terminal da loja) possui credencial própria; o token é
armazenado apenas como hash bcrypt e nunca é retornado após o pareamento.
"""

import uuid

from django.db import models

from apps.companies.models import Tenant
from apps.core.tenancy import TenantAwareModel


class ConfiguracaoImpressao(TenantAwareModel):
    """Configuração de impressão por tenant (1:1).

    Largura, impressão automática, mensagem final e dados do cabeçalho do
    comprovante. Campos vazios de cabeçalho caem para os dados do Emitente
    fiscal (ou para o nome do tenant) na hora de montar o comprovante.
    """

    class Largura(models.TextChoices):
        MM58 = "58", "58 mm (papel 32 colunas)"
        MM80 = "80", "80 mm (papel 48 colunas)"

    uuid = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    tenant = models.OneToOneField(
        Tenant, on_delete=models.PROTECT, related_name="configuracao_impressao"
    )
    largura = models.CharField(
        "largura do papel",
        max_length=2,
        choices=Largura.choices,
        default=Largura.MM58,
    )
    estacao_padrao = models.ForeignKey(
        "EstacaoImpressao",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        verbose_name="estação padrão",
        help_text=(
            "Estação preferencial para os novos PrintJobs. Vazio permite "
            "que qualquer estação ativa do tenant assuma o trabalho."
        ),
    )
    tentativas_maximas = models.PositiveIntegerField(
        "tentativas máximas",
        default=5,
        help_text="Após esgotar as tentativas o PrintJob vira FAILED.",
    )
    nome_loja = models.CharField("nome da loja", max_length=255, blank=True)
    cnpj = models.CharField("CNPJ", max_length=14, blank=True)
    endereco = models.CharField("endereço", max_length=255, blank=True)
    telefone = models.CharField("telefone", max_length=20, blank=True)
    mensagem_final = models.CharField(
        "mensagem final",
        max_length=120,
        blank=True,
        default="Obrigado pela preferência!",
    )
    data_atualizacao = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "configuração de impressão"
        verbose_name_plural = "configurações de impressão"

    def __str__(self):
        return f"Impressão · {self.tenant}"

    @classmethod
    def carregar(cls, tenant: "Tenant") -> "ConfiguracaoImpressao":
        """Retorna a configuração de impressão do tenant (cria se faltar)."""
        obj, _criado = cls.objects.get_or_create(tenant=tenant)
        return obj


class EstacaoImpressao(TenantAwareModel):
    """Estação/terminal da loja que executa o Local Print Agent.

    A credencial (token) é gerada apenas no pareamento e armazenada como
    hash bcrypt. O código de pareamento é exibido na tela da loja e digitado
    no agente uma única vez.
    """

    class Status(models.TextChoices):
        ATIVA = "ATIVA", "Ativa"
        INATIVA = "INATIVA", "Inativa"

    uuid = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    tenant = models.ForeignKey(
        Tenant, on_delete=models.PROTECT, related_name="estacoes_impressao"
    )
    nome = models.CharField("nome", max_length=120)
    status = models.CharField(
        "status", max_length=10, choices=Status.choices, default=Status.ATIVA
    )
    token_hash = models.CharField("token (hash)", max_length=255, blank=True)
    codigo_pareamento = models.CharField(
        "código de pareamento",
        max_length=6,
        blank=True,
        default="",
        help_text="Uso único: consumido no primeiro pareamento bem-sucedido.",
    )
    ultima_atividade = models.DateTimeField(null=True, blank=True)
    data_pareamento = models.DateTimeField(null=True, blank=True)
    data_criacao = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "estação de impressão"
        verbose_name_plural = "estações de impressão"
        ordering = ["nome"]
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "nome"],
                name="unique_estacao_nome_por_tenant",
            ),
        ]

    def __str__(self):
        return f"{self.nome} · {self.tenant}"

    @property
    def pareada(self):
        return bool(self.token_hash) and self.data_pareamento is not None


class PrintJob(TenantAwareModel):
    """Trabalho de impressão pendente para o Local Print Agent.

    O ``uuid`` é a chave de idempotência: o agente registra localmente os
    jobs já processados e nunca reimprime o mesmo uuid, mesmo que uma
    reconexão entregue o trabalho de novo.
    """

    class Status(models.TextChoices):
        PENDING = "PENDING", "Pendente"
        RETRYING = "RETRYING", "Aguardando retry"
        PROCESSING = "PROCESSING", "Imprimindo"
        PRINTED = "PRINTED", "Impresso"
        FAILED = "FAILED", "Falhou"

    uuid = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    tenant = models.ForeignKey(
        Tenant, on_delete=models.PROTECT, related_name="print_jobs"
    )
    venda = models.ForeignKey(
        "sales.Venda",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="print_jobs",
        help_text="Venda de origem (snapshot fica no payload).",
    )
    estacao = models.ForeignKey(
        EstacaoImpressao,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="print_jobs",
        help_text="Estação que assumiu (ou assumirá) o trabalho.",
    )
    status = models.CharField(
        "status", max_length=12, choices=Status.choices, default=Status.PENDING
    )
    payload = models.JSONField(
        "payload",
        default=dict,
        help_text="Snapshot serializável da venda para o comprovante.",
    )
    tentativa = models.PositiveIntegerField("tentativa", default=0)
    tentativas_maximas = models.PositiveIntegerField("tentativas máximas", default=5)
    erro = models.TextField("erro", blank=True)
    data_criacao = models.DateTimeField(auto_now_add=True)
    data_processamento = models.DateTimeField(null=True, blank=True)
    data_impressao = models.DateTimeField(null=True, blank=True)
    proxima_tentativa = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "trabalho de impressão"
        verbose_name_plural = "trabalhos de impressão"
        ordering = ["-data_criacao"]
        indexes = [
            models.Index(fields=["tenant", "status"]),
            models.Index(fields=["tenant", "venda"]),
            models.Index(fields=["estacao"]),
        ]

    def __str__(self):
        return f"PrintJob {self.uuid} · {self.get_status_display()}"
