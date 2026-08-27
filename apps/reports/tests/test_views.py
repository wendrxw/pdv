from decimal import Decimal

from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import User
from apps.companies.models import Tenant
from apps.financial.models import ContaFinanceira
from apps.financial.services import criar_conta, criar_forma_pagamento
from apps.products.models import Categoria, Produto
from apps.sales.services import (
    abrir_caixa,
    abrir_venda,
    adicionar_item,
    finalizar_venda,
)


class ReportsBaseTestCase(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(
            nome="Loja Relatórios", status=Tenant.Status.ATIVO
        )
        self.usuario = User.objects.create_user(
            username="gerente-rel", password="senha-12345", tenant=self.tenant
        )
        self.conta = criar_conta(
            self.tenant, nome="Gaveta", tipo=ContaFinanceira.Tipo.CAIXA
        )
        self.dinheiro = criar_forma_pagamento(
            self.tenant, nome="Dinheiro", codigo="DINHEIRO"
        )
        self.categoria = Categoria.objects.create(
            tenant=self.tenant, nome="Bebidas"
        )
        self.produto = Produto.objects.create(
            tenant=self.tenant,
            nome="Refrigerante",
            categoria=self.categoria,
            preco_venda=Decimal("10.00"),
        )
        self.caixa = abrir_caixa(
            self.tenant, operador=self.usuario, conta_financeira=self.conta
        )
        self.client.force_login(self.usuario)

    def _vender(self):
        venda = abrir_venda(self.caixa)
        adicionar_item(venda, self.produto, Decimal("2"), usuario=self.usuario)
        finalizar_venda(
            venda, usuario=self.usuario, forma_pagamento=self.dinheiro
        )
        return venda


class ReportsViewTest(ReportsBaseTestCase):
    def test_requer_login(self):
        self.client.logout()
        resposta = self.client.get(reverse("reports:indice"))
        self.assertEqual(resposta.status_code, 302)

    def test_usuario_sem_tenant_redireciona(self):
        sem_tenant = User.objects.create_user(
            username="plataforma-rel", password="x1234567"
        )
        self.client.force_login(sem_tenant)
        resposta = self.client.get(reverse("reports:indice"))
        self.assertRedirects(resposta, reverse("dashboard"))

    def test_pagina_renderiza_com_vendas(self):
        self._vender()
        resposta = self.client.get(reverse("reports:indice"))
        self.assertEqual(resposta.status_code, 200)
        conteudo = resposta.content.decode()
        self.assertIn("Relatórios", conteudo)
        self.assertIn("R$ 20,00", conteudo)
        self.assertIn("Refrigerante", conteudo)
        self.assertIn("Bebidas", conteudo)
        self.assertIn("Dinheiro", conteudo)

    def test_isolamento_por_tenant(self):
        alheio = Tenant.objects.create(nome="Alheia Rel")
        usuario_alheio = User.objects.create_user(
            username="alheio-rel", password="senha-12345", tenant=alheio
        )
        conta_alheia = criar_conta(
            alheio, nome="Gaveta alheia", tipo=ContaFinanceira.Tipo.CAIXA
        )
        dinheiro_alheio = criar_forma_pagamento(
            alheio, nome="Dinheiro alheio", codigo="DINHEIRO"
        )
        produto_alheio = Produto.objects.create(
            tenant=alheio, nome="Produto Secreto", preco_venda=Decimal("99.00")
        )
        caixa_alheio = abrir_caixa(
            alheio, operador=usuario_alheio, conta_financeira=conta_alheia
        )
        venda_alheia = abrir_venda(caixa_alheio)
        adicionar_item(
            venda_alheia, produto_alheio, Decimal("1"), usuario=usuario_alheio
        )
        finalizar_venda(
            venda_alheia, usuario=usuario_alheio, forma_pagamento=dinheiro_alheio
        )
        resposta = self.client.get(reverse("reports:indice"))
        conteudo = resposta.content.decode()
        self.assertNotIn("Produto Secreto", conteudo)
        self.assertNotIn("99,00", conteudo)

    def test_filtro_por_produto(self):
        self._vender()
        outro = Produto.objects.create(
            tenant=self.tenant, nome="Outro Produto", preco_venda=Decimal("5.00")
        )
        venda = abrir_venda(self.caixa)
        adicionar_item(venda, outro, Decimal("1"), usuario=self.usuario)
        finalizar_venda(
            venda, usuario=self.usuario, forma_pagamento=self.dinheiro
        )
        resposta = self.client.get(
            reverse("reports:indice"), {"produto": outro.pk}
        )
        conteudo = resposta.content.decode()
        self.assertIn(">Outro Produto</td>", conteudo)
        self.assertNotIn(">Refrigerante</td>", conteudo)
        self.assertIn("R$ 5,00", conteudo)

    def test_filtro_por_forma_de_pagamento(self):
        self._vender()
        pix = criar_forma_pagamento(self.tenant, nome="PIX", codigo="PIX")
        venda = abrir_venda(self.caixa)
        adicionar_item(venda, self.produto, Decimal("1"), usuario=self.usuario)
        finalizar_venda(venda, usuario=self.usuario, forma_pagamento=pix)
        resposta = self.client.get(
            reverse("reports:indice"), {"forma_pagamento": str(pix.uuid)}
        )
        conteudo = resposta.content.decode()
        self.assertIn(">PIX</td>", conteudo)
        self.assertNotIn(">Dinheiro</td>", conteudo)
        self.assertIn("R$ 10,00", conteudo)

    def test_periodo_invalido_normalizado(self):
        resposta = self.client.get(
            reverse("reports:indice"), {"inicio": "bogus", "fim": "2026-01-01"}
        )
        self.assertEqual(resposta.status_code, 200)

    def test_estoque_baixo_exibido(self):
        from apps.inventory.services import obter_ou_criar_estoque

        estoque = obter_ou_criar_estoque(self.produto)
        estoque.quantidade = Decimal("2")
        estoque.save(update_fields=["quantidade"])
        self.produto.estoque_minimo = Decimal("5")
        self.produto.save(update_fields=["estoque_minimo"])
        resposta = self.client.get(reverse("reports:indice"))
        conteudo = resposta.content.decode()
        self.assertIn("Refrigerante", conteudo)
        self.assertIn("Produtos com estoque baixo", conteudo)

    def test_fechamentos_de_caixa_listados(self):
        from apps.sales.services import fechar_caixa

        fechar_caixa(
            self.caixa,
            saldo_informado=Decimal("0.00"),
            observacao="Fim do turno",
            usuario=self.usuario,
        )
        resposta = self.client.get(reverse("reports:indice"))
        conteudo = resposta.content.decode()
        self.assertIn("Fechamentos de caixa", conteudo)
        self.assertIn("gerente-rel", conteudo)
