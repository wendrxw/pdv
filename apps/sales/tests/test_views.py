from decimal import Decimal

from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import User
from apps.companies.models import Tenant
from apps.financial.models import ContaFinanceira
from apps.financial.services import criar_conta, criar_forma_pagamento
from apps.inventory.services import adicionar_estoque
from apps.products.models import Produto

from ..models import Caixa, Venda
from ..services import abrir_caixa, abrir_venda, adicionar_item


class ViewsBaseTestCase(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(
            nome="Loja Web", status=Tenant.Status.ATIVO
        )
        self.user = User.objects.create_user(
            username="operador", password="senha-12345", tenant=self.tenant
        )
        self.conta = criar_conta(
            self.tenant,
            nome="Gaveta",
            tipo=ContaFinanceira.Tipo.CAIXA,
        )
        self.dinheiro = criar_forma_pagamento(
            self.tenant, nome="Dinheiro", codigo="DINHEIRO"
        )
        self.produto = Produto.objects.create(
            tenant=self.tenant,
            nome="Cerveja",
            sku="CERV-1",
            preco_venda=Decimal("12.00"),
        )
        adicionar_estoque(self.produto, Decimal("50"))
        self.caixa = abrir_caixa(
            self.tenant,
            operador=self.user,
            conta_financeira=self.conta,
            saldo_inicial=Decimal("30.00"),
        )
        self.client.force_login(self.user)


def criar_venda_com_item(caixa, produto, usuario, quantidade=Decimal("2")):
    venda = abrir_venda(caixa)
    adicionar_item(venda, produto, quantidade, usuario=usuario)
    return venda


class PdvHomeViewTest(ViewsBaseTestCase):
    def test_requer_login(self):
        self.client.logout()
        resposta = self.client.get(reverse("sales:pdv"))
        self.assertEqual(resposta.status_code, 302)
        self.assertIn("/login/", resposta.url)

    def test_get_mostra_caixas_abertos(self):
        resposta = self.client.get(reverse("sales:pdv"))
        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, "Frente de caixa")

    def test_post_abre_novo_caixa_bloqueado_operador_duplicado(self):
        resposta = self.client.post(
            reverse("sales:pdv"),
            {
                "conta_financeira": str(self.conta.pk),
                "saldo_inicial": "10",
            },
        )
        # Operador já possui caixa aberto → erro exibido.
        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, "já possui um caixa aberto")

    def test_usuario_sem_tenant_redireciona_dashboard(self):
        staff = User.objects.create_user(username="staffx", password="senha-12345")
        staff.is_staff = True
        staff.save()
        self.client.force_login(staff)
        resposta = self.client.get(reverse("sales:pdv"))
        self.assertRedirects(resposta, reverse("dashboard"))


class NovaVendaViewTest(ViewsBaseTestCase):
    def test_post_cria_venda_e_redireciona_para_tela(self):
        resposta = self.client.post(
            reverse("sales:nova_venda", args=[self.caixa.uuid])
        )
        venda = Venda.objects.get(caixa=self.caixa)
        self.assertRedirects(resposta, reverse("sales:venda_tela", args=[venda.uuid]))
        self.assertEqual(venda.numero, 1)


