"""Testes da API de etiquetas do agente (poll/resultado)."""

import json

from django.urls import reverse

from apps.printing.models import EstacaoImpressao
from apps.printing.services import gerar_codigo_pareamento, parear_estacao

from ..models import EtiquetaJob
from ..services import criar_etiqueta_job
from .base import LabelsBaseTestCase, criar_contexto_outro


def cabecalhos(estacao, token):
    return {
        "HTTP_X_STATION_UUID": str(estacao.uuid),
        "HTTP_X_STATION_TOKEN": token,
    }


class EtiquetasApiTest(LabelsBaseTestCase):
    def setUp(self):
        super().setUp()
        self.estacao = EstacaoImpressao.objects.create(
            tenant=self.tenant, nome="Caixa 01"
        )
        _, self.token = parear_estacao(gerar_codigo_pareamento(self.estacao))

    def test_poll_sem_autenticacao_rejeitado(self):
        resposta = self.client.post(
            reverse("labels_api:poll"),
            data=json.dumps({}),
            content_type="application/json",
        )
        self.assertEqual(resposta.status_code, 401)

    def test_poll_entrega_job_etiquetas(self):
        job = criar_etiqueta_job(self.tenant, self.itens((self.produto_a, 3)))
        resposta = self.client.post(
            reverse("labels_api:poll"),
            data=json.dumps({"disponivel": True}),
            content_type="application/json",
            **cabecalhos(self.estacao, self.token),
        )
        self.assertEqual(resposta.status_code, 200)
        dados = resposta.json()
        self.assertEqual(dados["job"]["uuid"], str(job.uuid))
        self.assertEqual(dados["job"]["payload"]["tipo"], "etiquetas")
        self.assertEqual(dados["job"]["payload"]["fileiras"][0][0]["nome"], "Produto A")
        job.refresh_from_db()
        self.assertEqual(job.status, EtiquetaJob.Status.PROCESSING)

    def test_poll_disponivel_false_nao_consome(self):
        job = criar_etiqueta_job(self.tenant, self.itens((self.produto_a, 1)))
        resposta = self.client.post(
            reverse("labels_api:poll"),
            data=json.dumps({"disponivel": False}),
            content_type="application/json",
            **cabecalhos(self.estacao, self.token),
        )
        self.assertIsNone(resposta.json()["job"])
        job.refresh_from_db()
        self.assertEqual(job.status, EtiquetaJob.Status.PENDING)

    def test_resultado_impresso_e_falha(self):
        job = criar_etiqueta_job(self.tenant, self.itens((self.produto_a, 1)))
        self.client.post(
            reverse("labels_api:poll"),
            data=json.dumps({}),
            content_type="application/json",
            **cabecalhos(self.estacao, self.token),
        )
        resposta = self.client.post(
            reverse("labels_api:resultado", args=[job.uuid]),
            data=json.dumps({"status": "PRINTED"}),
            content_type="application/json",
            **cabecalhos(self.estacao, self.token),
        )
        self.assertEqual(resposta.status_code, 200)
        job.refresh_from_db()
        self.assertEqual(job.status, EtiquetaJob.Status.PRINTED)

        job2 = criar_etiqueta_job(self.tenant, self.itens((self.produto_b, 1)))
        self.client.post(
            reverse("labels_api:poll"),
            data=json.dumps({}),
            content_type="application/json",
            **cabecalhos(self.estacao, self.token),
        )
        resposta = self.client.post(
            reverse("labels_api:resultado", args=[job2.uuid]),
            data=json.dumps({"status": "FAILED", "erro": "sem etiquetas"}),
            content_type="application/json",
            **cabecalhos(self.estacao, self.token),
        )
        job2.refresh_from_db()
        self.assertEqual(job2.status, EtiquetaJob.Status.RETRYING)
        self.assertIn("sem etiquetas", job2.erro)

    def test_resultado_nao_entregue_404(self):
        job = criar_etiqueta_job(self.tenant, self.itens((self.produto_a, 1)))
        resposta = self.client.post(
            reverse("labels_api:resultado", args=[job.uuid]),
            data=json.dumps({"status": "PRINTED"}),
            content_type="application/json",
            **cabecalhos(self.estacao, self.token),
        )
        self.assertEqual(resposta.status_code, 404)

    def test_isolamento_entre_tenants(self):
        outro = criar_contexto_outro()
        estacao_outra = EstacaoImpressao.objects.create(
            tenant=outro.tenant, nome="Caixa Alheia"
        )
        _, token_outra = parear_estacao(gerar_codigo_pareamento(estacao_outra))
        criar_etiqueta_job(self.tenant, self.itens((self.produto_a, 1)))
        resposta = self.client.post(
            reverse("labels_api:poll"),
            data=json.dumps({}),
            content_type="application/json",
            **cabecalhos(estacao_outra, token_outra),
        )
        self.assertIsNone(resposta.json()["job"])
