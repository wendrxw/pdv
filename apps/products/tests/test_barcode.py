from django.test import TestCase

from apps.companies.models import Tenant

from ..barcode import BarcodeError, BarcodeRenderer, BarcodeService
from ..models import Produto


class CheckDigitTest(TestCase):
    def test_digito_verificador_valores_conhecidos(self):
        # EAN-13 de exemplo da documentação GS1.
        self.assertEqual(BarcodeService.calculate_check_digit("400638133393"), "1")
        self.assertEqual(BarcodeService.calculate_check_digit("978020137962"), "4")

    def test_base_invalida_gera_erro(self):
        with self.assertRaises(BarcodeError):
            BarcodeService.calculate_check_digit("123")
        with self.assertRaises(BarcodeError):
            BarcodeService.calculate_check_digit("abcdefghijklm")


class ValidateBarcodeTest(TestCase):
    def test_codigo_valido(self):
        self.assertTrue(BarcodeService.validate("4006381333931"))

    def test_digito_verificador_errado(self):
        self.assertFalse(BarcodeService.validate("4006381333932"))

    def test_tamanho_errado(self):
        self.assertFalse(BarcodeService.validate("400638133393"))
        self.assertFalse(BarcodeService.validate("40063813339311"))

    def test_nao_numerico(self):
        self.assertFalse(BarcodeService.validate("40063813339A1"))


class GenerateBarcodeTest(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(nome="Loja Barcode")

    def test_gera_codigo_valido_com_prefixo_interno(self):
        codigo = BarcodeService.generate(self.tenant)
        self.assertEqual(len(codigo), 13)
        self.assertTrue(codigo.startswith("2"))
        self.assertTrue(BarcodeService.validate(codigo))

    def test_codigos_gerados_sao_unicos_no_tenant(self):
        codigos = {BarcodeService.generate(self.tenant) for _ in range(20)}
        self.assertEqual(len(codigos), 20)

    def test_nao_reutiliza_codigo_de_produto_desativado(self):
        codigo = BarcodeService.generate(self.tenant)
        Produto.objects.create(
            tenant=self.tenant, nome="X", codigo_barras=codigo, ativo=False
        )
        for _ in range(10):
            self.assertNotEqual(BarcodeService.generate(self.tenant), codigo)


class UnicidadePorTenantTest(TestCase):
    def test_mesmo_codigo_em_tenants_diferentes_e_permitido(self):
        tenant_a = Tenant.objects.create(nome="A")
        tenant_b = Tenant.objects.create(nome="B")
        codigo = BarcodeService.generate(tenant_a)
        Produto.objects.create(tenant=tenant_a, nome="P A", codigo_barras=codigo)
        Produto.objects.create(tenant=tenant_b, nome="P B", codigo_barras=codigo)
        self.assertEqual(Produto.objects.count(), 2)

    def test_codigo_duplicado_no_mesmo_tenant_bloqueado(self):
        from django.db import IntegrityError, transaction

        tenant = Tenant.objects.create(nome="C")
        codigo = BarcodeService.generate(tenant)
        Produto.objects.create(tenant=tenant, nome="P1", codigo_barras=codigo)
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Produto.objects.create(
                    tenant=tenant, nome="P2", codigo_barras=codigo
                )


class BarcodeRendererTest(TestCase):
    def test_renderiza_svg_valido(self):
        codigo = BarcodeService.generate(Tenant.objects.create(nome="R"))
        svg = BarcodeRenderer.to_svg(codigo)
        self.assertIn("<svg", svg)
        self.assertIn("</svg>", svg)
        self.assertIn(codigo, svg)

    def test_codigo_invalido_nao_renderiza(self):
        with self.assertRaises(BarcodeError):
            BarcodeRenderer.to_svg("123")
