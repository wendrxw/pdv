"""Clientes da plataforma (SaaS).

IMPORTANTE: "Cliente" aqui é a pessoa/empresa que contrata o sistema.
Não confundir com consumidor final de uma loja (futuro módulo de clientes
do PDV) nem com Tenant (apps.companies).

Fluxo comercial:
    contato → lead → cadastro → aprovação → criação do tenant → convite.
"""

import uuid

from django.conf import settings
from django.db import models

from apps.core.validators import only_digits, validate_cpf_cnpj


def normalizar_documento(value):
    """Normaliza CPF/CNPJ para apenas dígitos e valida."""
    return validate_cpf_cnpj(value)


class ClientePlataforma(models.Model):
    class TipoPessoa(models.TextChoices):
        PF = "PF", "Pessoa física"
        PJ = "PJ", "Pessoa jurídica"

    class Status(models.TextChoices):
        LEAD = "LEAD", "Lead"
        EM_ANALISE = "EM_ANALISE", "Em análise"
        PENDENTE = "PENDENTE", "Pendente"
        ATIVO = "ATIVO", "Ativo"
        SUSPENSO = "SUSPENSO", "Suspenso"
        CANCELADO = "CANCELADO", "Cancelado"

    class Origem(models.TextChoices):
        SITE = "SITE", "Site"
        TELEFONE = "TELEFONE", "Telefone"
        WHATSAPP = "WHATSAPP", "WhatsApp"
        INDICACAO = "INDICACAO", "Indicação"
        PRESENCIAL = "PRESENCIAL", "Presencial"
        OUTRO = "OUTRO", "Outro"

    uuid = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    tipo_pessoa = models.CharField(
        "tipo de pessoa",
        max_length=2,
        choices=TipoPessoa.choices,
        default=TipoPessoa.PJ,
    )
    nome = models.CharField("nome", max_length=255)
    razao_social = models.CharField("razão social", max_length=255, blank=True)
    nome_fantasia = models.CharField("nome fantasia", max_length=255, blank=True)
    cpf_cnpj = models.CharField(
        "CPF/CNPJ",
        max_length=14,
        unique=True,
        null=True,
        blank=True,
        help_text=(
            "Armazenado apenas com dígitos. Opcional durante o onboarding "
            "(ex.: conversão de lead); obrigatório para ativação."
        ),
    )
    email = models.EmailField("e-mail")
    telefone_celular = models.CharField("telefone celular", max_length=20)
    origem = models.CharField(
        "origem",
        max_length=20,
        choices=Origem.choices,
        default=Origem.OUTRO,
    )
    status = models.CharField(
        "status",
        max_length=20,
        choices=Status.choices,
        default=Status.LEAD,
        db_index=True,
    )
    observacao = models.TextField("observação", blank=True)

    # Endereço (opcional no onboarding inicial)
    cep = models.CharField("CEP", max_length=9, blank=True)
    logradouro = models.CharField("logradouro", max_length=255, blank=True)
    numero = models.CharField("número", max_length=20, blank=True)
    complemento = models.CharField("complemento", max_length=255, blank=True)
    bairro = models.CharField("bairro", max_length=120, blank=True)
    cidade = models.CharField("cidade", max_length=120, blank=True)
    estado = models.CharField("estado (UF)", max_length=2, blank=True)

    usuario_responsavel = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="clientes_responsavel",
        verbose_name="responsável",
    )

    data_cadastro = models.DateTimeField("cadastrado em", auto_now_add=True)
    data_atualizacao = models.DateTimeField("atualizado em", auto_now=True)

    class Meta:
        verbose_name = "cliente da plataforma"
        verbose_name_plural = "clientes da plataforma"
        ordering = ["-data_cadastro"]
        indexes = [
            models.Index(fields=["status", "data_cadastro"]),
            models.Index(fields=["email"]),
        ]

    def __str__(self):
        return self.nome

    def save(self, *args, **kwargs):
        # Normalizações garantidas no backend, independentemente da origem.
        if self.cpf_cnpj:
            self.cpf_cnpj = only_digits(self.cpf_cnpj)
        self.email = self.email.strip().lower()
        super().save(*args, **kwargs)


