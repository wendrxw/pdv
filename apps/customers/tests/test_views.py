from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import User
from apps.companies.models import Tenant

from ..models import Cliente
from ..services import (
    CustomerError,
    criar_cliente,
    desativar_cliente,
    reativar_cliente,
)


class ClientesBaseTestCase(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(
            nome="Loja Clientes", status=Tenant.Status.ATIVO
        )
        self.outro = Tenant.objects.create(nome="Loja Alheia")
        self.usuario = User.objects.create_user(
            username="atendente", password="senha-12345", tenant=self.tenant
        )
        self.client.force_login(self.usuario)


class ClienteServiceTest(ClientesBaseTestCase):
    def test_criar_cliente(self):
        cliente = criar_cliente(
            tenant=self.tenant,
            nome="Maria da Silva",
            cpf_cnpj="12345678900",
            usuario=self.usuario,
        )
        self.assertEqual(cliente.tenant, self.tenant)
        self.assertTrue(cliente.ativo)

    def test_cpf_cnpj_unico_por_tenant(self):
        criar_cliente(tenant=self.tenant, nome="A", cpf_cnpj="11122233344")
        criar_cliente(tenant=self.outro, nome="B", cpf_cnpj="11122233344")
        with self.assertRaises(CustomerError):
            criar_cliente(tenant=self.tenant, nome="C", cpf_cnpj="11122233344")

    def test_cpf_cnpj_unico_garantido_no_banco(self):
        from django.db import IntegrityError

        Cliente.objects.create(
            tenant=self.tenant, nome="A", cpf_cnpj="11122233344"
        )
        with self.assertRaises(IntegrityError):
            Cliente.objects.create(
                tenant=self.tenant, nome="C", cpf_cnpj="11122233344"
            )

    def test_desativar_e_reativar(self):
        cliente = criar_cliente(tenant=self.tenant, nome="José")
        desativar_cliente(cliente, usuario=self.usuario)
        cliente.refresh_from_db()
        self.assertFalse(cliente.ativo)
        reativar_cliente(cliente, usuario=self.usuario)
        cliente.refresh_from_db()
        self.assertTrue(cliente.ativo)


class ClienteViewTest(ClientesBaseTestCase):
    def test_requer_login(self):
        self.client.logout()
        resposta = self.client.get(reverse("customers:lista"))
        self.assertEqual(resposta.status_code, 302)

    def test_usuario_sem_tenant_redireciona(self):
        sem_tenant = User.objects.create_user(
            username="plataforma", password="x1234567"
        )
        self.client.force_login(sem_tenant)
        resposta = self.client.get(reverse("customers:lista"))
        self.assertRedirects(resposta, reverse("dashboard"))

    def test_criar_via_post(self):
        resposta = self.client.post(
            reverse("customers:novo"),
            {"nome": "Maria da Silva", "cpf_cnpj": "123.456.789-00"},
        )
        self.assertEqual(resposta.status_code, 302)
        cliente = Cliente.objects.get(nome="Maria da Silva")
        self.assertEqual(cliente.cpf_cnpj, "12345678900")

    def test_lista_isolada_por_tenant(self):
        Cliente.objects.create(tenant=self.tenant, nome="Visível")
        Cliente.objects.create(tenant=self.outro, nome="Invisível")
        resposta = self.client.get(reverse("customers:lista"))
        conteudo = resposta.content.decode()
        self.assertIn("Visível", conteudo)
        self.assertNotIn("Invisível", conteudo)

    def test_detalhe_alheio_404(self):
        alheio = Cliente.objects.create(tenant=self.outro, nome="Secreto")
        resposta = self.client.get(
            reverse("customers:detalhe", args=[alheio.uuid])
        )
        self.assertEqual(resposta.status_code, 404)

    def test_editar_via_post(self):
        cliente = Cliente.objects.create(tenant=self.tenant, nome="Antigo")
        resposta = self.client.post(
            reverse("customers:editar", args=[cliente.uuid]),
            {"nome": "Novo Nome", "ativo": "on"},
        )
        self.assertEqual(resposta.status_code, 302)
        cliente.refresh_from_db()
        self.assertEqual(cliente.nome, "Novo Nome")

    def test_alternar_status(self):
        cliente = Cliente.objects.create(tenant=self.tenant, nome="Para desativar")
        resposta = self.client.post(
            reverse("customers:alternar_status", args=[cliente.uuid])
        )
        self.assertEqual(resposta.status_code, 302)
        cliente.refresh_from_db()
        self.assertFalse(cliente.ativo)
