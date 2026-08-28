from django.test import TestCase

from apps.clients.forms import ClientePlataformaForm
from apps.clients.models import ClientePlataforma, Onboarding
from apps.companies.models import Tenant


class ClientePlataformaFormStatusTest(TestCase):
    def _dados(self, status):
        return {
            "tipo_pessoa": ClientePlataforma.TipoPessoa.PJ,
            "nome": "Cliente Form",
            "email": "form@empresa.com.br",
            "telefone_celular": "16999999999",
            "origem": ClientePlataforma.Origem.OUTRO,
            "status": status,
        }

    def test_novo_cliente_ativo_nao_estoura_500(self):
        # Regressão: instância sem pk passada a filter() de FK gerava
        # ValueError ("must be saved") e virava 500 no admin.
        form = ClientePlataformaForm(
            data=self._dados(ClientePlataforma.Status.ATIVO)
        )
        self.assertFalse(form.is_valid())
        self.assertIn("status", form.errors)

    def test_bloqueia_ativacao_direta_no_formulario(self):
        cliente = ClientePlataforma.objects.create(**self._dados(ClientePlataforma.Status.PENDENTE))
        form = ClientePlataformaForm(
            data={**self._dados(ClientePlataforma.Status.ATIVO), "cpf_cnpj": "11444777000161"},
            instance=cliente,
        )
        self.assertFalse(form.is_valid())
        self.assertIn("status", form.errors)

    def test_permite_reativar_suspenso_no_formulario(self):
        cliente = ClientePlataforma.objects.create(
            **self._dados(ClientePlataforma.Status.SUSPENSO)
        )
        form = ClientePlataformaForm(
            data={**self._dados(ClientePlataforma.Status.ATIVO), "cpf_cnpj": "11444777000161"},
            instance=cliente,
        )
        self.assertTrue(form.is_valid(), form.errors)

    def test_permite_salvar_ativo_que_ja_tem_tenant(self):
        cliente = ClientePlataforma.objects.create(**self._dados(ClientePlataforma.Status.ATIVO))
        Onboarding.objects.create(
            cliente=cliente, tenant=Tenant.objects.create(nome="Tenant Form")
        )
        form = ClientePlataformaForm(
            data={**self._dados(ClientePlataforma.Status.ATIVO), "cpf_cnpj": "11444777000161"},
            instance=cliente,
        )
        self.assertTrue(form.is_valid(), form.errors)


class ClientePlataformaAdminAddTest(TestCase):
    """Regressão do 500 em produção ao criar cliente ATIVO pelo admin."""

    def setUp(self):
        from apps.accounts.models import User

        self.usuario = User.objects.create_superuser(
            username="admin-form", email="admin@x.com", password="senha-12345"
        )
        self.client.force_login(self.usuario)

    def _dados(self):
        return {
            "tipo_pessoa": "PJ",
            "nome": "Cliente Admin",
            "email": "admin@empresa.com.br",
            "telefone_celular": "16999999999",
            "origem": "OUTRO",
            "status": "ATIVO",
            "onboarding-TOTAL_FORMS": "0",
            "onboarding-INITIAL_FORMS": "0",
            "onboarding-MIN_NUM_FORMS": "0",
            "onboarding-MAX_NUM_FORMS": "1",
            "historico-TOTAL_FORMS": "0",
            "historico-INITIAL_FORMS": "0",
            "historico-MIN_NUM_FORMS": "0",
            "historico-MAX_NUM_FORMS": "1000",
        }

    def test_add_com_status_ativo_retorna_erro_de_formulario(self):
        resposta = self.client.post(
            "/admin/clients/clienteplataforma/add/", self._dados()
        )
        self.assertEqual(resposta.status_code, 200)  # re-render com erro
        self.assertIn(
            "não podem ser ativados pelo formulário",
            resposta.content.decode(),
        )
        self.assertFalse(ClientePlataforma.objects.exists())

    def test_add_com_status_lead_salva(self):
        dados = self._dados()
        dados["status"] = "LEAD"
        resposta = self.client.post(
            "/admin/clients/clienteplataforma/add/", dados
        )
        self.assertEqual(resposta.status_code, 302)
        self.assertTrue(
            ClientePlataforma.objects.filter(nome="Cliente Admin").exists()
        )
