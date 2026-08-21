from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import User
from apps.companies.models import Tenant

from ..models import Categoria, Produto


class ProdutosViewBaseTestCase(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(nome="Loja Web", status=Tenant.Status.ATIVO)
        self.outro_tenant = Tenant.objects.create(
            nome="Outra Loja", status=Tenant.Status.ATIVO
        )
        self.usuario = User.objects.create_user(
            username="gerente", password="senha-12345", tenant=self.tenant
        )
        self.client.force_login(self.usuario)
        self.categoria = Categoria.objects.create(tenant=self.tenant, nome="Diversos")


class ListagemProdutosTest(ProdutosViewBaseTestCase):
    def test_requer_login(self):
        self.client.logout()
        resposta = self.client.get(reverse("products:lista"))
        self.assertEqual(resposta.status_code, 302)

    def test_lista_apenas_produtos_do_tenant(self):
        Produto.objects.create(tenant=self.tenant, nome="Meu produto")
        Produto.objects.create(tenant=self.outro_tenant, nome="Produto alheio")
        resposta = self.client.get(reverse("products:lista"))
        conteudo = resposta.content.decode()
        self.assertIn("Meu produto", conteudo)
        self.assertNotIn("Produto alheio", conteudo)

    def test_busca_por_termo(self):
        Produto.objects.create(tenant=self.tenant, nome="Teclado mecânico")
        Produto.objects.create(tenant=self.tenant, nome="Mouse gamer")
        resposta = self.client.get(reverse("products:lista"), {"q": "teclado"})
        self.assertIn("Teclado mecânico", resposta.content.decode())
        self.assertNotIn("Mouse gamer", resposta.content.decode())


class CriarProdutoViewTest(ProdutosViewBaseTestCase):
    def test_cria_produto_via_post(self):
        resposta = self.client.post(
            reverse("products:novo"),
            {
                "nome": "Monitor LED",
                "sku": "MON-LED",
                "unidade_medida": "UN",
                "preco_custo": "500.00",
                "preco_venda": "899.90",
                "estoque_minimo": "1",
                "ativo": "on",
            },
        )
        self.assertEqual(resposta.status_code, 302)
        self.assertTrue(Produto.objects.filter(sku="MON-LED").exists())

    def test_post_nao_aceita_categoria_de_outro_tenant(self):
        categoria_alheia = Categoria.objects.create(
            tenant=self.outro_tenant, nome="Alheia"
        )
        resposta = self.client.post(
            reverse("products:novo"),
            {
                "nome": "Produto invasor",
                "categoria": categoria_alheia.pk,
                "unidade_medida": "UN",
                "preco_custo": "1.00",
                "preco_venda": "2.00",
            },
        )
        self.assertEqual(resposta.status_code, 200)
        self.assertFalse(Produto.objects.filter(nome="Produto invasor").exists())


class DetalheProdutoViewTest(ProdutosViewBaseTestCase):
    def test_detalhe_produto_do_tenant(self):
        produto = Produto.objects.create(tenant=self.tenant, nome="Visível")
        resposta = self.client.get(
            reverse("products:detalhe", args=[produto.uuid])
        )
        self.assertEqual(resposta.status_code, 200)

    def test_detalhe_produto_de_outro_tenant_retorna_404(self):
        produto_alheio = Produto.objects.create(
            tenant=self.outro_tenant, nome="Secreto"
        )
        resposta = self.client.get(
            reverse("products:detalhe", args=[produto_alheio.uuid])
        )
        self.assertEqual(resposta.status_code, 404)


class AlternarStatusViewTest(ProdutosViewBaseTestCase):
    def test_desativar_via_post(self):
        produto = Produto.objects.create(tenant=self.tenant, nome="Para desativar")
        resposta = self.client.post(
            reverse("products:alternar_status", args=[produto.uuid])
        )
        self.assertEqual(resposta.status_code, 302)
        produto.refresh_from_db()
        self.assertFalse(produto.ativo)

    def test_get_nao_altera_status(self):
        produto = Produto.objects.create(tenant=self.tenant, nome="Intacto")
        self.client.get(reverse("products:alternar_status", args=[produto.uuid]))
        produto.refresh_from_db()
        self.assertTrue(produto.ativo)
