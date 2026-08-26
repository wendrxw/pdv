"""Models do módulo de clientes do tenant (consumidores da loja).

Não confundir com apps.clients (clientes da plataforma SaaS). Aqui vivem
os clientes finais de cada loja, usados no PDV e em contas a receber.
"""

import uuid

from django.db import models

from apps.companies.models import Tenant
from apps.core.tenancy import TenantAwareModel


class Cliente(TenantAwareModel):
    class UF(models.TextChoices):
        AC = "AC", "Acre"
        AL = "AL", "Alagoas"
        AP = "AP", "Amapá"
        AM = "AM", "Amazonas"
        BA = "BA", "Bahia"
        CE = "CE", "Ceará"
        DF = "DF", "Distrito Federal"
        ES = "ES", "Espírito Santo"
        GO = "GO", "Goiás"
        MA = "MA", "Maranhão"
        MT = "MT", "Mato Grosso"
        MS = "MS", "Mato Grosso do Sul"
        MG = "MG", "Minas Gerais"
        PA = "PA", "Pará"
        PB = "PB", "Paraíba"
        PR = "PR", "Paraná"
        PE = "PE", "Pernambuco"
        PI = "PI", "Piauí"
        RJ = "RJ", "Rio de Janeiro"
        RN = "RN", "Rio Grande do Norte"
        RS = "RS", "Rio Grande do Sul"
        RO = "RO", "Rondônia"
        RR = "RR", "Roraima"
        SC = "SC", "Santa Catarina"
        SP = "SP", "São Paulo"
        SE = "SE", "Sergipe"
        TO = "TO", "Tocantins"

    uuid = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    tenant = models.ForeignKey(
        Tenant,
        on_delete=models.PROTECT,
        related_name="clientes",
        verbose_name="tenant",
    )
    nome = models.CharField("nome", max_length=200)
    cpf_cnpj = models.CharField("CPF/CNPJ", max_length=14, blank=True)
    email = models.EmailField("e-mail", blank=True)
    telefone = models.CharField("telefone", max_length=20, blank=True)
    endereco = models.CharField("endereço", max_length=255, blank=True)
    numero = models.CharField("número", max_length=20, blank=True)
    complemento = models.CharField("complemento", max_length=100, blank=True)
    bairro = models.CharField("bairro", max_length=100, blank=True)
    cidade = models.CharField("cidade", max_length=100, blank=True)
    estado = models.CharField(
        "UF", max_length=2, choices=UF.choices, blank=True
    )
    cep = models.CharField("CEP", max_length=8, blank=True)
    observacoes = models.TextField("observações", blank=True)
    ativo = models.BooleanField("ativo", default=True, db_index=True)
    data_cadastro = models.DateTimeField("criado em", auto_now_add=True)
    data_atualizacao = models.DateTimeField("atualizado em", auto_now=True)

    class Meta:
        verbose_name = "cliente"
        verbose_name_plural = "clientes"
        ordering = ["nome"]
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "cpf_cnpj"],
                condition=~models.Q(cpf_cnpj=""),
                name="unique_cliente_cpf_cnpj_per_tenant",
            ),
        ]
        indexes = [
            models.Index(fields=["tenant", "ativo"]),
            models.Index(fields=["tenant", "nome"]),
        ]

    def __str__(self):
        return self.nome
