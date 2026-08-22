from decimal import Decimal

from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import User
from apps.companies.models import Tenant
from apps.products.models import Produto

from ..models import Estoque, MovimentacaoEstoque
from ..services import adicionar_estoque


class EstoqueViewBaseTestCase(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(
            nome="Loja Views", status=Tenant.Status.ATIVO
        )
        self.outro_tenant = Tenant.objects.create(
            nome="Outra", status=Tenant.Status.ATIVO
        )
        self.usuario = User.objects.create_user(
            username="estoquista", password="senha-12345", tenant=self.tenant
        )
        self.client.force_login(self.usuario)
        self.produto = Produto.objects.create(tenant=self.tenant, nome="Produto View")
        self.produto_alheio = Produto.objects.create(
            tenant=self.outro_tenant, nome="Produto Alheio"
        )


class DashboardEstoqueTest(EstoqueViewBaseTestCase):
    def test_requer_login(self):
        self.client.logout()
        resposta = self.client.get(reverse("inventory:dashboard"))
        self.assertEqual(resposta.status_code, 302)

    def test_dashboard_renderiza_indicadores(self):
        adicionar_estoque(self.produto, 10)
        resposta = self.client.get(reverse("inventory:dashboard"))
        self.assertEqual(resposta.status_code, 200)
        conteudo = resposta.content.decode()
        self.assertIn("Produto View", conteudo)


class EntradaSaidaViewTest(EstoqueViewBaseTestCase):
    def test_registra_entrada_via_post(self):
        resposta = self.client.post(
            reverse("inventory:entrada"),
            {
                "produto": self.produto.pk,
                "quantidade": "25",
                "custo_unitario": "9.90",
                "motivo": "Compra semanal",
            },
        )
        self.assertEqual(resposta.status_code, 302)
        estoque = Estoque.objects.get(produto=self.produto)
        self.assertEqual(estoque.quantidade, Decimal("25"))

    def test_entrada_com_produto_de_outro_tenant_falha(self):
        resposta = self.client.post(
            reverse("inventory:entrada"),
            {
                "produto": self.produto_alheio.pk,
                "quantidade": "10",
            },
        )
        self.assertEqual(resposta.status_code, 200)
        self.assertFalse(
            Estoque.objects.filter(produto=self.produto_alheio).exists()
        )

    def test_registra_saida_via_post(self):
        adicionar_estoque(self.produto, 20)
        resposta = self.client.post(
            reverse("inventory:saida"),
            {"produto": self.produto.pk, "quantidade": "5", "motivo": "Avaria"},
        )
        self.assertEqual(resposta.status_code, 302)
        estoque = Estoque.objects.get(produto=self.produto)
        self.assertEqual(estoque.quantidade, Decimal("15"))

    def test_saida_sem_saldo_mostra_erro(self):
        resposta = self.client.post(
            reverse("inventory:saida"),
            {"produto": self.produto.pk, "quantidade": "5"},
        )
        # Erro de domínio re-renderiza o formulário com mensagem e
        # nada é persistido (rollback transacional).
        self.assertEqual(resposta.status_code, 200)
        from ..services import obter_ou_criar_estoque

        estoque = obter_ou_criar_estoque(self.produto)
        self.assertEqual(estoque.quantidade, Decimal("0"))
        self.assertFalse(
            MovimentacaoEstoque.objects.filter(produto=self.produto).exists()
        )


class MovimentacoesViewTest(EstoqueViewBaseTestCase):
    def test_lista_somente_movimentacoes_do_tenant(self):
        adicionar_estoque(self.produto, 5)
        adicionar_estoque(self.produto_alheio, 99)
        resposta = self.client.get(reverse("inventory:movimentacoes"))
        conteudo = resposta.content.decode()
        self.assertIn("Produto View", conteudo)
        self.assertNotIn("Produto Alheio", conteudo)

    def test_filtra_por_tipo(self):
        adicionar_estoque(self.produto, 5)
        resposta = self.client.get(
            reverse("inventory:movimentacoes"), {"tipo": "VENDA"}
        )
        self.assertIn("Nenhuma movimentação", resposta.content.decode())


class HistoricoProdutoViewTest(EstoqueViewBaseTestCase):
    def test_historico_do_produto_do_tenant(self):
        adicionar_estoque(self.produto, 7)
        resposta = self.client.get(
            reverse("inventory:historico_produto", args=[self.produto.uuid])
        )
        self.assertEqual(resposta.status_code, 200)
        self.assertIn("7", resposta.content.decode())

    def test_historico_produto_alheio_retorna_404(self):
        resposta = self.client.get(
            reverse("inventory:historico_produto", args=[self.produto_alheio.uuid])
        )
        self.assertEqual(resposta.status_code, 404)


class SaldosViewTest(EstoqueViewBaseTestCase):
    def test_lista_saldos_com_situacao(self):
        adicionar_estoque(self.produto, 1)
        resposta = self.client.get(reverse("inventory:saldos"))
        self.assertEqual(resposta.status_code, 200)

    def test_busca_por_termo(self):
        adicionar_estoque(self.produto, 3)
        resposta = self.client.get(reverse("inventory:saldos"), {"q": "inexistente"})
        self.assertIn("Nenhum saldo", resposta.content.decode())
