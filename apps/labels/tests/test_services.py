"""Testes das regras da bobina (duas etiquetas por fileira)."""

from datetime import timedelta

from django.utils import timezone

from apps.printing.models import EstacaoImpressao

from ..models import ConfiguracaoEtiqueta, EtiquetaJob
from ..services import (
    LabelsError,
    agrupar_em_fileiras,
    classificar_status_etiquetas,
    criar_etiqueta_job,
    criar_job_calibracao,
    marcar_falha,
    marcar_impresso,
    montar_preview,
    obter_proximo_job_etiquetas,
    organizar_etiquetas,
    reativar_job,
    resumo_impressao,
)
from .base import LabelsBaseTestCase, criar_contexto_outro


class OrganizacaoTest(LabelsBaseTestCase):
    def test_um_produto_uma_etiqueta(self):
        selecao = [{"nome": "A", "codigo_barras": "1", "quantidade": 1}]
        self.assertEqual(len(organizar_etiquetas(selecao)), 1)
        fileiras = agrupar_em_fileiras(organizar_etiquetas(selecao))
        self.assertEqual(fileiras, [[{"nome": "A", "codigo_barras": "1"}, None]])

    def test_duas_etiquetas_preenchem_uma_fileira(self):
        selecao = [{"nome": "A", "codigo_barras": "1", "quantidade": 2}]
        fileiras = agrupar_em_fileiras(organizar_etiquetas(selecao))
        self.assertEqual(len(fileiras), 1)
        self.assertTrue(all(posicao is not None for posicao in fileiras[0]))

    def test_tres_etiquetas_ocupam_duas_fileiras(self):
        selecao = [{"nome": "A", "codigo_barras": "1", "quantidade": 3}]
        fileiras = agrupar_em_fileiras(organizar_etiquetas(selecao))
        self.assertEqual(len(fileiras), 2)
        self.assertIsNone(fileiras[1][1])
        self.assertIsNotNone(fileiras[1][0])

    def test_quatro_etiquetas_ocupam_duas_fileiras_completas(self):
        selecao = [{"nome": "A", "codigo_barras": "1", "quantidade": 4}]
        fileiras = agrupar_em_fileiras(organizar_etiquetas(selecao))
        self.assertEqual(len(fileiras), 2)
        self.assertTrue(all(posicao is not None for posicao in fileiras[0]))
        self.assertTrue(all(posicao is not None for posicao in fileiras[1]))

    def test_quantidades_mistas_a3_b1(self):
        # A=3, B=1 → fileiras: [A, A], [A, B] (exemplo da task §7).
        selecao = [
            {"nome": "A", "codigo_barras": "1", "quantidade": 3},
            {"nome": "B", "codigo_barras": "2", "quantidade": 1},
        ]
        fileiras = agrupar_em_fileiras(organizar_etiquetas(selecao))
        self.assertEqual(fileiras[0][0]["nome"], "A")
        self.assertEqual(fileiras[0][1]["nome"], "A")
        self.assertEqual(fileiras[1][0]["nome"], "A")
        self.assertEqual(fileiras[1][1]["nome"], "B")

    def test_quantidade_impar_gera_posicao_vazia(self):
        selecao = [{"nome": "A", "codigo_barras": "1", "quantidade": 5}]
        fileiras = agrupar_em_fileiras(organizar_etiquetas(selecao))
        self.assertEqual(len(fileiras), 3)
        self.assertIsNone(fileiras[2][1])
        resumo = resumo_impressao(selecao)
        self.assertEqual(resumo["posicoes_vazias"], 1)
        self.assertEqual(resumo["fileiras"], 3)

    def test_quantidade_invalida_rejeitada(self):
        selecao = [{"nome": "A", "codigo_barras": "1", "quantidade": 0}]
        with self.assertRaises(LabelsError):
            organizar_etiquetas(selecao)
        selecao = [{"nome": "A", "codigo_barras": "1", "quantidade": 101}]
        with self.assertRaises(LabelsError):
            organizar_etiquetas(selecao)

    def test_resumo_completo(self):
        selecao = [
            {"nome": "A", "codigo_barras": "1", "quantidade": 3},
            {"nome": "B", "codigo_barras": "2", "quantidade": 2},
        ]
        resumo = resumo_impressao(selecao)
        self.assertEqual(
            resumo,
            {
                "produtos": 2,
                "etiquetas": 5,
                "fileiras": 3,
                "posicoes_vazias": 1,
            },
        )


