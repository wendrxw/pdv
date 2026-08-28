"""Testes da API do agente (pair/poll/resultado) e isolamento."""

import json
from unittest import mock

from django.urls import reverse

from apps.companies.models import Tenant

from ..models import EstacaoImpressao, PrintJob
from ..services import (
    criar_print_job,
    gerar_codigo_pareamento,
    parear_estacao,
)
from .base import PrintingBaseTestCase


def cabecalhos(estacao, token=None):
    return {
        "HTTP_X_STATION_UUID": str(estacao.uuid),
        "HTTP_X_STATION_TOKEN": token or "",
    }


class PairApiTest(PrintingBaseTestCase):
    def test_pair_retorna_token_uma_vez(self):
        estacao = EstacaoImpressao.objects.create(tenant=self.tenant, nome="Caixa 01")
        codigo = gerar_codigo_pareamento(estacao)
        resposta = self.client.post(
            reverse("printing_api:pair"),
            data=json.dumps({"codigo": codigo}),
            content_type="application/json",
        )
        self.assertEqual(resposta.status_code, 200)
        dados = resposta.json()
        self.assertEqual(dados["nome"], "Caixa 01")
        self.assertEqual(dados["loja"], self.tenant.nome)
        self.assertIn("token", dados)
        # Segunda tentativa com o mesmo código: uso único.
        segunda = self.client.post(
            reverse("printing_api:pair"),
            data=json.dumps({"codigo": codigo}),
            content_type="application/json",
        )
        self.assertEqual(segunda.status_code, 400)

    def test_pair_codigo_invalido(self):
        resposta = self.client.post(
            reverse("printing_api:pair"),
            data=json.dumps({"codigo": "ZZZZZZ"}),
            content_type="application/json",
        )
        self.assertEqual(resposta.status_code, 400)


class PollApiTest(PrintingBaseTestCase):
    def setUp(self):
        super().setUp()
        self.estacao = EstacaoImpressao.objects.create(
            tenant=self.tenant, nome="Caixa 01"
        )
        _, self.token = parear_estacao(gerar_codigo_pareamento(self.estacao))

    def test_poll_sem_autenticacao_rejeitado(self):
        resposta = self.client.post(
            reverse("printing_api:poll"),
            data=json.dumps({}),
            content_type="application/json",
        )
        self.assertEqual(resposta.status_code, 401)

    def test_poll_com_token_invalido_rejeitado(self):
        resposta = self.client.post(
            reverse("printing_api:poll"),
            data=json.dumps({}),
            content_type="application/json",
            **cabecalhos(self.estacao, "token-errado"),
        )
        self.assertEqual(resposta.status_code, 401)

    def test_poll_entrega_job_e_marca_processando(self):
        venda = self.venda_finalizada()
        job = criar_print_job(venda)
        resposta = self.client.post(
            reverse("printing_api:poll"),
            data=json.dumps({"disponivel": True}),
            content_type="application/json",
            **cabecalhos(self.estacao, self.token),
        )
        self.assertEqual(resposta.status_code, 200)
        dados = resposta.json()
        self.assertEqual(dados["job"]["uuid"], str(job.uuid))
        self.assertEqual(dados["job"]["payload"]["venda"]["numero"], 1)
        job.refresh_from_db()
        self.assertEqual(job.status, PrintJob.Status.PROCESSING)
        self.assertEqual(job.estacao, self.estacao)

    def test_poll_com_impressora_indisponivel_nao_consome(self):
        venda = self.venda_finalizada()
        criar_print_job(venda)
        resposta = self.client.post(
            reverse("printing_api:poll"),
            data=json.dumps({"disponivel": False}),
            content_type="application/json",
            **cabecalhos(self.estacao, self.token),
        )
        self.assertIsNone(resposta.json()["job"])
        self.assertEqual(
            PrintJob.objects.for_tenant(self.tenant)
            .filter(status=PrintJob.Status.PENDING)
            .count(),
            1,
        )

    def test_resultado_impresso_e_falha(self):
        venda = self.venda_finalizada()
        job = criar_print_job(venda)
        self.client.post(
            reverse("printing_api:poll"),
            data=json.dumps({}),
            content_type="application/json",
            **cabecalhos(self.estacao, self.token),
        )
        resposta = self.client.post(
            reverse("printing_api:resultado", args=[job.uuid]),
            data=json.dumps({"status": "PRINTED"}),
            content_type="application/json",
            **cabecalhos(self.estacao, self.token),
        )
        self.assertEqual(resposta.status_code, 200)
        job.refresh_from_db()
        self.assertEqual(job.status, PrintJob.Status.PRINTED)

        venda2 = self.venda_finalizada()
        job2 = criar_print_job(venda2)
        self.client.post(
            reverse("printing_api:poll"),
            data=json.dumps({}),
            content_type="application/json",
            **cabecalhos(self.estacao, self.token),
        )
        resposta = self.client.post(
            reverse("printing_api:resultado", args=[job2.uuid]),
            data=json.dumps({"status": "FAILED", "erro": "Sem papel"}),
            content_type="application/json",
            **cabecalhos(self.estacao, self.token),
        )
        self.assertEqual(resposta.status_code, 200)
        job2.refresh_from_db()
        self.assertEqual(job2.status, PrintJob.Status.RETRYING)
        self.assertIn("Sem papel", job2.erro)

    def test_resultado_requer_job_da_propria_estacao(self):
        venda = self.venda_finalizada()
        job = criar_print_job(venda)
        resposta = self.client.post(
            reverse("printing_api:resultado", args=[job.uuid]),
            data=json.dumps({"status": "PRINTED"}),
            content_type="application/json",
            **cabecalhos(self.estacao, self.token),
        )
        self.assertEqual(resposta.status_code, 404)

    def test_isolamento_entre_tenants(self):
        outro_tenant = Tenant.objects.create(nome="Loja Vizinha")
        estacao_outra = EstacaoImpressao.objects.create(
            tenant=outro_tenant, nome="Caixa Alheia"
        )
        _, token_outra = parear_estacao(gerar_codigo_pareamento(estacao_outra))
        venda = self.venda_finalizada()
        criar_print_job(venda)
        resposta = self.client.post(
            reverse("printing_api:poll"),
            data=json.dumps({}),
            content_type="application/json",
            **cabecalhos(estacao_outra, token_outra),
        )
        self.assertIsNone(resposta.json()["job"])

    def test_status_invalido_no_resultado(self):
        venda = self.venda_finalizada()
        job = criar_print_job(venda)
        self.client.post(
            reverse("printing_api:poll"),
            data=json.dumps({}),
            content_type="application/json",
            **cabecalhos(self.estacao, self.token),
        )
        resposta = self.client.post(
            reverse("printing_api:resultado", args=[job.uuid]),
            data=json.dumps({"status": "QUALQUER"}),
            content_type="application/json",
            **cabecalhos(self.estacao, self.token),
        )
        self.assertEqual(resposta.status_code, 400)


