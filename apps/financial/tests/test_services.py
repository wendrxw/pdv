from datetime import date, timedelta
from decimal import Decimal

from django.db import OperationalError
from django.test import TestCase, TransactionTestCase
from django.utils import timezone

from apps.accounts.models import User
from apps.companies.models import Tenant

from ..models import (
    ContaFinanceira,
    ContaReceber,
    Entrada,
    MovimentacaoFinanceira,
    ParcelaReceber,
    Saida,
)
from ..services import (
    FinancialError,
    cancelar_conta_receber,
    cancelar_entrada,
    criar_categoria,
    criar_conta,
    criar_conta_receber,
    criar_entrada,
    criar_forma_pagamento,
    criar_saida,
    dividir_em_parcelas,
    estornar_pagamento_saida,
    estornar_recebimento_entrada,
    pagar_saida,
    receber_entrada,
    receber_parcela,
)

ZERO = Decimal("0.00")


class FinancialBaseTestCase(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(
            nome="Loja Financeira", status=Tenant.Status.ATIVO
        )
        self.usuario = User.objects.create_user(
            username="financ", password="senha-12345", tenant=self.tenant
        )
        self.caixa = criar_conta(
            self.tenant, nome="Caixa", tipo=ContaFinanceira.Tipo.CAIXA,
            saldo_inicial=Decimal("1000.00"),
        )


class CategoriaEContaTest(FinancialBaseTestCase):
    def test_criar_categoria(self):
        categoria = criar_categoria(
            self.tenant, nome="Vendas", tipo="ENTRADA"
        )
        self.assertEqual(categoria.tenant, self.tenant)
        self.assertTrue(categoria.ativo)

    def test_subcategoria_de_outro_tenant_rejeitada(self):
        outro = Tenant.objects.create(nome="Outra Fin")
        pai_alheio = criar_categoria(outro, nome="Despesas", tipo="SAIDA")
        with self.assertRaises(FinancialError):
            criar_categoria(
                self.tenant, nome="Aluguel", tipo="SAIDA",
                categoria_pai=pai_alheio,
            )

    def test_hierarquia_max_um_nivel(self):
        raiz = criar_categoria(self.tenant, nome="Operacionais", tipo="AMBOS")
        filho = criar_categoria(
            self.tenant, nome="Energia", tipo="SAIDA", categoria_pai=raiz
        )
        with self.assertRaises(FinancialError):
            criar_categoria(
                self.tenant, nome="Luz", tipo="SAIDA", categoria_pai=filho
            )

    def test_saldo_inicial_define_saldo_atual(self):
        self.assertEqual(self.caixa.saldo_atual, Decimal("1000.00"))


class EntradaTest(FinancialBaseTestCase):
    hoje = timezone.localdate()

    def test_entrada_pendente_nao_altera_saldo(self):
        criar_entrada(
            self.tenant,
            descricao="Venda futura",
            valor=Decimal("500.00"),
            conta_financeira=self.caixa,
            data_competencia=self.hoje,
        )
        self.caixa.refresh_from_db()
        self.assertEqual(self.caixa.saldo_atual, Decimal("1000.00"))

    def test_recebimento_credita_conta(self):
        entrada = criar_entrada(
            self.tenant,
            descricao="Venda",
            valor=Decimal("500.00"),
            conta_financeira=self.caixa,
            data_competencia=self.hoje,
        )
        entrada = receber_entrada(entrada, usuario=self.usuario)
        self.caixa.refresh_from_db()
        self.assertEqual(self.caixa.saldo_atual, Decimal("1500.00"))
        self.assertEqual(entrada.status, Entrada.Status.RECEBIDA)
        mov = MovimentacaoFinanceira.objects.get(referencia_uuid=entrada.uuid)
        self.assertEqual(mov.tipo, MovimentacaoFinanceira.Tipo.ENTRADA)
        self.assertEqual(mov.valor, Decimal("500.00"))

    def test_cancelada_nao_afeta_saldo_e_nao_recebe(self):
        entrada = criar_entrada(
            self.tenant,
            descricao="Cancelada",
            valor=Decimal("100.00"),
            conta_financeira=self.caixa,
            data_competencia=self.hoje,
        )
        cancelar_entrada(entrada)
        with self.assertRaises(FinancialError):
            receber_entrada(entrada)
        self.caixa.refresh_from_db()
        self.assertEqual(self.caixa.saldo_atual, Decimal("1000.00"))

    def test_recebida_nao_pode_ser_cancelada_mas_estorno_funciona(self):
        entrada = criar_entrada(
            self.tenant,
            descricao="Recebida",
            valor=Decimal("300.00"),
            conta_financeira=self.caixa,
            data_competencia=self.hoje,
        )
        receber_entrada(entrada)
        with self.assertRaises(FinancialError):
            cancelar_entrada(entrada)
        estornar_recebimento_entrada(entrada, motivo="Erro de digitação")
        self.caixa.refresh_from_db()
        self.assertEqual(self.caixa.saldo_atual, Decimal("1000.00"))
        estorno = MovimentacaoFinanceira.objects.get(
            tipo=MovimentacaoFinanceira.Tipo.ESTORNO_ENTRADA
        )
        self.assertIsNotNone(estorno.estorno_de_id)
        self.assertEqual(estorno.valor, Decimal("300.00"))

    def test_estorno_exige_motivo(self):
        entrada = criar_entrada(
            self.tenant,
            descricao="X",
            valor=Decimal("50.00"),
            conta_financeira=self.caixa,
            data_competencia=self.hoje,
        )
        receber_entrada(entrada)
        with self.assertRaises(FinancialError):
            estornar_recebimento_entrada(entrada, motivo="  ")

    def test_estorno_duplo_bloqueado(self):
        entrada = criar_entrada(
            self.tenant,
            descricao="X",
            valor=Decimal("50.00"),
            conta_financeira=self.caixa,
            data_competencia=self.hoje,
        )
        receber_entrada(entrada)
        estornar_recebimento_entrada(entrada, motivo="uma vez")
        with self.assertRaises(FinancialError):
            estornar_recebimento_entrada(entrada, motivo="duas vezes")

    def test_valor_negativo_rejeitado(self):
        with self.assertRaises(FinancialError):
            criar_entrada(
                self.tenant,
                descricao="Negativa",
                valor=Decimal("-10.00"),
                conta_financeira=self.caixa,
                data_competencia=self.hoje,
            )

    def test_conta_de_outro_tenant_rejeitada(self):
        outro = Tenant.objects.create(nome="Outro Fin 2")
        conta_alheia = criar_conta(
            outro, nome="Caixa alheio", tipo=ContaFinanceira.Tipo.CAIXA
        )
        with self.assertRaises(FinancialError):
            criar_entrada(
                self.tenant,
                descricao="Invasão",
                valor=Decimal("10.00"),
                conta_financeira=conta_alheia,
                data_competencia=self.hoje,
            )


class SaidaTest(FinancialBaseTestCase):
    hoje = timezone.localdate()

    def _saida(self, valor="300.00"):
        return criar_saida(
            self.tenant,
            descricao="Energia",
            valor=Decimal(valor),
            conta_financeira=self.caixa,
            data_competencia=self.hoje,
            data_vencimento=self.hoje,
        )

    def test_pagamento_debita_conta(self):
        saida = self._saida()
        saida = pagar_saida(saida, usuario=self.usuario)
        self.caixa.refresh_from_db()
        self.assertEqual(self.caixa.saldo_atual, Decimal("700.00"))
        self.assertEqual(saida.status, Saida.Status.PAGA)

    def test_saldo_insuficiente_sem_permissao(self):
        saida = self._saida("5000.00")
        with self.assertRaises(FinancialError) as ctx:
            pagar_saida(saida)
        self.assertIn("Saldo insuficiente", str(ctx.exception))
        self.caixa.refresh_from_db()
        self.assertEqual(self.caixa.saldo_atual, Decimal("1000.00"))
        saida.refresh_from_db()
        self.assertEqual(saida.status, Saida.Status.PENDENTE)

    def test_saldo_negativo_com_permissao(self):
        self.caixa.permitir_saldo_negativo = True
        self.caixa.save()
        saida = self._saida("1500.00")
        pagar_saida(saida)
        self.caixa.refresh_from_db()
        self.assertEqual(self.caixa.saldo_atual, Decimal("-500.00"))

    def test_estorno_devolve_saldo(self):
        saida = self._saida()
        pagar_saida(saida)
        estornar_pagamento_saida(saida, motivo="Pago em duplicidade")
        self.caixa.refresh_from_db()
        self.assertEqual(self.caixa.saldo_atual, Decimal("1000.00"))
        self.assertEqual(saida.status, Saida.Status.PENDENTE)
        self.assertIsNone(saida.data_pagamento)

    def test_vencida_property(self):
        saida_atrasada = criar_saida(
            self.tenant,
            descricao="Antiga",
            valor=Decimal("50.00"),
            conta_financeira=self.caixa,
            data_competencia=self.hoje - timedelta(days=5),
            data_vencimento=self.hoje - timedelta(days=2),
        )
        self.assertTrue(saida_atrasada.vencida)
        self.assertFalse(self._saida().vencida)


class ParcelamentoTest(FinancialBaseTestCase):
    def test_divisao_sem_residuo(self):
        parcelas = dividir_em_parcelas(Decimal("400.00"), 4)
        self.assertEqual(parcelas, [Decimal("100.00")] * 4)

    def test_divisao_com_centavos_na_ultima(self):
        parcelas = dividir_em_parcelas(Decimal("100.00"), 3)
        self.assertEqual(sum(parcelas), Decimal("100.00"))
        self.assertEqual(parcelas[0], Decimal("33.33"))
        self.assertEqual(parcelas[-1], Decimal("33.34"))

    def test_divisao_impossivel(self):
        with self.assertRaises(FinancialError):
            dividir_em_parcelas(Decimal("0.01"), 3)


class ContaReceberTest(FinancialBaseTestCase):
    def _conta(self, total="1200.00", n=3):
        return criar_conta_receber(
            self.tenant,
            descricao="Venda fiado João",
            valor_total=Decimal(total),
            parcelas=n,
            cliente_nome="João",
        )

    def test_criacao_com_parcelas(self):
        conta = self._conta()
        parcelas = list(conta.parcelas.order_by("numero"))
        self.assertEqual(len(parcelas), 3)
        self.assertEqual(sum(p.valor for p in parcelas), Decimal("1200.00"))
        self.assertEqual(conta.status, ContaReceber.Status.ABERTA)

    def test_recebimento_parcial_atualiza_status(self):
        conta = self._conta()
        segunda = conta.parcelas.get(numero=2)
        receber_parcela(segunda, conta_financeira=self.caixa)
        conta.refresh_from_db()
        self.assertEqual(conta.status, ContaReceber.Status.PARCIAL)
        self.assertEqual(conta.valor_recebido, Decimal("400.00"))
        self.assertEqual(conta.valor_pendente, Decimal("800.00"))
        self.caixa.refresh_from_db()
        self.assertEqual(self.caixa.saldo_atual, Decimal("1400.00"))

    def test_recebimento_total(self):
        conta = self._conta()
        for parcela in conta.parcelas.all():
            receber_parcela(parcela, conta_financeira=self.caixa)
        conta.refresh_from_db()
        self.assertEqual(conta.status, ContaReceber.Status.RECEBIDA)
        self.assertEqual(conta.valor_pendente, ZERO)

    def test_parcela_dupla_rejeitada(self):
        conta = self._conta()
        primeira = conta.parcelas.get(numero=1)
        receber_parcela(primeira, conta_financeira=self.caixa)
        primeira.refresh_from_db()
        with self.assertRaises(FinancialError):
            receber_parcela(primeira, conta_financeira=self.caixa)

    def test_cancelamento_sem_recebimentos(self):
        conta = self._conta()
        conta = cancelar_conta_receber(conta)
        self.assertEqual(conta.status, ContaReceber.Status.CANCELADA)
        self.assertFalse(
            ParcelaReceber.objects.filter(status=ParcelaReceber.Status.PENDENTE).exists()
        )
        self.caixa.refresh_from_db()
        self.assertEqual(self.caixa.saldo_atual, Decimal("1000.00"))

    def test_cancelamento_com_parcela_recebida_bloqueado(self):
        conta = self._conta()
        receber_parcela(
            conta.parcelas.first(), conta_financeira=self.caixa
        )
        with self.assertRaises(FinancialError):
            cancelar_conta_receber(conta)

    def test_vencimentos_mensais_clampados(self):
        vencimentos = [
            date(2026, 1, 31),
            date(2026, 2, 28),
            date(2026, 3, 31),
        ]
        conta = criar_conta_receber(
            self.tenant,
            descricao="Clamp",
            valor_total=Decimal("90.00"),
            parcelas=3,
            vencimentos=vencimentos,
        )
        self.assertEqual(
            list(conta.parcelas.values_list("data_vencimento", flat=True)),
            vencimentos,
        )


class FormaPagamentoTest(FinancialBaseTestCase):
    def test_criar_forma(self):
        forma = criar_forma_pagamento(
            self.tenant,
            nome="Cartão crédito",
            codigo="CREDITO",
            taxa_percentual=Decimal("3.50"),
            gera_conta_receber=False,
        )
        self.assertEqual(forma.taxa_percentual, Decimal("3.50"))


class IsolamentoMultiTenantTest(TestCase):
    def setUp(self):
        self.tenant_a = Tenant.objects.create(
            nome="Tenant A Fin", status=Tenant.Status.ATIVO
        )
        self.tenant_b = Tenant.objects.create(
            nome="Tenant B Fin", status=Tenant.Status.ATIVO
        )
        self.conta_a = criar_conta(
            self.tenant_a, nome="Caixa A", tipo=ContaFinanceira.Tipo.CAIXA
        )
        self.conta_b = criar_conta(
            self.tenant_b, nome="Caixa B", tipo=ContaFinanceira.Tipo.CAIXA
        )
        hoje = timezone.localdate()
        criar_entrada(
            self.tenant_a,
            descricao="Entrada A",
            valor=Decimal("1000.00"),
            conta_financeira=self.conta_a,
            data_competencia=hoje,
        )
        criar_entrada(
            self.tenant_b,
            descricao="Entrada B",
            valor=Decimal("5000.00"),
            conta_financeira=self.conta_b,
            data_competencia=hoje,
        )

    def test_movimentacoes_isoladas(self):
        from ..services import resumo_analise

        resumo_a = resumo_analise(
            self.tenant_a,
            inicio=timezone.localdate(),
            fim=timezone.localdate(),
        )
        # modo CAIXA: nada recebido ainda
        self.assertEqual(resumo_a["entradas"], ZERO)

    def test_analise_por_competencia_isolada(self):
        from ..services import resumo_analise

        hoje = timezone.localdate()
        resumo_a = resumo_analise(
            self.tenant_a, inicio=hoje, fim=hoje, modo="COMPETENCIA"
        )
        resumo_b = resumo_analise(
            self.tenant_b, inicio=hoje, fim=hoje, modo="COMPETENCIA"
        )
        self.assertEqual(resumo_a["entradas"], Decimal("1000.00"))
        self.assertEqual(resumo_b["entradas"], Decimal("5000.00"))

    def test_receber_parcela_cross_tenant(self):
        conta_b = criar_conta_receber(
            self.tenant_b,
            descricao="Fiado B",
            valor_total=Decimal("60.00"),
            parcelas=2,
        )
        parcela = conta_b.parcelas.first()
        with self.assertRaises(FinancialError):
            receber_parcela(parcela, conta_financeira=self.conta_a)


class ConcorrenciaFinanceiraTest(TransactionTestCase):
    """Duas saídas simultâneas de 700 com saldo 1000: no máximo uma passa."""

    def test_saidas_simultaneas_nao_estouram_saldo(self):
        tenant = Tenant.objects.create(
            nome="Concorrência Fin", status=Tenant.Status.ATIVO
        )
        conta = criar_conta(
            tenant, nome="Caixa conc.", tipo=ContaFinanceira.Tipo.CAIXA,
            saldo_inicial=Decimal("1000.00"),
        )
        hoje = timezone.localdate()
        saidas = [
            criar_saida(
                tenant,
                descricao=f"Saída {i}",
                valor=Decimal("700.00"),
                conta_financeira=conta,
                data_competencia=hoje,
                data_vencimento=hoje,
            )
            for i in range(2)
        ]

        import threading

        barreira = threading.Barrier(2, timeout=10)
        resultados = []

        def pagar(saida):
            barreira.wait()
            try:
                pagar_saida(saida)
                resultados.append("ok")
            except (FinancialError, OperationalError):
                resultados.append("rejeitada")

        threads = [
            threading.Thread(target=pagar, args=(saida,)) for saida in saidas
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=15)

        conta.refresh_from_db()
        self.assertLessEqual(resultados.count("ok"), 1)
        esperado = (
            Decimal("300.00") if resultados.count("ok") == 1 else Decimal("1000.00")
        )
        self.assertEqual(conta.saldo_atual, esperado)
        self.assertEqual(
            MovimentacaoFinanceira.objects.filter(
                tipo=MovimentacaoFinanceira.Tipo.SAIDA
            ).count(),
            resultados.count("ok"),
        )
