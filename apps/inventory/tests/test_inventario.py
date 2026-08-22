from decimal import Decimal

from django.test import TestCase

from apps.accounts.models import User
from apps.companies.models import Tenant
from apps.products.models import Produto

from ..inventario import (
    InventarioError,
    cancelar,
    enviar_para_revisao,
    finalizar,
    iniciar_contagem,
    iniciar_inventario,
    registrar_contagem,
)
from ..models import (
    Estoque,
    Inventario,
    InventarioItem,
    MovimentacaoEstoque,
)
from ..services import adicionar_estoque


class InventarioBaseTestCase(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(
            nome="Loja Inv", status=Tenant.Status.ATIVO
        )
        self.usuario = User.objects.create_user(
            username="contador", password="senha-12345", tenant=self.tenant
        )
        self.produto_a = Produto.objects.create(tenant=self.tenant, nome="Produto A")
        self.produto_b = Produto.objects.create(tenant=self.tenant, nome="Produto B")
        adicionar_estoque(self.produto_a, 100)
        adicionar_estoque(self.produto_b, 50)


class IniciarInventarioTest(InventarioBaseTestCase):
    def test_congela_saldo_de_referencia(self):
        inventario = iniciar_inventario(
            tenant=self.tenant,
            descricao="Contagem geral",
            usuario=self.usuario,
        )
        item_a = InventarioItem.objects.get(
            inventario=inventario, produto=self.produto_a
        )
        item_b = InventarioItem.objects.get(
            inventario=inventario, produto=self.produto_b
        )
        self.assertEqual(item_a.quantidade_sistema, Decimal("100"))
        self.assertEqual(item_b.quantidade_sistema, Decimal("50"))
        self.assertEqual(inventario.status, Inventario.Status.ABERTO)

    def test_venda_durante_contagem_nao_altera_referencia(self):
        inventario = iniciar_inventario(
            tenant=self.tenant, descricao="Ref congelada"
        )
        from ..services import registrar_venda

        registrar_venda(self.produto_a, 10)
        item_a = InventarioItem.objects.get(
            inventario=inventario, produto=self.produto_a
        )
        self.assertEqual(item_a.quantidade_sistema, Decimal("100"))

    def test_produto_de_outro_tenant_rejeitado(self):
        outro = Tenant.objects.create(nome="Outro Inv")
        produto_alheio = Produto.objects.create(tenant=outro, nome="Alheio")
        with self.assertRaises(InventarioError):
            iniciar_inventario(
                tenant=self.tenant,
                descricao="Invadido",
                produtos=[produto_alheio],
            )


class FluxoStatusTest(InventarioBaseTestCase):
    def _inventario(self):
        return iniciar_inventario(
            tenant=self.tenant, descricao="Fluxo completo", usuario=self.usuario
        )

    def test_fluxo_completo_valido(self):
        inventario = self._inventario()
        iniciar_contagem(inventario)
        registrar_contagem(
            inventario,
            {
                str(inventario.itens.get(produto=self.produto_a).uuid): 98,
                str(inventario.itens.get(produto=self.produto_b).uuid): 52,
            },
        )
        enviar_para_revisao(inventario)
        finalizar(inventario, usuario=self.usuario)
        inventario.refresh_from_db()
        self.assertEqual(inventario.status, Inventario.Status.FINALIZADO)
        self.assertIsNotNone(inventario.data_finalizacao)

    def test_transicao_invalida_bloqueada(self):
        inventario = self._inventario()
        with self.assertRaises(InventarioError):
            finalizar(inventario)  # ABERTO → FINALIZADO é inválido

    def test_finalizado_nao_pode_ser_alterado(self):
        inventario = self._inventario()
        iniciar_contagem(inventario)
        enviar_para_revisao(inventario)
        finalizar(inventario)
        with self.assertRaises(InventarioError):
            cancelar(inventario)
        with self.assertRaises(InventarioError):
            iniciar_contagem(inventario)

    def test_cancelamento_nao_aplica_ajustes(self):
        inventario = self._inventario()
        iniciar_contagem(inventario)
        registrar_contagem(
            inventario,
            {str(inventario.itens.get(produto=self.produto_a).uuid): 10},
        )
        enviar_para_revisao(inventario)
        cancelar(inventario)
        estoque = Estoque.objects.get(produto=self.produto_a)
        self.assertEqual(estoque.quantidade, Decimal("100"))


class FinalizacaoAjustesTest(InventarioBaseTestCase):
    def _inventario_com_contagem(self):
        inventario = iniciar_inventario(
            tenant=self.tenant, descricao="Ajuste automático"
        )
        iniciar_contagem(inventario)
        registrar_contagem(
            inventario,
            {
                str(inventario.itens.get(produto=self.produto_a).uuid): 97,
                str(inventario.itens.get(produto=self.produto_b).uuid): 50,
            },
        )
        enviar_para_revisao(inventario)
        return inventario

    def test_finalizacao_gera_movimentacoes_inventario(self):
        inventario = self._inventario_com_contagem()
        finalizar(inventario, usuario=self.usuario)

        estoque_a = Estoque.objects.get(produto=self.produto_a)
        estoque_b = Estoque.objects.get(produto=self.produto_b)
        self.assertEqual(estoque_a.quantidade, Decimal("97"))
        self.assertEqual(estoque_b.quantidade, Decimal("50"))  # sem divergência

        movs = MovimentacaoEstoque.objects.filter(
            tipo=MovimentacaoEstoque.Tipo.INVENTARIO
        )
        self.assertEqual(movs.count(), 1)
        mov = movs.first()
        self.assertEqual(mov.produto, self.produto_a)
        self.assertEqual(mov.quantidade, Decimal("3"))
        self.assertEqual(mov.saldo_anterior, Decimal("100"))
        self.assertEqual(mov.saldo_posterior, Decimal("97"))

    def test_itens_sem_contagem_sao_ignorados(self):
        inventario = iniciar_inventario(
            tenant=self.tenant, descricao="Parcial"
        )
        iniciar_contagem(inventario)
        item_a = inventario.itens.get(produto=self.produto_a)
        registrar_contagem(inventario, {str(item_a.uuid): 90})
        enviar_para_revisao(inventario)
        finalizar(inventario)

        estoque_b = Estoque.objects.get(produto=self.produto_b)
        self.assertEqual(estoque_b.quantidade, Decimal("50"))
        self.assertFalse(
            MovimentacaoEstoque.objects.filter(
                produto=self.produto_b,
                tipo=MovimentacaoEstoque.Tipo.INVENTARIO,
            ).exists()
        )

    def test_divergencia_calculada(self):
        inventario = iniciar_inventario(
            tenant=self.tenant, descricao="Divergência"
        )
        item_a = inventario.itens.get(produto=self.produto_a)
        self.assertIsNone(item_a.divergencia)
        item_a.quantidade_contada = Decimal("95")
        self.assertEqual(item_a.divergencia, Decimal("-5"))
        self.assertTrue(item_a.tem_divergencia)


class IsolamentoMultiTenantTest(InventarioBaseTestCase):
    def test_inventarios_isolados_por_tenant(self):
        inventario = iniciar_inventario(
            tenant=self.tenant, descricao="Meu inventário"
        )
        outro_tenant = Tenant.objects.create(nome="Outra Loja Inv")
        with self.assertRaises(Inventario.DoesNotExist):
            Inventario.objects.for_tenant(outro_tenant).get(uuid=inventario.uuid)

    def test_contagem_so_aceita_itens_do_inventario(self):
        outro_inventario = iniciar_inventario(
            tenant=self.tenant, descricao="Outro"
        )
        inventario = iniciar_inventario(
            tenant=self.tenant, descricao="Principal"
        )
        iniciar_contagem(inventario)
        item_alheio = outro_inventario.itens.first()
        with self.assertRaises(InventarioError):
            registrar_contagem(inventario, {str(item_alheio.uuid): 5})
