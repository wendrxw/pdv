import shutil
import tempfile

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.accounts.models import User
from apps.companies.models import Tenant

from ..models import Categoria, Produto

MEDIA_TESTE = tempfile.mkdtemp()


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


@override_settings(MEDIA_ROOT=MEDIA_TESTE)
class ProdutoImagemENcmTest(ProdutosViewBaseTestCase):
    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(MEDIA_TESTE, ignore_errors=True)

    def test_ncm_invalido_rejeitado(self):
        resposta = self.client.post(
            reverse("products:novo"),
            {
                "nome": "NCM ruim",
                "ncm": "abc",
                "unidade_medida": "UN",
                "preco_custo": "0.50",
                "preco_venda": "1.00",
                "estoque_minimo": "0",
            },
        )
        self.assertEqual(resposta.status_code, 200)
        self.assertFalse(Produto.objects.filter(nome="NCM ruim").exists())

    def test_ncm_valido_salvo(self):
        resposta = self.client.post(
            reverse("products:novo"),
            {
                "nome": "NCM bom",
                "ncm": "21069030",
                "unidade_medida": "UN",
                "preco_custo": "0.50",
                "preco_venda": "1.00",
                "estoque_minimo": "0",
            },
        )
        self.assertEqual(resposta.status_code, 302)
        produto = Produto.objects.get(nome="NCM bom")
        self.assertEqual(produto.ncm, "21069030")

    def test_imagem_valida_salva(self):
        imagem = SimpleUploadedFile(
            "foto.png", b"\x89PNG\r\n\x1a\n" + b"0" * 100, content_type="image/png"
        )
        resposta = self.client.post(
            reverse("products:novo"),
            {
                "nome": "Com imagem",
                "unidade_medida": "UN",
                "preco_custo": "0.50",
                "preco_venda": "1.00",
                "estoque_minimo": "0",
                "imagem": imagem,
            },
        )
        self.assertEqual(resposta.status_code, 302)
        produto = Produto.objects.get(nome="Com imagem")
        self.assertTrue(produto.imagem.name.endswith("foto.png"))

    def test_imagem_acima_de_2mb_rejeitada(self):
        imagem = SimpleUploadedFile(
            "grande.png",
            b"x" * (2 * 1024 * 1024 + 1),
            content_type="image/png",
        )
        resposta = self.client.post(
            reverse("products:novo"),
            {
                "nome": "Grande",
                "unidade_medida": "UN",
                "preco_custo": "0.50",
                "preco_venda": "1.00",
                "estoque_minimo": "0",
                "imagem": imagem,
            },
        )
        self.assertEqual(resposta.status_code, 200)
        self.assertFalse(Produto.objects.filter(nome="Grande").exists())

    def test_formato_nao_suportado_rejeitado(self):
        imagem = SimpleUploadedFile(
            "anim.gif", b"GIF89a" + b"0" * 100, content_type="image/gif"
        )
        resposta = self.client.post(
            reverse("products:novo"),
            {
                "nome": "GIF",
                "unidade_medida": "UN",
                "preco_custo": "0.50",
                "preco_venda": "1.00",
                "estoque_minimo": "0",
                "imagem": imagem,
            },
        )
        self.assertEqual(resposta.status_code, 200)
        self.assertFalse(Produto.objects.filter(nome="GIF").exists())

    def test_editar_sem_nova_imagem_mantem_imagem_existente(self):
        imagem = SimpleUploadedFile(
            "original.png", b"\x89PNG\r\n\x1a\n" + b"0" * 100,
            content_type="image/png",
        )
        self.client.post(
            reverse("products:novo"),
            {
                "nome": "Mantém imagem",
                "unidade_medida": "UN",
                "preco_custo": "0.50",
                "preco_venda": "1.00",
                "estoque_minimo": "0",
                "imagem": imagem,
            },
        )
        produto = Produto.objects.get(nome="Mantém imagem")
        self.assertTrue(produto.imagem)
        resposta = self.client.post(
            reverse("products:editar", args=[produto.uuid]),
            {
                "nome": "Mantém imagem",
                "unidade_medida": "UN",
                "preco_custo": "0.50",
                "preco_venda": "2.00",
                "estoque_minimo": "0",
            },
        )
        self.assertEqual(resposta.status_code, 302)
        produto.refresh_from_db()
        self.assertTrue(produto.imagem)
        self.assertTrue(produto.imagem.name.endswith("original.png"))


class BarcodeViewTest(ProdutosViewBaseTestCase):
    def test_gera_codigo_via_post_json(self):
        resposta = self.client.post(reverse("products:gerar_codigo_barras"))
        self.assertEqual(resposta.status_code, 200)
        codigo = resposta.json()["codigo"]
        self.assertEqual(len(codigo), 13)

    def test_get_nao_gera_codigo(self):
        resposta = self.client.get(reverse("products:gerar_codigo_barras"))
        self.assertEqual(resposta.status_code, 405)

    def test_svg_do_produto_com_codigo(self):
        from ..barcode import BarcodeService

        produto = Produto.objects.create(tenant=self.tenant, nome="Com código")
        produto.codigo_barras = BarcodeService.generate(self.tenant)
        produto.save(update_fields=["codigo_barras"])
        resposta = self.client.get(
            reverse("products:codigo_barras_svg", args=[produto.uuid])
        )
        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(resposta["Content-Type"], "image/svg+xml")

    def test_svg_sem_codigo_retorna_404(self):
        produto = Produto.objects.create(tenant=self.tenant, nome="Sem código")
        resposta = self.client.get(
            reverse("products:codigo_barras_svg", args=[produto.uuid])
        )
        self.assertEqual(resposta.status_code, 404)

    def test_formulario_rejeita_codigo_invalido(self):
        resposta = self.client.post(
            reverse("products:novo"),
            {
                "nome": "Produto código ruim",
                "codigo_barras": "1234567890123",
                "unidade_medida": "UN",
                "preco_custo": "1.00",
                "preco_venda": "2.00",
            },
        )
        self.assertEqual(resposta.status_code, 200)
        self.assertFalse(Produto.objects.filter(nome="Produto código ruim").exists())

    def test_busca_por_codigo_de_barras_na_listagem(self):
        from ..barcode import BarcodeService

        produto = Produto.objects.create(tenant=self.tenant, nome="Achável")
        produto.codigo_barras = BarcodeService.generate(self.tenant)
        produto.save(update_fields=["codigo_barras"])
        resposta = self.client.get(
            reverse("products:lista"), {"q": produto.codigo_barras}
        )
        self.assertIn("Achável", resposta.content.decode())