class PreviewPayloadTest(LabelsBaseTestCase):
    def test_preview_usa_mesma_estrutura_do_payload(self):
        itens = self.itens((self.produto_a, 3), (self.produto_b, 1))
        preview = montar_preview(self.tenant, itens)
        payload = criar_etiqueta_job(self.tenant, itens).payload
        # Regra 18: preview e impressão usam a MESMA estrutura.
        self.assertEqual(preview["fileiras"], payload["fileiras"])
        self.assertEqual(preview["resumo"], payload["resumo"])
        self.assertEqual(payload["fileiras"][0][0]["nome"], "Produto A")
        self.assertEqual(payload["fileiras"][1][1]["nome"], "Produto B")

    def test_produto_de_outro_tenant_rejeitado(self):
        outro = criar_contexto_outro()
        itens = self.itens((outro.produto_a, 1))
        with self.assertRaises(LabelsError):
            montar_preview(self.tenant, itens)

    def test_produto_inexistente_rejeitado(self):
        with self.assertRaises(LabelsError):
            montar_preview(
                self.tenant,
                [{"uuid": "00000000-0000-0000-0000-000000000000", "quantidade": 1}],
            )

    def test_sem_produtos_rejeitado(self):
        with self.assertRaises(LabelsError):
            montar_preview(self.tenant, [])

    def test_payload_tem_dimensoes_e_impressora(self):
        job = criar_etiqueta_job(self.tenant, self.itens((self.produto_a, 1)))
        payload = job.payload
        self.assertEqual(payload["tipo"], "etiquetas")
        self.assertEqual(payload["impressora"], "Elgin L42 Pro Full")
        self.assertEqual(payload["dimensoes"]["dpi"], 203)
        self.assertIn("largura_etiqueta", payload["dimensoes"])

    def test_job_calibracao(self):
        job = criar_job_calibracao(self.tenant, usuario=self.operador)
        self.assertEqual(job.payload["tipo"], "calibracao")
        self.assertEqual(job.status, EtiquetaJob.Status.PENDING)


class FilaEtiquetasTest(LabelsBaseTestCase):
    def setUp(self):
        super().setUp()
        self.estacao = EstacaoImpressao.objects.create(
            tenant=self.tenant, nome="Caixa 01"
        )

    def test_poll_entrega_mais_antigo(self):
        primeiro = criar_etiqueta_job(self.tenant, self.itens((self.produto_a, 1)))
        segundo = criar_etiqueta_job(self.tenant, self.itens((self.produto_b, 1)))
        job = obter_proximo_job_etiquetas(self.estacao)
        self.assertEqual(job.pk, primeiro.pk)
        self.assertEqual(job.status, EtiquetaJob.Status.PROCESSING)
        self.assertEqual(job.tentativa, 1)
        self.assertIsNotNone(segundo)

    def test_isolamento_entre_tenants(self):
        outro = criar_contexto_outro()
        criar_etiqueta_job(self.tenant, self.itens((self.produto_a, 1)))
        estacao_outra = EstacaoImpressao.objects.create(
            tenant=outro.tenant, nome="Caixa Alheia"
        )
        self.assertIsNone(obter_proximo_job_etiquetas(estacao_outra))

    def test_retry_respeita_backoff_e_esgota(self):
        criar_etiqueta_job(self.tenant, self.itens((self.produto_a, 1)))
        entregue = obter_proximo_job_etiquetas(self.estacao)
        marcar_falha(entregue, self.estacao, "sem etiquetas")
        entregue.refresh_from_db()
        self.assertEqual(entregue.status, EtiquetaJob.Status.RETRYING)
        self.assertGreater(entregue.proxima_tentativa, timezone.now())
        entregue.tentativa = entregue.tentativas_maximas
        entregue.save()
        marcar_falha(entregue, self.estacao, "acabou de vez")
        entregue.refresh_from_db()
        self.assertEqual(entregue.status, EtiquetaJob.Status.FAILED)

    def test_impresso_e_reativar(self):
        criar_etiqueta_job(self.tenant, self.itens((self.produto_a, 1)))
        entregue = obter_proximo_job_etiquetas(self.estacao)
        marcar_impresso(entregue, self.estacao)
        entregue.refresh_from_db()
        self.assertEqual(entregue.status, EtiquetaJob.Status.PRINTED)
        self.assertIsNotNone(entregue.data_impressao)
        outro = criar_etiqueta_job(self.tenant, self.itens((self.produto_b, 1)))
        outro.status = EtiquetaJob.Status.FAILED
        outro.save()
        reativar_job(outro)
        outro.refresh_from_db()
        self.assertEqual(outro.status, EtiquetaJob.Status.PENDING)

    def test_processando_parado_volta_para_fila(self):
        criar_etiqueta_job(self.tenant, self.itens((self.produto_a, 1)))
        entregue = obter_proximo_job_etiquetas(self.estacao)
        entregue.data_processamento = timezone.now() - timedelta(minutes=10)
        entregue.save()
        self.assertIsNone(obter_proximo_job_etiquetas(self.estacao))
        entregue.refresh_from_db()
        self.assertEqual(entregue.status, EtiquetaJob.Status.RETRYING)


class ClassificarStatusTest(LabelsBaseTestCase):
    def test_estados(self):
        self.assertEqual(classificar_status_etiquetas(None, self.tenant), "SEM_JOB")
        job = criar_etiqueta_job(self.tenant, self.itens((self.produto_a, 1)))
        self.assertEqual(
            classificar_status_etiquetas(job, self.tenant), "AGUARDANDO_AGENTE"
        )
        EstacaoImpressao.objects.create(tenant=self.tenant, nome="Caixa 01")
        self.assertEqual(
            classificar_status_etiquetas(job, self.tenant), "AGUARDANDO_IMPRESSORA"
        )


class ConfiguracaoTest(LabelsBaseTestCase):
    def test_carregar_cria_com_padroes(self):
        config = ConfiguracaoEtiqueta.carregar(self.tenant)
        self.assertEqual(config.dpi, 203)
        self.assertEqual(config.nome_impressora, "Elgin L42 Pro Full")
        self.assertIn("largura_etiqueta", config.dimensoes_mm())
