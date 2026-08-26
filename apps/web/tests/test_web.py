from django.test import TestCase

from apps.accounts.models import User
from apps.clients.models import LeadContato
from apps.companies.models import Tenant


class LandingPageTest(TestCase):
    def test_landing_retorna_200(self):
        resposta = self.client.get("/")
        self.assertEqual(resposta.status_code, 200)

    def test_landing_em_portugues_com_seo(self):
        resposta = self.client.get("/")
        conteudo = resposta.content.decode()
        self.assertIn('lang="pt-BR"', conteudo)
        self.assertIn("<title>", conteudo)
        self.assertIn('name="description"', conteudo)
        self.assertIn("Gestão simples para o seu negócio", conteudo)
        self.assertIn('property="og:title"', conteudo)

    def test_landing_apresenta_secoes_e_cta(self):
        resposta = self.client.get("/")
        conteudo = resposta.content.decode()
        for termo in ("Recursos", "Benefícios", "Como funciona", "Fale conosco"):
            self.assertIn(termo, conteudo)


class ContatoTest(TestCase):
    def test_formulario_contato_renderiza(self):
        resposta = self.client.get("/contato/")
        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, "csrfmiddlewaretoken")

    def test_post_cria_lead_sem_tenant_nem_cliente(self):
        from apps.companies.models import Tenant

        resposta = self.client.post(
            "/contato/",
            {
                "nome": "Visitante Teste",
                "email": "visitante@teste.com.br",
                "telefone": "(16) 90000-0000",
                "empresa": "Empresa do Visitante",
                "mensagem": "Gostaria de uma demonstração.",
            },
        )
        self.assertEqual(resposta.status_code, 302)
        lead = LeadContato.objects.get(email="visitante@teste.com.br")
        self.assertEqual(lead.nome, "Visitante Teste")
        self.assertEqual(lead.status, LeadContato.Status.NOVO)
        # Contato público NÃO cria tenant nem cliente ativo
        self.assertFalse(Tenant.objects.exists())

    def test_post_invalido_nao_cria_lead(self):
        resposta = self.client.post(
            "/contato/",
            {"nome": "", "email": "email-invalido", "telefone": "", "mensagem": ""},
        )
        self.assertEqual(resposta.status_code, 200)
        self.assertFalse(LeadContato.objects.exists())

    def test_pagina_de_sucesso(self):
        resposta = self.client.get("/contato/obrigado/")
        self.assertEqual(resposta.status_code, 200)


class DashboardTest(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(
            nome="Loja Home", status=Tenant.Status.ATIVO
        )
        self.user = User.objects.create_user(
            username="operador-home", password="senha-12345", tenant=self.tenant
        )
        self.client.force_login(self.user)

    def test_requer_login(self):
        self.client.logout()
        resposta = self.client.get("/app/")
        self.assertEqual(resposta.status_code, 302)

    def test_tela_de_boas_vindas(self):
        resposta = self.client.get("/app/")
        self.assertEqual(resposta.status_code, 200)
        conteudo = resposta.content.decode()
        self.assertIn("BEM-VINDO(A)!", conteudo)
        self.assertIn("Bem-vindo ao seu PDV!", conteudo)
        self.assertIn("Tenha um ótimo dia de trabalho!", conteudo)
        self.assertIn("Hoje é", conteudo)

    def test_sem_indicadores_ou_tabelas(self):
        resposta = self.client.get("/app/")
        conteudo = resposta.content.decode()
        self.assertNotIn("Recebido hoje", conteudo)
        self.assertNotIn("Total no período", conteudo)
        self.assertNotIn("<table", conteudo)

    def test_logo_e_marca_dagua_presentes(self):
        resposta = self.client.get("/app/")
        conteudo = resposta.content.decode()
        self.assertIn("img/logo.png", conteudo)
        self.assertIn("img/logo-simbolo.png", conteudo)

    def test_nome_do_operador_autenticado(self):
        resposta = self.client.get("/app/")
        self.assertContains(resposta, "operador-home")

    def test_plataforma_ve_painel_admin(self):
        staff = User.objects.create_user(
            username="staff-home", password="senha-12345"
        )
        staff.is_staff = True
        staff.save()
        self.client.force_login(staff)
        resposta = self.client.get("/app/")
        self.assertContains(resposta, "Abrir painel administrativo")

    def test_sem_tenant_exibe_mensagem_de_vinculo(self):
        usuario = User.objects.create_user(
            username="sem-tenant-home", password="senha-12345"
        )
        self.client.force_login(usuario)
        resposta = self.client.get("/app/")
        self.assertContains(resposta, "não está vinculado a um ambiente")


class LoginLogoutTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="operador", password="senha-123"
        )

    def test_login_com_credenciais_validas(self):
        resposta = self.client.post(
            "/login/", {"username": "operador", "password": "senha-123"}
        )
        self.assertEqual(resposta.status_code, 302)

    def test_login_com_credenciais_invalidas(self):
        resposta = self.client.post(
            "/login/", {"username": "operador", "password": "errada"}
        )
        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, "inválidos")

    def test_logout_via_post(self):
        self.client.force_login(self.user)
        resposta = self.client.post("/logout/")
        self.assertEqual(resposta.status_code, 302)

    def test_senhas_hashadas_com_bcrypt(self):
        from django.conf import settings

        self.assertTrue(
            settings.PASSWORD_HASHERS[0].startswith(
                "django.contrib.auth.hashers.BCrypt"
            )
        )
        self.user.refresh_from_db()
        self.assertIn("$", self.user.password)  # formato hasher$senha_hash
