from django.test import TestCase

from apps.companies.models import Tenant

from ..models import Categoria, Produto


class ProdutoModelTest(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(nome="Loja X")

    def test_str_retorna_nome(self):
        produto = Produto.objects.create(tenant=self.tenant, nome="Caderno")
        self.assertEqual(str(produto), "Caderno")

    def test_uuid_unico_por_produto(self):
        p1 = Produto.objects.create(tenant=self.tenant, nome="A")
        p2 = Produto.objects.create(tenant=self.tenant, nome="B")
        self.assertNotEqual(p1.uuid, p2.uuid)

    def test_sku_opcional_e_unico_no_tenant(self):
        Produto.objects.create(tenant=self.tenant, nome="A", sku="SKU-1")
        from django.db import IntegrityError

        with self.assertRaises(IntegrityError):
            Produto.objects.create(tenant=self.tenant, nome="B", sku="SKU-1")

    def test_sku_vazio_permite_varios_produtos(self):
        Produto.objects.create(tenant=self.tenant, nome="A", sku="")
        Produto.objects.create(tenant=self.tenant, nome="B", sku="")
        self.assertEqual(Produto.objects.count(), 2)

    def test_categoria_unica_por_tenant(self):
        from django.db import IntegrityError, transaction

        tenant_b = Tenant.objects.create(nome="Loja Y")
        Categoria.objects.create(tenant=self.tenant, nome="Geral")
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Categoria.objects.create(tenant=self.tenant, nome="Geral")
        # Mesmo nome em tenants diferentes é permitido.
        Categoria.objects.create(tenant=tenant_b, nome="Geral")
