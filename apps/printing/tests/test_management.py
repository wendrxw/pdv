"""Testes do comando de monitoramento de estações (Fase 3)."""

from datetime import timedelta
from io import StringIO

from django.core.management import call_command
from django.utils import timezone

from ..models import EstacaoImpressao
from .base import PrintingBaseTestCase


class CheckPrintAgentsTest(PrintingBaseTestCase):
    def setUp(self):
        super().setUp()
        self.saida = StringIO()

    def executar(self, *argumentos):
        try:
            call_command("check_print_agents", *argumentos, stdout=self.saida)
            return 0
        except SystemExit as exc:
            return exc.code

    def test_todas_ativas_recentes_nao_avisa(self):
        EstacaoImpressao.objects.create(
            tenant=self.tenant,
            nome="Caixa 01",
            ultima_atividade=timezone.now(),
        )
        codigo = self.executar()
        self.assertEqual(codigo, 0)
        self.assertIn("responderam recentemente", self.saida.getvalue())

    def test_estacao_nunca_respondida_avisa(self):
        EstacaoImpressao.objects.create(tenant=self.tenant, nome="Caixa 01")
        codigo = self.executar()
        self.assertEqual(codigo, 1)
        self.assertIn("última atividade nunca", self.saida.getvalue())

    def test_estacao_atrasada_avisa(self):
        EstacaoImpressao.objects.create(
            tenant=self.tenant,
            nome="Caixa 01",
            ultima_atividade=timezone.now() - timedelta(minutes=15),
        )
        codigo = self.executar("--minutos", "10")
        self.assertEqual(codigo, 1)
        self.assertIn("Caixa 01", self.saida.getvalue())

    def test_estacao_inativa_ignorada(self):
        EstacaoImpressao.objects.create(
            tenant=self.tenant,
            nome="Caixa 01",
            status=EstacaoImpressao.Status.INATIVA,
        )
        self.assertEqual(self.executar(), 0)
