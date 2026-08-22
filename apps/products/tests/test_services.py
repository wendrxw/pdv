from decimal import Decimal

from django.test import TestCase

from apps.companies.models import Tenant

from ..models import Categoria, Marca, Produto
from ..services import (
    ProductServiceError,
    alterar_produto,
    criar_produto,
    desativar_produto,
    obter_produto,
)


class ProdutoBaseTestCase(TestCase):
    def setUp(self):
        self.tenant_a = Tenant.objects.create(nome="Loja A", status=Tenant.Status.ATIVO)
        self.tenant_b = Tenant.objects.create(nome="Loja B", status=Tenant.Status.ATIVO)
        self.categoria_a = Categoria.objects.create(
            tenant=self.tenant_a, nome="Bebidas"
        )
        self.marca_a = Marca.objects.create(tenant=self.tenant_a, nome="Acme")

    def _dados(self, **overrides):
        dados = {
            "nome": "Refrigerante 2L",
            "sku": "REF-2L",
            "preco_custo": Decimal("4.50"),
            "preco_venda": Decimal("7.90"),
            "categoria": self.categoria_a,
            "marca": self.marca_a,
        }
        dados.update(overrides)
        return dados


class CriarProdutoTest(ProdutoBaseTestCase):
    def test_cria_produto_com_uuid_e_datas_automaticos(self):
        produto = criar_produto(tenant=self.tenant_a, **self._dados())
        self.assertIsNotNone(produto.uuid)
        self.assertIsNotNone(produto.data_cadastro)
        self.assertTrue(produto.ativo)
        self.assertEqual(produto.unidade_medida, Produto.UnidadeMedida.UN)

    def test_preco_negativo_rejeitado(self):
        with self.assertRaises(ProductServiceError):
            criar_produto(
                tenant=self.tenant_a, **self._dados(preco_venda=Decimal("-1"))
            )

    def test_categoria_de_outro_tenant_rejeitada(self):
        categoria_b = Categoria.objects.create(tenant=self.tenant_b, nome="Limpeza")
        with self.assertRaises(ProductServiceError):
            criar_produto(
                tenant=self.tenant_a, **self._dados(categoria=categoria_b)
            )

    def test_marca_de_outro_tenant_rejeitada(self):
        marca_b = Marca.objects.create(tenant=self.tenant_b, nome="Beta")
        with self.assertRaises(ProductServiceError):
            criar_produto(tenant=self.tenant_a, **self._dados(marca=marca_b))

    def test_sku_duplicado_no_tenant_rejeitado(self):
        criar_produto(tenant=self.tenant_a, **self._dados())
        with self.assertRaises(ProductServiceError):
            criar_produto(
                tenant=self.tenant_a,
                **self._dados(nome="Outro produto", sku="REF-2L"),
            )

    def test_sku_pode_repetir_entre_tenants(self):
        criar_produto(tenant=self.tenant_a, **self._dados())
        produto_b = criar_produto(
            tenant=self.tenant_b, **self._dados(categoria=None, marca=None)
        )
        self.assertEqual(produto_b.sku, "REF-2L")


class AlterarProdutoTest(ProdutoBaseTestCase):
    def test_altera_preco(self):
        produto = criar_produto(tenant=self.tenant_a, **self._dados())
        alterar_produto(
            produto, preco_venda=Decimal("9.90"), usuario=None
        )
        produto.refresh_from_db()
        self.assertEqual(produto.preco_venda, Decimal("9.90"))

    def test_alteracao_para_categoria_cross_tenant_bloqueada(self):
        produto = criar_produto(tenant=self.tenant_a, **self._dados())
        categoria_b = Categoria.objects.create(tenant=self.tenant_b, nome="Padaria")
        with self.assertRaises(ProductServiceError):
            alterar_produto(produto, categoria=categoria_b)


class DesativarProdutoTest(ProdutoBaseTestCase):
    def test_desativacao_mantem_registro(self):
        produto = criar_produto(tenant=self.tenant_a, **self._dados())
        desativar_produto(produto)
        produto.refresh_from_db()
        self.assertFalse(produto.ativo)
        self.assertTrue(Produto.objects.filter(pk=produto.pk).exists())


class IsolamentoMultiTenantTest(ProdutoBaseTestCase):
    def _dados_sem_relacoes(self, **overrides):
        return self._dados(categoria=None, marca=None, **overrides)

    def test_tenant_nao_acessa_produto_de_outro(self):
        produto_b = criar_produto(
            tenant=self.tenant_b, **self._dados_sem_relacoes()
        )
        with self.assertRaises(Produto.DoesNotExist):
            obter_produto(self.tenant_a, produto_b.uuid)

    def test_listagem_somente_do_tenant(self):
        criar_produto(tenant=self.tenant_a, **self._dados())
        criar_produto(
            tenant=self.tenant_b,
            **self._dados_sem_relacoes(nome="Produto B"),
        )
        from ..services import buscar_produtos

        produtos_a = buscar_produtos(self.tenant_a)
        produtos_b = buscar_produtos(self.tenant_b)
        self.assertEqual(produtos_a.count(), 1)
        self.assertEqual(produtos_b.count(), 1)
        self.assertEqual(produtos_a.first().tenant, self.tenant_a)

    def test_busca_por_termo_e_filtros(self):
        criar_produto(tenant=self.tenant_a, **self._dados())
        criar_produto(
            tenant=self.tenant_a,
            **self._dados(nome="Cadeira plástica", sku="CAD-PLA"),
        )
        from ..services import buscar_produtos

        resultado = buscar_produtos(self.tenant_a, termo="refri")
        self.assertEqual(resultado.count(), 1)
        por_categoria = buscar_produtos(
            self.tenant_a, categoria=self.categoria_a
        )
        self.assertEqual(por_categoria.count(), 2)
        inativos = buscar_produtos(self.tenant_a, status="inativos")
        self.assertEqual(inativos.count(), 0)