class ClienteHistorico(models.Model):
    class Acao(models.TextChoices):
        CRIADO = "CRIADO", "Criado"
        ATUALIZADO = "ATUALIZADO", "Atualizado"
        STATUS_ALTERADO = "STATUS_ALTERADO", "Status alterado"
        TENANT_ASSOCIADO = "TENANT_ASSOCIADO", "Tenant associado"
        ONBOARDING_INICIADO = "ONBOARDING_INICIADO", "Onboarding iniciado"

    uuid = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    cliente = models.ForeignKey(
        ClientePlataforma,
        on_delete=models.CASCADE,
        related_name="historico",
        verbose_name="cliente",
    )
    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="historico_clientes",
        verbose_name="usuário",
    )
    acao = models.CharField("ação", max_length=40, choices=Acao.choices)
    status_anterior = models.CharField("status anterior", max_length=20, blank=True)
    status_novo = models.CharField("status novo", max_length=20, blank=True)
    descricao = models.TextField("descrição", blank=True)
    data = models.DateTimeField("data", auto_now_add=True, db_index=True)

    class Meta:
        verbose_name = "histórico do cliente"
        verbose_name_plural = "históricos do cliente"
        ordering = ["-data"]

    def __str__(self):
        return f"{self.cliente} — {self.get_acao_display()}"


class Onboarding(models.Model):
    class Status(models.TextChoices):
        INICIADO = "INICIADO", "Iniciado"
        DADOS_PENDENTES = "DADOS_PENDENTES", "Dados pendentes"
        CONFIGURANDO = "CONFIGURANDO", "Configurando"
        CONCLUIDO = "CONCLUIDO", "Concluído"
        CANCELADO = "CANCELADO", "Cancelado"

    uuid = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    cliente = models.OneToOneField(
        ClientePlataforma,
        on_delete=models.CASCADE,
        related_name="onboarding",
        verbose_name="cliente",
    )
    tenant = models.ForeignKey(
        "companies.Tenant",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="onboardings",
        verbose_name="tenant",
    )
    status = models.CharField(
        "status",
        max_length=20,
        choices=Status.choices,
        default=Status.INICIADO,
    )
    observacao = models.TextField("observação", blank=True)
    usuario_responsavel = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="onboardings_responsavel",
        verbose_name="responsável",
    )
    data_inicio = models.DateTimeField("iniciado em", auto_now_add=True)
    data_conclusao = models.DateTimeField("concluído em", null=True, blank=True)

    class Meta:
        verbose_name = "onboarding"
        verbose_name_plural = "onboardings"

    def __str__(self):
        return f"Onboarding — {self.cliente}"


class LeadContato(models.Model):
    """Contato recebido pelo formulário público do site.

    Um lead NÃO cria tenant nem cliente ativo automaticamente. A equipe da
    plataforma analisa o contato e, quando aprovado, converte em cliente.
    """

    class Status(models.TextChoices):
        NOVO = "NOVO", "Novo"
        EM_ATENDIMENTO = "EM_ATENDIMENTO", "Em atendimento"
        CONVERTIDO = "CONVERTIDO", "Convertido"
        DESCARTADO = "DESCARTADO", "Descartado"

    uuid = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    nome = models.CharField("nome", max_length=255)
    email = models.EmailField("e-mail")
    telefone = models.CharField("telefone", max_length=20)
    empresa = models.CharField("empresa", max_length=255, blank=True)
    mensagem = models.TextField("mensagem")
    status = models.CharField(
        "status",
        max_length=20,
        choices=Status.choices,
        default=Status.NOVO,
    )
    cliente_convertido = models.ForeignKey(
        ClientePlataforma,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="leads_origem",
        verbose_name="cliente convertido",
    )
    ip_origem = models.GenericIPAddressField("IP de origem", null=True, blank=True)
    data_criacao = models.DateTimeField("criado em", auto_now_add=True)

    class Meta:
        verbose_name = "lead de contato"
        verbose_name_plural = "leads de contato"
        ordering = ["-data_criacao"]

    def __str__(self):
        return f"{self.nome} <{self.email}>"
