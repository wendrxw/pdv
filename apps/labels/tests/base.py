"""Fábrica comum dos testes de etiquetas."""

from decimal import Decimal

from django.test import TestCase

from apps.accounts.models import User
from apps.companies.models import Tenant
from apps.products.models import Produto


class LabelsBaseTestCase(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(
            nome="Loja Etiquetas", status=Tenant.Status.ATIVO
        )
        self.operador = User.objects.create_user(
            username="etiquetador", password="senha-12345", tenant=self.tenant
        )
        self.produto_a = Produto.objects.create(
            tenant=self.tenant,
            nome="Produto A",
            sku="A-1",
            codigo_barras="789000000001",
            preco_venda=Decimal("10.00"),
        )
        self.produto_b = Produto.objects.create(
            tenant=self.tenant,
            nome="Produto B",
            sku="B-1",
            codigo_barras="789000000002",
            preco_venda=Decimal("20.00"),
        )
        self.produto_c = Produto.objects.create(
            tenant=self.tenant,
            nome="Produto C",
            sku="C-1",
            codigo_barras="789000000003",
            preco_venda=Decimal("30.00"),
        )

    def itens(self, *pares):
        return [
            {"uuid": str(produto.uuid), "quantidade": quantidade}
            for produto, quantidade in pares
        ]


def criar_contexto_outro():
    """Segundo tenant isolado (para testes cross-tenant)."""
    contexto = type("Contexto", (), {})()
    contexto.tenant = Tenant.objects.create(
        nome="Loja Alheia", status=Tenant.Status.ATIVO
    )
    contexto.operador = User.objects.create_user(
        username="alheio", password="senha-12345", tenant=contexto.tenant
    )
    contexto.produto_a = Produto.objects.create(
        tenant=contexto.tenant,
        nome="Produto A",
        sku="A-9",
        codigo_barras="799000000001",
        preco_venda=Decimal("1.00"),
    )
    return contexto
