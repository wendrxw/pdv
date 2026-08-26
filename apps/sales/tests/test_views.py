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


class AbrirCaixaRapidoViewsTest(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(
            nome="Loja Rápida", status=Tenant.Status.ATIVO
        )
        self.user = User.objects.create_user(
            username="operador-rapido", password="senha-12345", tenant=self.tenant
        )
        self.client.force_login(self.user)

    def test_pdv_post_abre_caixa_sem_selecionar_conta(self):
        resposta = self.client.post(
            reverse("sales:pdv"), {"saldo_inicial": "50"}, follow=True
        )
        self.assertEqual(resposta.status_code, 200)
        caixa = Caixa.objects.get(operador=self.user)
        self.assertEqual(caixa.conta_financeira.nome, "Caixa Principal")
        self.assertEqual(caixa.saldo_inicial, Decimal("50.00"))

    def test_nova_venda_rapida_abre_caixa_automaticamente(self):
        resposta = self.client.post(reverse("sales:nova_venda_rapida"))
        venda = Venda.objects.get()
        self.assertRedirects(
            resposta, reverse("sales:venda_tela", args=[venda.uuid])
        )
        self.assertEqual(venda.caixa.conta_financeira.nome, "Caixa Principal")
        self.assertEqual(venda.caixa.operador, self.user)


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
        self.assertContains(resposta, "R$ 24,00")

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

    def test_post_cliente_define_nome(self):
        resposta = self.client.post(
            reverse("sales:venda_tela", args=[self.venda.uuid]),
            {"acao": "cliente", "cliente_nome": "Maria da Silva"},
        )
        self.assertEqual(resposta.status_code, 302)
        self.venda.refresh_from_db()
        self.assertEqual(self.venda.cliente_nome, "Maria da Silva")

    def test_post_cliente_com_uuid_associa_cadastrado(self):
        from apps.customers.models import Cliente

        cliente = Cliente.objects.create(
            tenant=self.tenant, nome="Maria Cadastrada", cpf_cnpj="12345678900"
        )
        resposta = self.client.post(
            reverse("sales:venda_tela", args=[self.venda.uuid]),
            {"acao": "cliente", "cliente": str(cliente.uuid)},
        )
        self.assertEqual(resposta.status_code, 302)
        self.venda.refresh_from_db()
        self.assertEqual(self.venda.cliente, cliente)
        self.assertEqual(self.venda.cliente_nome, "Maria Cadastrada")

    def test_post_cliente_alheio_falha(self):
        from apps.companies.models import Tenant
        from apps.customers.models import Cliente

        alheio = Cliente.objects.create(
            tenant=Tenant.objects.create(nome="Alheia"), nome="Invasor"
        )
        resposta = self.client.post(
            reverse("sales:venda_tela", args=[self.venda.uuid]),
            {"acao": "cliente", "cliente": str(alheio.uuid)},
            follow=True,
        )
        self.assertEqual(resposta.status_code, 200)
        self.venda.refresh_from_db()
        self.assertIsNone(self.venda.cliente)

    def test_post_alterar_item_recalcula_total(self):
        item = self.venda.itens.get()
        resposta = self.client.post(
            reverse("sales:venda_tela", args=[self.venda.uuid]),
            {"acao": "alterar_item", "item": str(item.uuid), "quantidade": "5"},
        )
        self.assertEqual(resposta.status_code, 302)
        self.venda.refresh_from_db()
        item.refresh_from_db()
        self.assertEqual(item.quantidade, Decimal("5.000"))
        self.assertEqual(self.venda.total, Decimal("60.00"))

    def test_post_alterar_item_quantidade_zero_falha(self):
        item = self.venda.itens.get()
        resposta = self.client.post(
            reverse("sales:venda_tela", args=[self.venda.uuid]),
            {"acao": "alterar_item", "item": str(item.uuid), "quantidade": "0"},
            follow=True,
        )
        self.assertEqual(resposta.status_code, 200)
        self.venda.refresh_from_db()
        self.assertEqual(self.venda.total, Decimal("24.00"))

    def test_post_cliente_em_venda_finalizada_falha(self):
        from ..services import finalizar_venda

        finalizar_venda(
            self.venda, usuario=self.user, forma_pagamento=self.dinheiro
        )
        resposta = self.client.post(
            reverse("sales:venda_tela", args=[self.venda.uuid]),
            {"acao": "cliente", "cliente_nome": "Tarde demais"},
            follow=True,
        )
        self.assertEqual(resposta.status_code, 200)
        self.venda.refresh_from_db()
        self.assertEqual(self.venda.cliente_nome, "")

    def test_get_exibe_catalogo_de_produtos(self):
        resposta = self.client.get(
            reverse("sales:venda_tela", args=[self.venda.uuid])
        )
        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, "Venda atual")
        self.assertContains(resposta, "Estoque:")

    def test_post_finaliza_venda(self):
        resposta = self.client.post(
            reverse("sales:venda_tela", args=[self.venda.uuid]),
            {
                "acao": "finalizar",
                "forma_pagamento": str(self.dinheiro.uuid),
            },
        )
        self.venda.refresh_from_db()
        self.assertEqual(self.venda.status, Venda.Status.FINALIZADA)
        self.assertEqual(self.venda.pagamentos.count(), 1)
        self.assertEqual(
            self.venda.pagamentos.get().forma_pagamento, self.dinheiro
        )
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

    def test_post_pagamento_aceita_uuid_da_forma(self):
        resposta = self.client.post(
            reverse("sales:venda_tela", args=[self.venda.uuid]),
            {
                "acao": "pagamento",
                "forma_pagamento": str(self.dinheiro.uuid),
                "valor": "24.00",
            },
            follow=True,
        )
        self.assertEqual(resposta.status_code, 200)
        self.venda.refresh_from_db()
        self.assertEqual(self.venda.pagamentos.count(), 1)

    def test_post_pagamento_com_pk_invalido_mostra_mensagem(self):
        resposta = self.client.post(
            reverse("sales:venda_tela", args=[self.venda.uuid]),
            {
                "acao": "pagamento",
                "forma_pagamento": str(self.dinheiro.pk),
                "valor": "24.00",
            },
            follow=True,
        )
        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, "Pagamento inválido")
        self.assertEqual(self.venda.pagamentos.count(), 0)

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
