from decimal import Decimal

from django.test import TestCase
from django.utils import timezone

from apps.accounts.models import User
from apps.companies.models import Tenant
from apps.financial.models import ContaFinanceira, ContaReceber, FormaPagamento
from apps.financial.services import criar_conta, criar_forma_pagamento
from apps.inventory.services import adicionar_estoque
from apps.products.models import Produto

from ..models import Caixa, ItemVenda, Venda
from ..services import (
    SalesError,
    abrir_caixa,
    abrir_venda,
    adicionar_item,
    adicionar_pagamento,
    aplicar_desconto,
    cancelar_venda,
    fechar_caixa,
    finalizar_venda,
    remover_item,
    saldo_esperado_caixa,
    sangria,
    suprimento,
)

ZERO = Decimal("0.00")


class SalesBaseTestCase(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(
            nome="Loja PDV", status=Tenant.Status.ATIVO
        )
        self.operador = User.objects.create_user(
            username="caixista", password="senha-12345", tenant=self.tenant
        )
        self.conta = criar_conta(
            self.tenant,
            nome="Gaveta",
            tipo=ContaFinanceira.Tipo.CAIXA,
            saldo_inicial=ZERO,
        )
        self.dinheiro = criar_forma_pagamento(
            self.tenant, nome="Dinheiro", codigo="DINHEIRO"
        )
        self.fiado = criar_forma_pagamento(
            self.tenant,
            nome="Fiado",
            codigo="OUTRO",
            gera_conta_receber=True,
        )
        self.produto = Produto.objects.create(
            tenant=self.tenant,
            nome="Refrigerante",
            preco_venda=Decimal("10.00"),
        )
        adicionar_estoque(self.produto, Decimal("100"))
        self.caixa = abrir_caixa(
            self.tenant,
            operador=self.operador,
            conta_financeira=self.conta,
            saldo_inicial=Decimal("50.00"),
        )

    def _venda_com_item(self, quantidade=Decimal("2")):
        venda = abrir_venda(self.caixa)
        adicionar_item(venda, self.produto, quantidade, usuario=self.operador)
        venda.refresh_from_db()
        return venda


class AbrirCaixaTest(SalesBaseTestCase):
    def test_segundo_caixa_do_mesmo_operador_bloqueado(self):
        with self.assertRaises(SalesError):
            abrir_caixa(
                self.tenant,
                operador=self.operador,
                conta_financeira=self.conta,
            )

    def test_multi_caixa_operadores_diferentes_permitido(self):
        outro = User.objects.create_user(
            username="colega", password="senha-12345", tenant=self.tenant
        )
        caixa2 = abrir_caixa(
            self.tenant,
            operador=outro,
            conta_financeira=self.conta,
        )
        self.assertEqual(caixa2.status, Caixa.Status.ABERTO)

    def test_conta_de_outro_tenant_rejeitada(self):
        outro_tenant = Tenant.objects.create(nome="Outra Loja")
        conta_alheia = criar_conta(
            outro_tenant, nome="Caixa Alheio", tipo=ContaFinanceira.Tipo.CAIXA
        )
        with self.assertRaises(SalesError):
            abrir_caixa(
                self.tenant, operador=self.operador, conta_financeira=conta_alheia
            )


class SuprimentoSangriaTest(SalesBaseTestCase):
    def test_suprimento_credita_conta_e_registra_historico(self):
        mov = suprimento(
            self.caixa, valor=Decimal("200"), motivo="Troco extra",
            usuario=self.operador,
        )
        self.conta.refresh_from_db()
        self.assertEqual(mov.tipo, "SUPRIMENTO")
        # 50 abertura + 200 suprimento
        self.assertEqual(self.conta.saldo_atual, Decimal("250.00"))

    def test_sangria_debita_conta(self):
        suprimento(self.caixa, valor=Decimal("200"))
        sangria(self.caixa, valor=Decimal("80"), motivo="Depósito")
        self.conta.refresh_from_db()
        self.assertEqual(self.conta.saldo_atual, Decimal("170.00"))

    def test_sangria_sem_saldo_rejeitada(self):
        with self.assertRaises(SalesError):
            sangria(self.caixa, valor=Decimal("999"))

    def test_movimentacao_em_caixa_fechado_rejeitada(self):
        fechar_caixa(self.caixa, saldo_informado=Decimal("50"))
        with self.assertRaises(SalesError):
            suprimento(self.caixa, valor=Decimal("10"))


class FechamentoCaixaTest(SalesBaseTestCase):
    def test_esperado_calculado_das_movimentacoes(self):
        venda = self._venda_com_item(Decimal("3"))  # R$ 30
        adicionar_pagamento(venda, self.dinheiro, venda.total)
        finalizar_venda(venda, usuario=self.operador)
        suprimento(self.caixa, valor=Decimal("20"))
        sangria(self.caixa, valor=Decimal("5"))
        esperado = saldo_esperado_caixa(self.caixa)
        # 50 abertura + 30 venda + 20 suprimento − 5 sangria
        self.assertEqual(esperado, Decimal("95.00"))
        caixa = fechar_caixa(self.caixa, saldo_informado=Decimal("94.00"))
        self.assertEqual(caixa.saldo_final_esperado, Decimal("95.00"))
        self.assertEqual(caixa.diferenca, Decimal("-1.00"))
        self.assertEqual(caixa.status, Caixa.Status.FECHADO)

    def test_venda_aberta_bloqueia_fechamento(self):
        self._venda_com_item()
        with self.assertRaises(SalesError):
            fechar_caixa(self.caixa, saldo_informado=Decimal("70"))


class VendaAvistaTest(SalesBaseTestCase):
    def test_fluxo_completo_credita_financeiro(self):
        venda = self._venda_com_item(Decimal("2"))
        adicionar_pagamento(venda, self.dinheiro, venda.total)
        finalizar_venda(venda, usuario=self.operador)

        venda.refresh_from_db()
        self.assertEqual(venda.status, Venda.Status.FINALIZADA)
        self.assertEqual(venda.total, Decimal("20.00"))
        self.conta.refresh_from_db()
        self.assertEqual(self.conta.saldo_atual, Decimal("70.00"))

    def test_numero_sequencial_por_tenant(self):
        venda1 = self._venda_com_item()
        venda2 = self._venda_com_item()
        self.assertEqual(venda2.numero, venda1.numero + 1)

    def test_preco_congelado_no_momento_da_venda(self):
        venda = self._venda_com_item(Decimal("1"))
        self.produto.preco_venda = Decimal("99.00")
        self.produto.save()
        item = venda.itens.get()
        self.assertEqual(item.preco_unitario, Decimal("10.00"))

    def test_item_merge_soma_quantidade(self):
        venda = self._venda_com_item(Decimal("1"))
        adicionar_item(venda, self.produto, Decimal("2"))
        item = ItemVenda.objects.get(venda=venda)
        self.assertEqual(item.quantidade, Decimal("3"))


class DescontoTest(SalesBaseTestCase):
    def test_desconto_valido_aplicado(self):
        venda = self._venda_com_item(Decimal("5"))  # subtotal 50
        aplicar_desconto(venda, Decimal("5.50"))
        venda.refresh_from_db()
        self.assertEqual(venda.total, Decimal("44.50"))

    def test_desconto_negativo_rejeitado(self):
        venda = self._venda_com_item()
        with self.assertRaises(SalesError):
            aplicar_desconto(venda, Decimal("-1"))

    def test_desconto_maior_que_subtotal_rejeitado(self):
        venda = self._venda_com_item(Decimal("1"))
        with self.assertRaises(SalesError):
            aplicar_desconto(venda, Decimal("10.01"))


class PagamentoTest(SalesBaseTestCase):
    def test_pagamento_excedente_rejeitado(self):
        venda = self._venda_com_item(Decimal("1"))
        with self.assertRaises(SalesError):
            adicionar_pagamento(venda, self.dinheiro, Decimal("11"))

    def test_pagamento_valor_invalido_rejeitado(self):
        venda = self._venda_com_item()
        with self.assertRaises(SalesError):
            adicionar_pagamento(venda, self.dinheiro, ZERO)

    def test_finalizar_sem_pagamentos_rejeitado(self):
        venda = self._venda_com_item()
        with self.assertRaises(SalesError):
            finalizar_venda(venda)

    def test_finalizar_pagamento_parcial_rejeitado(self):
        venda = self._venda_com_item()  # total 20
        adicionar_pagamento(venda, self.dinheiro, Decimal("15"))
        with self.assertRaises(SalesError):
            finalizar_venda(venda)

    def test_finalizar_sem_itens_rejeitado(self):
        venda = abrir_venda(self.caixa)
        with self.assertRaises(SalesError):
            finalizar_venda(venda)

    def test_finalizar_com_forma_registra_pagamento_total(self):
        venda = self._venda_com_item(Decimal("2"))  # total 20
        finalizar_venda(venda, usuario=self.operador, forma_pagamento=self.dinheiro)
        venda.refresh_from_db()
        self.assertEqual(venda.status, Venda.Status.FINALIZADA)
        pagamento = venda.pagamentos.get()
        self.assertEqual(pagamento.forma_pagamento, self.dinheiro)
        self.assertEqual(pagamento.valor, Decimal("20.00"))
        self.conta.refresh_from_db()
        self.assertEqual(self.conta.saldo_atual, Decimal("70.00"))

    def test_finalizar_com_forma_completa_pagamento_parcial(self):
        venda = self._venda_com_item(Decimal("2"))  # total 20
        adicionar_pagamento(venda, self.dinheiro, Decimal("5"))
        finalizar_venda(venda, usuario=self.operador, forma_pagamento=self.fiado)
        venda.refresh_from_db()
        self.assertEqual(venda.status, Venda.Status.FINALIZADA)
        self.assertEqual(
            sum(p.valor for p in venda.pagamentos.all()), Decimal("20.00")
        )

    def test_finalizar_com_forma_de_outro_tenant_rejeitado(self):
        outro_tenant = Tenant.objects.create(nome="Outra Loja")
        forma_alheia = criar_forma_pagamento(
            outro_tenant, nome="Cartão alheio", codigo="OUTRO"
        )
        venda = self._venda_com_item(Decimal("2"))
        with self.assertRaises(SalesError):
            finalizar_venda(venda, forma_pagamento=forma_alheia)


class VendaFiadoTest(SalesBaseTestCase):
    def test_forma_fiado_gera_conta_receber(self):
        venda = self._venda_com_item(Decimal("3"))  # 30
        adicionar_pagamento(venda, self.fiado, venda.total)
        finalizar_venda(venda, usuario=self.operador)

        recebivel = ContaReceber.objects.for_tenant(self.tenant).get(
            origem=ContaReceber.Origem.VENDA, referencia_uuid=venda.uuid
        )
        self.assertEqual(recebivel.valor_total, Decimal("30.00"))
        self.assertEqual(recebivel.parcelas.count(), 1)
        # Fiado NÃO credita a conta na venda.
        self.conta.refresh_from_db()
        self.assertEqual(self.conta.saldo_atual, Decimal("50.00"))

    def test_cancelar_venda_fiada_cancela_recebivel(self):
        venda = self._venda_com_item(Decimal("3"))
        adicionar_pagamento(venda, self.fiado, venda.total)
        finalizar_venda(venda)
        cancelar_venda(venda, motivo="Cliente desistiu", usuario=self.operador)
        recebivel = ContaReceber.objects.get(referencia_uuid=venda.uuid)
        self.assertEqual(recebivel.status, ContaReceber.Status.CANCELADA)


class CancelamentoVendaTest(SalesBaseTestCase):
    def test_cancelar_venda_aberta(self):
        venda = self._venda_com_item(Decimal("4"))
        cancelar_venda(venda, motivo="Erro do operador", usuario=self.operador)
        venda.refresh_from_db()
        self.assertEqual(venda.status, Venda.Status.CANCELADA)

    def test_cancelar_venda_finalizada_estorna(self):
        venda = self._venda_com_item(Decimal("2"))
        adicionar_pagamento(venda, self.dinheiro, venda.total)
        finalizar_venda(venda)  # caixa: 50 → 70
        cancelar_venda(venda, motivo="Arrependimento", usuario=self.operador)

        self.conta.refresh_from_db()
        self.assertEqual(self.conta.saldo_atual, Decimal("50.00"))

        from apps.financial.models import MovimentacaoFinanceira

        movs = list(MovimentacaoFinanceira.objects.filter(referencia_uuid=venda.uuid))
        tipos = sorted(m.tipo for m in movs)
        self.assertIn("ENTRADA", tipos)
        self.assertIn("ESTORNO_ENTRADA", tipos)

    def test_cancelar_sem_motivo_rejeitado(self):
        venda = self._venda_com_item()
        with self.assertRaises(SalesError):
            cancelar_venda(venda, motivo="")

    def test_remover_item(self):
        venda = self._venda_com_item(Decimal("2"))
        item = venda.itens.get()
        remover_item(venda, item, usuario=self.operador)
        self.assertFalse(ItemVenda.objects.filter(pk=item.pk).exists())


class AbrirCaixaAutomaticoTest(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(nome="Loja Zero")
        self.operador = User.objects.create_user(
            username="zero", password="senha-12345", tenant=self.tenant
        )

    def test_abrir_caixa_cria_conta_principal_e_formas_padrao(self):
        caixa = abrir_caixa(self.tenant, operador=self.operador)
        self.assertEqual(caixa.conta_financeira.nome, "Caixa Principal")
        self.assertEqual(caixa.conta_financeira.tipo, ContaFinanceira.Tipo.CAIXA)
        codigos = set(
            FormaPagamento.objects.for_tenant(self.tenant).values_list(
                "codigo", flat=True
            )
        )
        self.assertEqual(
            codigos, {"DINHEIRO", "CREDITO", "DEBITO", "PIX"}
        )

    def test_aberturas_seguintes_reutilizam_conta_principal(self):
        abrir_caixa(self.tenant, operador=self.operador)
        outro = User.objects.create_user(
            username="colega-zero", password="senha-12345", tenant=self.tenant
        )
        caixa = abrir_caixa(self.tenant, operador=outro)
        self.assertEqual(caixa.conta_financeira.nome, "Caixa Principal")
        self.assertEqual(ContaFinanceira.objects.for_tenant(self.tenant).count(), 1)

    def test_conta_informada_ainda_e_suportada(self):
        conta = criar_conta(
            self.tenant, nome="Gaveta", tipo=ContaFinanceira.Tipo.CAIXA
        )
        caixa = abrir_caixa(
            self.tenant, operador=self.operador, conta_financeira=conta
        )
        self.assertEqual(caixa.conta_financeira, conta)


class VendasMultiTenantTest(TestCase):
    def setUp(self):
        self.tenant_a = Tenant.objects.create(nome="Loja A")
        self.tenant_b = Tenant.objects.create(nome="Loja B")
        self.user_a = User.objects.create_user(
            username="op-a", password="senha-12345", tenant=self.tenant_a
        )
        self.conta_a = criar_conta(
            self.tenant_a, nome="Caixa A", tipo=ContaFinanceira.Tipo.CAIXA
        )
        self.dinheiro_a = criar_forma_pagamento(
            self.tenant_a, nome="Dinheiro", codigo="DINHEIRO"
        )
        self.produto_b = Produto.objects.create(
            tenant=self.tenant_b, nome="Produto B", preco_venda=Decimal("7.00")
        )

    def test_numeracao_independente_por_tenant(self):
        caixa = abrir_caixa(
            self.tenant_a, operador=self.user_a, conta_financeira=self.conta_a
        )
        venda = abrir_venda(caixa)
        self.assertEqual(venda.numero, 1)

    def test_produto_de_outro_tenant_rejeitado_na_venda(self):
        caixa = abrir_caixa(
            self.tenant_a, operador=self.user_a, conta_financeira=self.conta_a
        )
        venda = abrir_venda(caixa)
        with self.assertRaises(SalesError):
            adicionar_item(venda, self.produto_b, Decimal("1"))

    def test_isolamento_queryset(self):
        caixa = abrir_caixa(
            self.tenant_a, operador=self.user_a, conta_financeira=self.conta_a
        )
        venda = abrir_venda(caixa)
        venda.data_finalizacao = timezone.now()
        venda.save()
        self.assertEqual(Venda.objects.for_tenant(self.tenant_b).count(), 0)
        self.assertEqual(Venda.objects.for_tenant(self.tenant_a).count(), 1)


class SemCaixaAbertoTest(SalesBaseTestCase):
    def test_venda_exige_caixa_aberto(self):
        fechar_caixa(self.caixa, saldo_informado=Decimal("50"))
        with self.assertRaises(SalesError):
            abrir_venda(self.caixa)
