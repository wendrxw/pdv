"""Fábrica comum dos testes do módulo de impressão."""

from decimal import Decimal

from django.test import TestCase

from apps.accounts.models import User
from apps.companies.models import Tenant
from apps.financial.models import ContaFinanceira
from apps.financial.services import criar_conta, criar_forma_pagamento
from apps.inventory.services import adicionar_estoque
from apps.products.models import Produto
from apps.sales.services import (
    abrir_caixa,
    abrir_venda,
    adicionar_item,
    adicionar_pagamento,
    finalizar_venda,
)


class PrintingBaseTestCase(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(
            nome="Loja Impressão", status=Tenant.Status.ATIVO
        )
        self.operador = User.objects.create_user(
            username="operador-impressao",
            password="senha-12345",
            tenant=self.tenant,
        )
        self.conta = criar_conta(
            self.tenant,
            nome="Gaveta",
            tipo=ContaFinanceira.Tipo.CAIXA,
        )
        self.dinheiro = criar_forma_pagamento(
            self.tenant, nome="Dinheiro", codigo="DINHEIRO"
        )
        self.pix = criar_forma_pagamento(self.tenant, nome="PIX", codigo="PIX")
        self.produto = Produto.objects.create(
            tenant=self.tenant,
            nome="Café Especial",
            sku="CAFE-1",
            preco_venda=Decimal("9.90"),
        )
        adicionar_estoque(self.produto, Decimal("100"))
        self.caixa = abrir_caixa(
            self.tenant,
            operador=self.operador,
            conta_financeira=self.conta,
            saldo_inicial=Decimal("50.00"),
        )

    def venda_finalizada(self, forma_pagamento=None, quantidade=Decimal("2")):
        venda = abrir_venda(self.caixa)
        adicionar_item(venda, self.produto, quantidade, usuario=self.operador)
        venda.refresh_from_db()
        forma = forma_pagamento or self.dinheiro
        adicionar_pagamento(venda, forma, venda.total)
        return finalizar_venda(venda, usuario=self.operador)
