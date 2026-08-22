from django.core.exceptions import ValidationError
from django.test import TestCase

from apps.clients.models import (
    ClienteHistorico,
    ClientePlataforma,
    LeadContato,
    Onboarding,
)
from apps.clients.services import (
    ClientServiceError,
    alterar_status,
    ativar_cliente,
    converter_lead,
    criar_cliente,
)
from apps.companies.models import Tenant


class CriarClienteTest(TestCase):
    def setUp(self):
        self.dados = {
            "nome": "Empresa ABC",
            "cpf_cnpj": "11.444.777/0001-61",
            "email": "contato@empresaabc.com.br",
            "telefone_celular": "(16) 99999-0000",
        }

    def test_cria_cliente_com_historico_e_documento_normalizado(self):
        cliente = criar_cliente(**self.dados)
        self.assertEqual(cliente.cpf_cnpj, "11444777000161")
        self.assertEqual(cliente.status, ClientePlataforma.Status.LEAD)
        self.assertTrue(
            ClienteHistorico.objects.filter(
                cliente=cliente, acao=ClienteHistorico.Acao.CRIADO
            ).exists()
        )

    def test_email_normalizado_para_minusculas(self):
        cliente = criar_cliente(**{**self.dados, "email": "CONTATO@EmpresaABC.COM.BR"})
        self.assertEqual(cliente.email, "contato@empresaabc.com.br")

    def test_documento_duplicado_rejeitado(self):
        criar_cliente(**self.dados)
        with self.assertRaises(ValidationError):
            criar_cliente(**self.dados)

    def test_documento_invalido_rejeitado(self):
        with self.assertRaises(ValueError):
            criar_cliente(**{**self.dados, "cpf_cnpj": "11144477734"})

    def test_pj_pode_ser_criado_sem_razao_social_no_onboarding(self):
        """Durante o onboarding (ex.: conversão de lead) a razão social é
        opcional; pode ser complementada antes da ativação."""
        cliente = criar_cliente(**self.dados)
        self.assertEqual(cliente.tipo_pessoa, ClientePlataforma.TipoPessoa.PJ)
        self.assertEqual(cliente.razao_social, "")


class TransicaoStatusTest(TestCase):
    def _cliente(self, status):
        return ClientePlataforma.objects.create(
            nome="Cliente Fluxo",
            cpf_cnpj="11444777000161",
            email="fluxo@empresa.com.br",
            telefone_celular="16999999999",
            status=status,
        )

    def test_fluxo_completo_aprovacao(self):
        cliente = self._cliente(ClientePlataforma.Status.LEAD)
        alterar_status(cliente, ClientePlataforma.Status.EM_ANALISE)
        alterar_status(cliente, ClientePlataforma.Status.PENDENTE)
        alterar_status(cliente, ClientePlataforma.Status.ATIVO)
        cliente.refresh_from_db()
        self.assertEqual(cliente.status, ClientePlataforma.Status.ATIVO)

    def test_transicao_invalida_bloqueada(self):
        cliente = self._cliente(ClientePlataforma.Status.LEAD)
        with self.assertRaises(ClientServiceError):
            alterar_status(cliente, ClientePlataforma.Status.ATIVO)

    def test_cancelamento_a_partir_de_lead(self):
        cliente = self._cliente(ClientePlataforma.Status.LEAD)
        alterar_status(cliente, ClientePlataforma.Status.CANCELADO)
        cliente.refresh_from_db()
        self.assertEqual(cliente.status, ClientePlataforma.Status.CANCELADO)


class AtivacaoClienteTest(TestCase):
    def _cliente(self, status=ClientePlataforma.Status.PENDENTE, com_documento=True):
        return ClientePlataforma.objects.create(
            nome="Empresa Para Ativar",
            cpf_cnpj="11444777000161" if com_documento else None,
            email="ativar@empresa.com.br",
            telefone_celular="16999999999",
            status=status,
        )

    def test_ativacao_cria_tenant_e_onboarding(self):
        cliente = self._cliente()
        ativar_cliente(cliente)
        cliente.refresh_from_db()
        self.assertEqual(cliente.status, ClientePlataforma.Status.ATIVO)
        onboarding = Onboarding.objects.get(cliente=cliente)
        self.assertIsNotNone(onboarding.tenant)
        self.assertEqual(onboarding.tenant.status, Tenant.Status.ATIVO)
        self.assertTrue(
            ClienteHistorico.objects.filter(
                cliente=cliente, acao=ClienteHistorico.Acao.TENANT_ASSOCIADO
            ).exists()
        )

    def test_ativacao_exige_status_pendente(self):
        cliente = self._cliente(status=ClientePlataforma.Status.LEAD)
        with self.assertRaises(ClientServiceError):
            ativar_cliente(cliente)
        # Nenhum tenant criado
        self.assertFalse(Tenant.objects.exists())

    def test_ativacao_exige_documento(self):
        cliente = self._cliente(com_documento=False)
        with self.assertRaises(ClientServiceError) as contexto:
            ativar_cliente(cliente)
        self.assertIn("CPF/CNPJ", str(contexto.exception))
        cliente.refresh_from_db()
        self.assertNotEqual(cliente.status, ClientePlataforma.Status.ATIVO)
        self.assertFalse(Tenant.objects.exists())

    def test_ativacao_de_cliente_ja_ativo_falha(self):
        cliente = self._cliente()
        ativar_cliente(cliente)
        total_tenants = Tenant.objects.count()
        with self.assertRaises(ClientServiceError):
            ativar_cliente(cliente)
        self.assertEqual(Tenant.objects.count(), total_tenants)


class ConverterLeadTest(TestCase):
    def test_converte_lead_em_cliente_sem_tenant(self):
        lead = LeadContato.objects.create(
            nome="Maria Contato",
            email="maria@interessada.com.br",
            telefone="16988887777",
            empresa="Loja da Maria",
            mensagem="Quero conhecer o sistema.",
        )
        cliente = converter_lead(lead)
        lead.refresh_from_db()
        self.assertEqual(lead.status, LeadContato.Status.CONVERTIDO)
        self.assertEqual(lead.cliente_convertido, cliente)
        self.assertEqual(cliente.status, ClientePlataforma.Status.LEAD)
        self.assertFalse(Tenant.objects.exists())

    def test_nao_permite_converter_lead_duas_vezes(self):
        lead = LeadContato.objects.create(
            nome="João",
            email="joao@lead.com.br",
            telefone="16977776666",
            mensagem="Interesse.",
        )
        converter_lead(lead)
        with self.assertRaises(ClientServiceError):
            converter_lead(lead)
