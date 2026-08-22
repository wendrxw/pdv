from django.contrib.auth import authenticate, get_user_model
from django.test import TestCase

from apps.clients.models import ClientePlataforma, Onboarding
from apps.companies.models import Tenant


class ClientePlataformaAutenticacaoTest(TestCase):
    def _cliente(self, email="cliente@empresa.com.br", senha="SenhaCliente@123"):
        cliente = ClientePlataforma.objects.create(
            nome="Cliente Login",
            email=email,
            telefone_celular="16999999999",
        )
        cliente.set_password(senha)
        cliente.save()
        return cliente

    def test_autentica_cliente_por_email_e_senha(self):
        cliente = self._cliente()
        user = authenticate(username="cliente@empresa.com.br", password="SenhaCliente@123")
        self.assertIsNotNone(user)
        self.assertEqual(user.email, cliente.email)
        self.assertFalse(user.is_staff)
        cliente.refresh_from_db()
        self.assertEqual(cliente.usuario_id, user.id)

    def test_senha_incorreta_nao_autentica(self):
        self._cliente()
        self.assertIsNone(
            authenticate(username="cliente@empresa.com.br", password="senha-errada")
        )

    def test_email_inexistente_nao_autentica(self):
        self.assertIsNone(
            authenticate(username="naoexiste@empresa.com.br", password="qualquer")
        )

    def test_sem_senha_cadastrada_nao_autentica(self):
        cliente = ClientePlataforma.objects.create(
            nome="Sem Senha",
            email="semsenha@empresa.com.br",
            telefone_celular="16999999999",
        )
        self.assertIsNone(
            authenticate(username="semsenha@empresa.com.br", password="qualquer")
        )
        self.assertIsNone(cliente.usuario)

    def test_conta_vinculada_reutilizada_nos_proximos_logins(self):
        self._cliente()
        primeiro = authenticate(username="cliente@empresa.com.br", password="SenhaCliente@123")
        segundo = authenticate(username="cliente@empresa.com.br", password="SenhaCliente@123")
        self.assertEqual(primeiro.id, segundo.id)
        self.assertEqual(
            get_user_model().objects.filter(username="cliente@empresa.com.br").count(), 1
        )

    def test_login_via_view_com_cliente(self):
        cliente = self._cliente()
        response = self.client.post(
            "/login/",
            {"username": cliente.email, "password": "SenhaCliente@123"},
            follow=True,
        )
        self.assertEqual(response.status_code, 200)
        cliente.refresh_from_db()
        self.assertEqual(self.client.session.get("_auth_user_id"), str(cliente.usuario_id))

    def test_login_sincroniza_tenant_do_cliente(self):
        cliente = self._cliente()
        tenant = Tenant.objects.create(nome="Tenant do Cliente")
        Onboarding.objects.create(cliente=cliente, tenant=tenant)
        user = authenticate(username=cliente.email, password="SenhaCliente@123")
        self.assertIsNotNone(user)
        self.assertEqual(user.tenant_id, tenant.id)
