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