class ThrottleTest(PrintingBaseTestCase):
    """Fase 0: freio de força bruta por IP (cache)."""

    def setUp(self):
        super().setUp()
        from django.core.cache import cache

        cache.clear()
        self.addCleanup(cache.clear)
        self.patcher = mock.patch("apps.printing.api.MAX_FALHAS_AUTENTICACAO", 3)
        self.patcher.start()
        self.addCleanup(self.patcher.stop)

    def test_bloqueia_poll_apos_muitas_falhas_de_autenticacao(self):
        url = reverse("printing_api:poll")
        estacao = EstacaoImpressao.objects.create(tenant=self.tenant, nome="X")
        for _ in range(3):
            resposta = self.client.post(
                url,
                data=json.dumps({}),
                content_type="application/json",
                **cabecalhos(estacao, "token-errado"),
            )
            self.assertEqual(resposta.status_code, 401)
        resposta = self.client.post(
            url, data=json.dumps({}), content_type="application/json"
        )
        self.assertEqual(resposta.status_code, 429)

    def test_bloqueia_pair_apos_muitos_codigos_invalidos(self):
        url = reverse("printing_api:pair")
        for _ in range(3):
            resposta = self.client.post(
                url,
                data=json.dumps({"codigo": "ZZZZZZ"}),
                content_type="application/json",
            )
            self.assertEqual(resposta.status_code, 400)
        resposta = self.client.post(
            url,
            data=json.dumps({"codigo": "ZZZZZZ"}),
            content_type="application/json",
        )
        self.assertEqual(resposta.status_code, 429)

    @mock.patch("apps.printing.api.settings")
    def test_throttle_usa_ip_real_atras_do_proxy(self, settings_fake):
        settings_fake.PDV_BEHIND_PROXY = True
        url = reverse("printing_api:pair")
        for _ in range(3):
            resposta = self.client.post(
                url,
                data=json.dumps({"codigo": "ZZZZZZ"}),
                content_type="application/json",
                HTTP_X_FORWARDED_FOR="200.100.50.1",
            )
            self.assertEqual(resposta.status_code, 400)
        # Outro cliente (IP diferente) não é bloqueado pelo balde do primeiro.
        resposta = self.client.post(
            url,
            data=json.dumps({"codigo": "ZZZZZZ"}),
            content_type="application/json",
            HTTP_X_FORWARDED_FOR="200.100.50.2",
        )
        self.assertEqual(resposta.status_code, 400)
        # O primeiro cliente, sim, está bloqueado.
        resposta = self.client.post(
            url,
            data=json.dumps({"codigo": "ZZZZZZ"}),
            content_type="application/json",
            HTTP_X_FORWARDED_FOR="200.100.50.1",
        )
        self.assertEqual(resposta.status_code, 429)

    @mock.patch("apps.printing.api.settings")
    def test_sem_proxy_ignora_x_forwarded_for(self, settings_fake):
        settings_fake.PDV_BEHIND_PROXY = False
        url = reverse("printing_api:pair")
        for _ in range(3):
            resposta = self.client.post(
                url,
                data=json.dumps({"codigo": "ZZZZZZ"}),
                content_type="application/json",
                HTTP_X_FORWARDED_FOR="200.100.50.9",
            )
            self.assertEqual(resposta.status_code, 400)
        # Sem proxy o cabeçalho é ignorado: todo mundo usa REMOTE_ADDR.
        resposta = self.client.post(
            url,
            data=json.dumps({"codigo": "ZZZZZZ"}),
            content_type="application/json",
            HTTP_X_FORWARDED_FOR="200.100.50.8",
        )
        self.assertEqual(resposta.status_code, 429)
