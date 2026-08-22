"""Testes de segurança multi-tenant e de permissões.

Garante que:
- usuário de tenant não acessa dados de outro tenant;
- usuário comum não acessa o Django Admin;
- UUID não é mecanismo de bypass de autorização.
"""

from django.test import TestCase

from apps.accounts.models import User
from apps.clients.models import ClientePlataforma
from apps.companies.models import Tenant


class IsolamentoUsuariosPorTenantTest(TestCase):
    def setUp(self):
        self.tenant_a = Tenant.objects.create(
            nome="Tenant A", slug="tenant-a", status=Tenant.Status.ATIVO
        )
        self.tenant_b = Tenant.objects.create(
            nome="Tenant B", slug="tenant-b", status=Tenant.Status.ATIVO
        )
        self.user_a = User.objects.create_user(
            username="user-a", password="senha-123", tenant=self.tenant_a
        )
        self.user_b = User.objects.create_user(
            username="user-b", password="senha-123", tenant=self.tenant_b
        )

    def test_usuario_pertence_ao_tenant_correto(self):
        self.assertEqual(self.user_a.get_tenant(), self.tenant_a)
        self.assertNotEqual(self.user_a.get_tenant(), self.tenant_b)

    def test_equipe_plataforma_nao_tem_tenant(self):
        staff = User.objects.create_user(
            username="staff",
            password="senha-123",
            is_staff=True,
            is_superuser=True,
        )
        self.assertTrue(staff.is_plataforma)
        self.assertIsNone(staff.get_tenant())

    def test_usuario_de_tenant_nao_e_plataforma(self):
        self.assertFalse(self.user_a.is_plataforma)


class AcessoAdminTest(TestCase):
    def setUp(self):
        self.staff = User.objects.create_user(
            username="admin-user",
            password="senha-123",
            is_staff=True,
            is_superuser=True,
        )
        self.comum = User.objects.create_user(
            username="comum", password="senha-123"
        )

    def test_staff_acessa_admin(self):
        self.client.force_login(self.staff)
        resposta = self.client.get("/admin/")
        self.assertEqual(resposta.status_code, 200)

    def test_usuario_comum_nao_acessa_admin(self):
        self.client.force_login(self.comum)
        resposta = self.client.get("/admin/")
        # Redireciona para login do admin (403/302), nunca 200
        self.assertIn(resposta.status_code, (302, 403))

    def test_anonimo_redirecionado_para_login_admin(self):
        resposta = self.client.get("/admin/")
        self.assertEqual(resposta.status_code, 302)
        self.assertIn("/admin/login/", resposta.url)


class DashboardMultiTenantTest(TestCase):
    def setUp(self):
        self.tenant_a = Tenant.objects.create(
            nome="Tenant A", slug="tenant-a", status=Tenant.Status.ATIVO
        )
        self.tenant_b = Tenant.objects.create(
            nome="Tenant B", slug="tenant-b", status=Tenant.Status.ATIVO
        )
        self.user_a = User.objects.create_user(
            username="user-a", password="senha-123", tenant=self.tenant_a
        )

    def test_dashboard_exige_login(self):
        resposta = self.client.get("/app/")
        self.assertEqual(resposta.status_code, 302)
        self.assertIn("/login/", resposta.url)

    def test_dashboard_mostra_apenas_tenant_do_usuario(self):
        self.client.force_login(self.user_a)
        resposta = self.client.get("/app/")
        self.assertEqual(resposta.status_code, 200)
        conteudo = resposta.content.decode()
        self.assertIn("Tenant A", conteudo)
        self.assertNotIn("Tenant B", conteudo)


class ClientePlataformaAcessoTest(TestCase):
    """UUID não é mecanismo de isolamento: acesso a dados de clientes da
    plataforma é restrito à equipe autorizada."""

    def setUp(self):
        self.cliente = ClientePlataforma.objects.create(
            nome="Cliente Confidencial",
            cpf_cnpj="11444777000161",
            email="confidencial@empresa.com.br",
            telefone_celular="16999999999",
        )
        self.comum = User.objects.create_user(
            username="comum", password="senha-123"
        )

    def test_usuario_de_tenant_nao_ve_clientes_no_admin(self):
        self.client.force_login(self.comum)
        resposta = self.client.get(
            f"/admin/clients/clienteplataforma/{self.cliente.pk}/change/"
        )
        self.assertIn(resposta.status_code, (302, 403))