class VendaTelaViewTest(ViewsBaseTestCase):
    def setUp(self):
        super().setUp()
        self.venda = criar_venda_com_item(
            self.caixa, self.produto, self.user, Decimal("2")
        )

    def test_get_renderiza_carrinho(self):
        resposta = self.client.get(
            reverse("sales:venda_tela", args=[self.venda.uuid])
        )
        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, "Cerveja")
        self.assertContains(resposta, "24.00")

    def test_post_adiciona_item(self):
        resposta = self.client.post(
            reverse("sales:venda_tela", args=[self.venda.uuid]),
            {
                "acao": "add_item",
                "produto": str(self.produto.uuid),
                "quantidade": "3",
            },
        )
        self.assertEqual(resposta.status_code, 302)
        self.venda.refresh_from_db()
        self.assertEqual(self.venda.total, Decimal("60.00"))

    def test_post_desconto(self):
        resposta = self.client.post(
            reverse("sales:venda_tela", args=[self.venda.uuid]),
            {"acao": "desconto", "desconto": "4"},
        )
        self.assertEqual(resposta.status_code, 302)
        self.venda.refresh_from_db()
        self.assertEqual(self.venda.desconto, Decimal("4.00"))

    def test_post_finaliza_venda(self):
        self.client.post(
            reverse("sales:venda_tela", args=[self.venda.uuid]),
            {
                "acao": "pagamento",
                "forma_pagamento": str(self.dinheiro.uuid),
                "valor": "24.00",
            },
        )
        resposta = self.client.post(
            reverse("sales:venda_tela", args=[self.venda.uuid]),
            {"acao": "finalizar"},
        )
        self.venda.refresh_from_db()
        self.assertEqual(self.venda.status, Venda.Status.FINALIZADA)
        self.assertRedirects(
            resposta, reverse("sales:venda_detalhe", args=[self.venda.uuid])
        )

    def test_post_cancelar_exige_motivo(self):
        resposta = self.client.post(
            reverse("sales:venda_tela", args=[self.venda.uuid]),
            {"acao": "cancelar", "motivo": ""},
        )
        self.assertEqual(resposta.status_code, 302)
        self.venda.refresh_from_db()
        self.assertEqual(self.venda.status, Venda.Status.ABERTA)

    def test_cross_tenant_404(self):
        outro = Tenant.objects.create(nome="Outra")
        outro_user = User.objects.create_user(
            username="outro", password="senha-12345", tenant=outro
        )
        self.client.force_login(outro_user)
        resposta = self.client.get(
            reverse("sales:venda_tela", args=[self.venda.uuid])
        )
        self.assertEqual(resposta.status_code, 404)


class ProdutoBuscaApiTest(ViewsBaseTestCase):
    def test_busca_por_codigo_ou_nome(self):
        url = reverse("sales:produto_busca")
        resposta = self.client.get(url, {"q": "cerveja"})
        dados = resposta.json()
        self.assertEqual(dados["resultados"][0]["nome"], "Cerveja")

    def test_busca_por_sku(self):
        resposta = self.client.get(
            reverse("sales:produto_busca"), {"q": "CERV-1"}
        )
        self.assertEqual(len(resposta.json()["resultados"]), 1)

    def test_isolamento_na_busca(self):
        Produto.objects.create(
            tenant=Tenant.objects.create(nome="X"),
            nome="Produto Secreto",
            preco_venda=Decimal("1.00"),
        )
        resposta = self.client.get(
            reverse("sales:produto_busca"), {"q": "secreto"}
        )
        self.assertEqual(resposta.json()["resultados"], [])


class VendasHistoricoViewsTest(ViewsBaseTestCase):
    def test_lista_e_detalhe(self):
        venda = criar_venda_com_item(
            self.caixa, self.produto, self.user, Decimal("1")
        )
        lista = self.client.get(reverse("sales:vendas"))
        self.assertContains(lista, "#1")
        detalhe = self.client.get(reverse("sales:venda_detalhe", args=[venda.uuid]))
        self.assertContains(detalhe, "Venda #1")

    def test_cancelar_via_detalhe(self):
        venda = criar_venda_com_item(
            self.caixa, self.produto, self.user, Decimal("1")
        )
        resposta = self.client.post(
            reverse("sales:venda_detalhe", args=[venda.uuid]),
            {"motivo": "Teste"},
        )
        self.assertEqual(resposta.status_code, 302)
        venda.refresh_from_db()
        self.assertEqual(venda.status, Venda.Status.CANCELADA)


class CaixaViewsTest(ViewsBaseTestCase):
    def test_lista_caixas(self):
        resposta = self.client.get(reverse("sales:caixas"))
        self.assertEqual(resposta.status_code, 200)

    def test_movimentacao_suprimento_via_view(self):
        resposta = self.client.post(
            reverse("sales:movimentacao_caixa", args=[self.caixa.uuid]),
            {"tipo": "SUPRIMENTO", "valor": "15", "motivo": "troco"},
        )
        self.assertEqual(resposta.status_code, 302)
        self.conta.refresh_from_db()
        self.assertEqual(self.conta.saldo_atual, Decimal("45.00"))

    def test_fechar_caixa_via_view(self):
        resposta = self.client.post(
            reverse("sales:caixa_detalhe", args=[self.caixa.uuid]),
            {"saldo_informado": "30.00", "observacao": "ok"},
        )
        self.assertEqual(resposta.status_code, 302)
        self.caixa.refresh_from_db()
        self.assertEqual(self.caixa.status, Caixa.Status.FECHADO)
