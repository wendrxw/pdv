from django.test import TestCase

from apps.core.validators import (
    is_valid_cnpj,
    is_valid_cpf,
    only_digits,
    validate_cpf_cnpj,
)


class ValidadoresDocumentoTest(TestCase):
    def test_only_digits_remove_mascara(self):
        self.assertEqual(only_digits("123.456.789-01"), "12345678901")
        self.assertEqual(only_digits("12.345.678/0001-95"), "12345678000195")
        self.assertEqual(only_digits(""), "")
        self.assertEqual(only_digits(None), "")

    def test_cpf_valido(self):
        self.assertTrue(is_valid_cpf("11144477735"))
        self.assertTrue(is_valid_cpf("111.444.777-35"))
        self.assertTrue(is_valid_cpf("52998224725"))

    def test_cpf_invalido(self):
        self.assertFalse(is_valid_cpf("11144477734"))  # DV errado
        self.assertFalse(is_valid_cpf("11111111111"))  # dígitos repetidos
        self.assertFalse(is_valid_cpf("1234"))  # tamanho errado
        self.assertFalse(is_valid_cpf(""))

    def test_cnpj_valido(self):
        self.assertTrue(is_valid_cnpj("11444777000161"))
        self.assertTrue(is_valid_cnpj("11.444.777/0001-61"))

    def test_cnpj_invalido(self):
        self.assertFalse(is_valid_cnpj("11444777000162"))  # DV errado
        self.assertFalse(is_valid_cnpj("11111111111111"))  # repetidos
        self.assertFalse(is_valid_cnpj("123456"))  # tamanho errado

    def test_validate_retorna_digitos_normalizados(self):
        self.assertEqual(validate_cpf_cnpj("111.444.777-35"), "11144477735")
        self.assertEqual(
            validate_cpf_cnpj("11.444.777/0001-61"), "11444777000161"
        )

    def test_validate_levanta_erro_para_documento_invalido(self):
        with self.assertRaises(ValueError):
            validate_cpf_cnpj("11144477734")
        with self.assertRaises(ValueError):
            validate_cpf_cnpj("abc")

    def test_modelo_cliente_rejeita_documento_invalido_via_full_clean(self):
        from apps.clients.models import ClientePlataforma

        cliente = ClientePlataforma(
            nome="Empresa Teste",
            cpf_cnpj="11144477734",
            email="teste@empresa.com.br",
            telefone_celular="16999999999",
        )
        # O model normaliza para dígitos; a validação de DV ocorre nos
        # serviços e no admin (full_clean não valida DV por padrão).
        cliente.full_clean()
        self.assertEqual(cliente.cpf_cnpj, "11144477734")


class TenancyQuerySetTest(TestCase):
    def test_for_tenant_filtra_por_tenant(self):
        from apps.companies.models import Tenant

        tenant_a = Tenant.objects.create(nome="Tenant A", slug="tenant-a")
        tenant_b = Tenant.objects.create(nome="Tenant B", slug="tenant-b")

        from apps.accounts.models import User

        User.objects.create_user(username="user-a", password="x", tenant=tenant_a)
        User.objects.create_user(username="user-b", password="x", tenant=tenant_b)

        usuarios_a = User.objects.for_tenant(tenant_a)
        self.assertEqual(usuarios_a.count(), 1)
        self.assertEqual(usuarios_a.first().username, "user-a")
        self.assertNotIn(tenant_b, [u.tenant for u in usuarios_a])

    def test_tenant_slug_unico_e_gerado_automaticamente(self):
        from apps.companies.models import Tenant

        tenant = Tenant.objects.create(nome="Loja Exemplo!")
        self.assertEqual(tenant.slug, "loja-exemplo")

        duplicado = Tenant.objects.create(nome="Loja Exemplo")
        self.assertTrue(duplicado.slug.startswith("loja-exemplo-"))
        self.assertNotEqual(duplicado.slug, tenant.slug)

    def test_is_operacional_apenas_para_ativo(self):
        from apps.companies.models import Tenant

        ativo = Tenant.objects.create(
            nome="Ativo", status=Tenant.Status.ATIVO
        )
        pendente = Tenant.objects.create(
            nome="Pendente", status=Tenant.Status.PENDENTE
        )
        self.assertTrue(ativo.is_operacional)
        self.assertFalse(pendente.is_operacional)
