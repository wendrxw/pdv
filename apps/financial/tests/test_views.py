from datetime import timedelta
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import User
from apps.companies.models import Tenant

from ..models import ContaFinanceira, ContaReceber, Entrada, Saida
from ..services import (
    criar_conta,
    criar_conta_receber,
    criar_entrada,
    criar_forma_pagamento,
)


class FinancialViewBaseTestCase(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(
            nome="Loja Views Fin", status=Tenant.Status.ATIVO
        )
        self.usuario = User.objects.create_user(
            username="finview", password="senha-12345", tenant=self.tenant
        )
        self.caixa = criar_conta(
            self.tenant, nome="Caixa", tipo=ContaFinanceira.Tipo.CAIXA,
            saldo_inicial=Decimal("500.00"),
        )
        self.client = self.client_class(HTTP_HOST="localhost")
        self.client.force_login(self.usuario)
        hoje = timezone.localdate()
        self.hoje = hoje


class AnaliseViewTest(FinancialViewBaseTestCase):
    url = reverse("financial:analise")

    def test_dashboard_requer_login(self):
        self.client.logout()
        resposta = self.client.get(self.url)
        self.assertEqual(resposta.status_code, 302)

    def test_usuario_sem_tenant_redirecionado(self):
        sem_tenant = User.objects.create_user(
            username="plataforma", password="x1234567"
        )
        client = self.client_class(HTTP_HOST="localhost")
        client.force_login(sem_tenant)
        resposta = client.get(self.url)
        self.assertEqual(resposta.status_code, 302)

    def test_periodo_invalido_normalizado(self):
        resposta = self.client.get(self.url, {"inicio": "bogus", "fim": "2026-01-01"})
        self.assertEqual(resposta.status_code, 200)

    def test_cards_presentes(self):
        resposta = self.client.get(self.url)
        self.assertContains(resposta, "Entradas")
        self.assertContains(resposta, "Resultado")


class EntradaFlowTest(FinancialViewBaseTestCase):
    def test_criar_e_receber_via_http(self):
        categoria_resp = self.client.post(
            reverse("financial:contas"),
            {"tipo_objeto": "categoria", "nome": "Vendas", "tipo_categoria": "ENTRADA"},
        )
        self.assertEqual(categoria_resp.status_code, 302)
        resposta = self.client.post(
            reverse("financial:entrada_nova"),
            {
                "descricao": "Venda balcão",
                "valor": "150.00",
                "conta_financeira": str(self.caixa.pk),
                "data_competencia": self.hoje.strftime("%Y-%m-%d"),
                "acao": "recebido",
            },
        )
        self.assertEqual(resposta.status_code, 302)
        entrada = Entrada.objects.get(descricao="Venda balcão")
        self.assertEqual(entrada.status, Entrada.Status.RECEBIDA)
        self.caixa.refresh_from_db()
        self.assertEqual(self.caixa.saldo_atual, Decimal("650.00"))

    def test_receber_na_detalhe(self):
        entrada = criar_entrada(
            self.tenant,
            descricao="Pendente",
            valor=Decimal("80.00"),
            conta_financeira=self.caixa,
            data_competencia=self.hoje,
        )
        url = reverse("financial:entrada_detalhe", args=[entrada.uuid])
        resposta = self.client.post(url, {"acao": "receber"})
        self.assertEqual(resposta.status_code, 302)
        entrada.refresh_from_db()
        self.assertEqual(entrada.status, Entrada.Status.RECEBIDA)

    def test_cancelar_na_detalhe(self):
        entrada = criar_entrada(
            self.tenant,
            descricao="Para cancelar",
            valor=Decimal("10.00"),
            conta_financeira=self.caixa,
            data_competencia=self.hoje,
        )
        resposta = self.client.post(
            reverse("financial:entrada_detalhe", args=[entrada.uuid]),
            {"acao": "cancelar"},
        )
        self.assertEqual(resposta.status_code, 302)
        entrada.refresh_from_db()
        self.assertEqual(entrada.status, Entrada.Status.CANCELADA)

    def test_lista_com_filtros(self):
        criar_entrada(
            self.tenant,
            descricao="Filtrável única",
            valor=Decimal("1.00"),
            conta_financeira=self.caixa,
            data_competencia=self.hoje,
        )
        resposta = self.client.get(reverse("financial:entradas"), {"q": "Filtrável"})
        self.assertContains(resposta, "Filtrável única")


class SaidaFlowTest(FinancialViewBaseTestCase):
    def test_criar_pagar_cancelar_via_http(self):
        resposta = self.client.post(
            reverse("financial:saida_nova"),
            {
                "descricao": "Aluguel",
                "valor": "300.00",
                "conta_financeira": str(self.caixa.pk),
                "data_competencia": self.hoje.strftime("%Y-%m-%d"),
                "data_vencimento": self.hoje.strftime("%Y-%m-%d"),
                "acao": "pago",
            },
        )
        self.assertEqual(resposta.status_code, 302)
        saida = Saida.objects.get(descricao="Aluguel")
        self.assertEqual(saida.status, Saida.Status.PAGA)
        self.caixa.refresh_from_db()
        self.assertEqual(self.caixa.saldo_atual, Decimal("200.00"))

        resposta = self.client.post(
            reverse("financial:saida_detalhe", args=[saida.uuid]),
            {"acao": "estornar", "motivo": "Débito indevido"},
        )
        self.assertEqual(resposta.status_code, 302)
        self.caixa.refresh_from_db()
        self.assertEqual(self.caixa.saldo_atual, Decimal("500.00"))


class ReceberFlowTest(FinancialViewBaseTestCase):
    def test_criar_parcelada_e_receber_segunda(self):
        resposta = self.client.post(
            reverse("financial:receber_nova"),
            {
                "descricao": "Fiado Maria",
                "cliente_nome": "Maria",
                "valor_total": "1200.00",
                "quantidade_parcelas": "3",
                "primeiro_vencimento": (
                    self.hoje + timedelta(days=30)
                ).strftime("%Y-%m-%d"),
            },
        )
        self.assertEqual(resposta.status_code, 302)
        conta = ContaReceber.objects.get(descricao="Fiado Maria")
        self.assertEqual(conta.parcelas.count(), 3)

        segunda = conta.parcelas.get(numero=2)
        resposta = self.client.post(
            reverse("financial:receber_detalhe", args=[conta.uuid]),
            {
                "acao": "receber_parcela",
                "parcela_uuid": str(segunda.uuid),
                "conta_financeira": str(self.caixa.pk),
            },
        )
        self.assertEqual(resposta.status_code, 302)
        conta.refresh_from_db()
        self.assertEqual(conta.status, ContaReceber.Status.PARCIAL)
        self.assertEqual(conta.valor_recebido, Decimal("400.00"))
        self.assertEqual(conta.valor_pendente, Decimal("800.00"))

    def test_cancelar_conta_http(self):
        conta = criar_conta_receber(
            self.tenant,
            descricao="Cancelar via HTTP",
            valor_total=Decimal("50.00"),
            parcelas=1,
        )
        resposta = self.client.post(
            reverse("financial:receber_detalhe", args=[conta.uuid]),
            {"acao": "cancelar"},
        )
        self.assertEqual(resposta.status_code, 302)
        conta.refresh_from_db()
        self.assertEqual(conta.status, ContaReceber.Status.CANCELADA)


class IsolamentoCrossTenantTest(TestCase):
    """UUID de outro tenant nunca resolve (404) e POST não afeta."""

    def setUp(self):
        self.tenant_a = Tenant.objects.create(
            nome="Tenant A HTTP", status=Tenant.Status.ATIVO
        )
        self.tenant_b = Tenant.objects.create(
            nome="Tenant B HTTP", status=Tenant.Status.ATIVO
        )
        self.usuario_a = User.objects.create_user(
            username="user-a", password="senha-12345", tenant=self.tenant_a
        )
        self.conta_b = criar_conta(
            self.tenant_b, nome="Caixa B", tipo=ContaFinanceira.Tipo.CAIXA,
            saldo_inicial=Decimal("1000.00"),
        )
        self.entrada_b = criar_entrada(
            self.tenant_b,
            descricao="Segredo B",
            valor=Decimal("999.00"),
            conta_financeira=self.conta_b,
            data_competencia=timezone.localdate(),
        )
        self.forma_b = criar_forma_pagamento(
            self.tenant_b, nome="PIX B", codigo="PIX"
        )
        self.client = self.client_class(HTTP_HOST="localhost")
        self.client.force_login(self.usuario_a)

    def test_detalhe_cross_tenant_404(self):
        resposta = self.client.get(
            reverse("financial:entrada_detalhe", args=[self.entrada_b.uuid])
        )
        self.assertEqual(resposta.status_code, 404)

    def test_post_cross_tenant_404(self):
        resposta = self.client.post(
            reverse("financial:entrada_detalhe", args=[self.entrada_b.uuid]),
            {"acao": "cancelar"},
        )
        self.assertEqual(resposta.status_code, 404)
        self.entrada_b.refresh_from_db()
        self.assertEqual(self.entrada_b.status, Entrada.Status.PENDENTE)

    def test_analise_mostra_somente_do_proprio_tenant(self):
        resposta = self.client.get(
            reverse("financial:analise"), {"modo": "COMPETENCIA"}
        )
        content = resposta.content.decode()
        self.assertNotIn("999.00", content)
