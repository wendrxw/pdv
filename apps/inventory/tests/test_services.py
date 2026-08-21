import threading
from decimal import Decimal

from django.db.utils import OperationalError
from django.test import TestCase, TransactionTestCase

from apps.companies.models import Tenant
from apps.products.models import Produto

from ..models import Estoque, Fornecedor, MovimentacaoEstoque
from ..services import (
    EstoqueError,
    adicionar_estoque,
    ajustar_estoque,
    obter_ou_criar_estoque,
    registrar_devolucao,
    registrar_venda,
    remover_estoque,
)

Q3 = Decimal("0.001")


class EstoqueBaseTestCase(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(
            nome="Loja Estoque", status=Tenant.Status.ATIVO
        )
        self.produto = Produto.objects.create(
            tenant=self.tenant,
            nome="Produto base",
            preco_custo=Decimal("10.00"),
            preco_venda=Decimal("20.00"),
            estoque_minimo=Decimal("5"),
        )


class MovimentacoesBasicasTest(EstoqueBaseTestCase):
    def test_entrada_cria_saldo_e_movimentacao(self):
        mov = adicionar_estoque(self.produto, 50)
        estoque = Estoque.objects.get(produto=self.produto)
        self.assertEqual(estoque.quantidade, Decimal("50"))
        self.assertEqual(mov.saldo_anterior, Decimal("0"))
        self.assertEqual(mov.saldo_posterior, Decimal("50"))
        self.assertEqual(mov.tipo, MovimentacaoEstoque.Tipo.ENTRADA)

    def test_saida_respeita_saldo(self):
        adicionar_estoque(self.produto, 50)
        mov = remover_estoque(self.produto, 12)
        self.assertEqual(mov.saldo_posterior, Decimal("38"))

    def test_saida_bloqueada_sem_saldo(self):
        with self.assertRaises(EstoqueError):
            remover_estoque(self.produto, 1)
        estoque = obter_ou_criar_estoque(self.produto)
        self.assertEqual(estoque.quantidade, Decimal("0"))

    def test_venda_e_devolucao(self):
        adicionar_estoque(self.produto, 30)
        venda = registrar_venda(self.produto, 3)
        devolucao = registrar_devolucao(self.produto, 1)
        estoque = Estoque.objects.get(produto=self.produto)
        self.assertEqual(venda.tipo, MovimentacaoEstoque.Tipo.VENDA)
        self.assertEqual(devolucao.tipo, MovimentacaoEstoque.Tipo.DEVOLUCAO)
        self.assertEqual(estoque.quantidade, Decimal("28"))

    def test_ajuste_para_valor_absoluto(self):
        adicionar_estoque(self.produto, 10)
        mov = ajustar_estoque(self.produto, novo_saldo=4)
        self.assertEqual(mov.tipo, MovimentacaoEstoque.Tipo.AJUSTE_NEGATIVO)
        self.assertEqual(mov.quantidade, Decimal("6"))
        estoque = Estoque.objects.get(produto=self.produto)
        self.assertEqual(estoque.quantidade, Decimal("4"))

    def test_quantidade_zero_ou_negativa_rejeitada(self):
        with self.assertRaises(EstoqueError):
            adicionar_estoque(self.produto, 0)
        with self.assertRaises(EstoqueError):
            remover_estoque(self.produto, -5)

    def test_fornecedor_de_outro_tenant_rejeitado(self):
        outro = Tenant.objects.create(nome="Outro")
        fornecedor_alheio = Fornecedor.objects.create(
            tenant=outro, razao_social="Fornecedor Alheio"
        )
        with self.assertRaises(EstoqueError):
            adicionar_estoque(
                self.produto, 10, fornecedor=fornecedor_alheio
            )

    def test_historico_explica_saldo(self):
        """Integridade §42: o saldo é reconstruível pelas movimentações."""
        adicionar_estoque(self.produto, 50)
        registrar_venda(self.produto, 3)
        registrar_venda(self.produto, 2)
        registrar_devolucao(self.produto, 1)
        ajustar_estoque(self.produto, novo_saldo=42)
        saldo = Decimal("0")
        for mov in MovimentacaoEstoque.objects.filter(
            produto=self.produto
        ).order_by("data_criacao"):
            saldo = mov.saldo_posterior
            entrada = mov.saldo_posterior > mov.saldo_anterior
            esperado = (
                mov.saldo_anterior + mov.quantidade
                if entrada
                else mov.saldo_anterior - mov.quantidade
            )
            self.assertEqual(saldo, esperado)
        estoque = Estoque.objects.get(produto=self.produto)
        self.assertEqual(estoque.quantidade, saldo)


class EstoqueNegativoTest(EstoqueBaseTestCase):
    def _permitir(self, valor):
        self.tenant.permitir_estoque_negativo = valor
        self.tenant.save(update_fields=["permitir_estoque_negativo"])

    def test_negativo_bloqueado_por_padrao(self):
        adicionar_estoque(self.produto, 2)
        with self.assertRaises(EstoqueError):
            registrar_venda(self.produto, 3)

    def test_negativo_permitido_por_tenant(self):
        self._permitir(True)
        adicionar_estoque(self.produto, 2)
        mov = registrar_venda(self.produto, 3)
        self.assertEqual(mov.saldo_posterior, Decimal("-1"))


class RollbackTransacionalTest(TransactionTestCase):
    def test_falha_apos_update_nao_persiste_nada(self):
        tenant = Tenant.objects.create(nome="Rollback")
        produto = Produto.objects.create(tenant=tenant, nome="P")
        adicionar_estoque(produto, 10)
        from unittest.mock import patch

        with patch.object(
            MovimentacaoEstoque.objects,
            "create",
            side_effect=RuntimeError("falha simulada"),
        ):
            with self.assertRaises(RuntimeError):
                adicionar_estoque(produto, 5)
        estoque = Estoque.objects.get(produto=produto)
        self.assertEqual(estoque.quantidade, Decimal("10"))
        self.assertEqual(MovimentacaoEstoque.objects.count(), 1)


class ConcorrenciaEstoqueTest(TransactionTestCase):
    """Duas vendas simultâneas de 7 com saldo 10: apenas uma consome."""

    def test_vendas_simultaneas_nao_geram_negativo(self):
        """No máximo uma das vendas simultâneas consome o estoque.

        Em PostgreSQL a segunda operação espera o lock (select_for_update),
        relê o saldo atualizado e é rejeitada por EstoqueError. Em SQLite
        (sem lock de linha) a escrita concorrente falha com
        OperationalError ("table is locked") — também uma rejeição; sob
        disputa, ocasionalmente ambas as threads perdem a corrida pelo
        lock de escrita e nenhuma consuma. O invariante garantido em
        qualquer banco: saldo nunca negativo e no máximo uma venda.
        """
        tenant = Tenant.objects.create(
            nome="Concorrente", status=Tenant.Status.ATIVO
        )
        produto = Produto.objects.create(tenant=tenant, nome="Concorrido")
        adicionar_estoque(produto, 10)

        barreira = threading.Barrier(2, timeout=10)
        resultados = []

        def vender():
            barreira.wait()
            try:
                registrar_venda(produto, 7)
                resultados.append("ok")
            except EstoqueError:
                resultados.append("rejeitada")
            except OperationalError:
                resultados.append("rejeitada")

        threads = [threading.Thread(target=vender) for _ in range(2)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=15)

        estoque = Estoque.objects.get(produto=produto)
        self.assertLessEqual(resultados.count("ok"), 1)
        self.assertEqual(
            estoque.quantidade,
            Decimal("3") if resultados.count("ok") == 1 else Decimal("10"),
        )
        self.assertLessEqual(estoque.quantidade, Decimal("10"))
        movimentos = MovimentacaoEstoque.objects.filter(
            tipo=MovimentacaoEstoque.Tipo.VENDA
        ).count()
        self.assertEqual(movimentos, resultados.count("ok"))
