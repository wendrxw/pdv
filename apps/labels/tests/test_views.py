"""Testes das views de etiquetas (preparação, preview, impressão, status)."""

import json

from django.urls import reverse

from ..models import ConfiguracaoEtiqueta, EtiquetaJob
from .base import LabelsBaseTestCase, criar_contexto_outro


class ViewsBase(LabelsBaseTestCase):
    def setUp(self):
        super().setUp()
        self.client.force_login(self.operador)


class SelecaoViewTest(ViewsBase):
    def test_requer_login(self):
        self.client.logout()
        resposta = self.client.get(reverse("labels:selecao"))
        self.assertEqual(resposta.status_code, 302)

    def test_get_com_produtos_do_post(self):
        resposta = self.client.post(
            reverse("labels:selecao"),
            {
                "uuid": [str(self.produto_a.uuid), str(self.produto_b.uuid)],
                "quantidade": ["2", "1"],
            },
        )
        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, "Produto A")
        self.assertContains(resposta, "Produto B")
        self.assertContains(resposta, "Pré-visualização da bobina")

    def test_sem_produtos_mostra_aviso(self):
        resposta = self.client.get(reverse("labels:selecao"))
        self.assertContains(resposta, "Nenhum produto selecionado.")

    def test_produto_de_outro_tenant_ignorado(self):
        outro = criar_contexto_outro()
        resposta = self.client.post(
            reverse("labels:selecao"),
            {"uuid": [str(outro.produto_a.uuid)], "quantidade": ["1"]},
        )
        self.assertEqual(resposta.status_code, 200)
        self.assertNotContains(resposta, "Produto A")


class PreviewViewTest(ViewsBase):
    def test_preview_json_com_fileiras(self):
        resposta = self.client.post(
            reverse("labels:preview"),
            data=json.dumps(
                {
                    "produtos": [
                        {"uuid": str(self.produto_a.uuid), "quantidade": 3},
                        {"uuid": str(self.produto_b.uuid), "quantidade": 1},
                    ]
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(resposta.status_code, 200)
        dados = resposta.json()
        self.assertEqual(dados["resumo"]["etiquetas"], 4)
        self.assertEqual(dados["resumo"]["fileiras"], 2)
        self.assertEqual(dados["resumo"]["posicoes_vazias"], 0)
        self.assertEqual(dados["fileiras"][0][0]["nome"], "Produto A")
        self.assertEqual(dados["fileiras"][1][1]["nome"], "Produto B")

    def test_preview_impar_avisa_no_resumo(self):
        resposta = self.client.post(
            reverse("labels:preview"),
            data=json.dumps(
                {"produtos": [{"uuid": str(self.produto_a.uuid), "quantidade": 1}]}
            ),
            content_type="application/json",
        )
        dados = resposta.json()
        self.assertEqual(dados["resumo"]["posicoes_vazias"], 1)
        self.assertIsNone(dados["fileiras"][0][1])

    def test_preview_produto_de_outro_tenant_400(self):
        outro = criar_contexto_outro()
        resposta = self.client.post(
            reverse("labels:preview"),
            data=json.dumps(
                {"produtos": [{"uuid": str(outro.produto_a.uuid), "quantidade": 1}]}
            ),
            content_type="application/json",
        )
        self.assertEqual(resposta.status_code, 400)

    def test_preview_quantidade_invalida_400(self):
        resposta = self.client.post(
            reverse("labels:preview"),
            data=json.dumps(
                {"produtos": [{"uuid": str(self.produto_a.uuid), "quantidade": 0}]}
            ),
            content_type="application/json",
        )
        self.assertEqual(resposta.status_code, 400)


class ImpressaoViewTest(ViewsBase):
    def test_imprimir_cria_job_com_ordem(self):
        resposta = self.client.post(
            reverse("labels:imprimir"),
            {
                "uuid": [str(self.produto_b.uuid), str(self.produto_a.uuid)],
                "quantidade": ["1", "2"],
            },
        )
        job = EtiquetaJob.objects.for_tenant(self.tenant).get()
        self.assertRedirects(resposta, reverse("labels:status", args=[job.uuid]))
        fileiras = job.payload["fileiras"]
        # Ordem preservada: B, A, A → [B, A], [A, None]
        self.assertEqual(fileiras[0][0]["nome"], "Produto B")
        self.assertEqual(fileiras[0][1]["nome"], "Produto A")
        self.assertEqual(fileiras[1][0]["nome"], "Produto A")
        self.assertIsNone(fileiras[1][1])

    def test_imprimir_sem_produtos_redireciona(self):
        resposta = self.client.post(reverse("labels:imprimir"), {})
        self.assertRedirects(resposta, reverse("labels:selecao"))
        self.assertEqual(EtiquetaJob.objects.count(), 0)

    def test_calibrar_cria_job(self):
        resposta = self.client.post(reverse("labels:calibrar"))
        job = EtiquetaJob.objects.for_tenant(self.tenant).get()
        self.assertEqual(job.payload["tipo"], "calibracao")
        self.assertRedirects(resposta, reverse("labels:status", args=[job.uuid]))


class StatusViewTest(ViewsBase):
    def test_status_pagina_mostra_resumo(self):
        job = self.client_post_job()
        resposta = self.client.get(reverse("labels:status", args=[job.uuid]))
        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, "etiqueta(s)")

    def test_status_json(self):
        job = self.client_post_job()
        resposta = self.client.get(reverse("labels:status_json", args=[job.uuid]))
        dados = resposta.json()
        self.assertEqual(dados["job"]["status"], "PENDING")
        self.assertEqual(dados["estado"], "AGUARDANDO_AGENTE")

    def test_status_de_outro_tenant_404(self):
        outro = criar_contexto_outro()
        job = criar_job_outro(outro)
        resposta = self.client.get(reverse("labels:status", args=[job.uuid]))
        self.assertEqual(resposta.status_code, 404)

    def test_tentar_novamente_reativa(self):
        job = self.client_post_job()
        job.status = EtiquetaJob.Status.FAILED
        job.save()
        resposta = self.client.post(reverse("labels:tentar_novamente", args=[job.uuid]))
        job.refresh_from_db()
        self.assertEqual(job.status, EtiquetaJob.Status.PENDING)
        self.assertRedirects(resposta, reverse("labels:status", args=[job.uuid]))

    def client_post_job(self):
        from ..services import criar_etiqueta_job

        return criar_etiqueta_job(
            self.tenant,
            self.itens((self.produto_a, 2)),
            usuario=self.operador,
        )


def criar_job_outro(base):
    from ..services import criar_etiqueta_job

    return criar_etiqueta_job(
        base.tenant, [{"uuid": str(base.produto_a.uuid), "quantidade": 1}]
    )


class ConfigViewTest(ViewsBase):
    def test_config_get_e_post(self):
        resposta = self.client.get(reverse("labels:config"))
        self.assertEqual(resposta.status_code, 200)
        resposta = self.client.post(
            reverse("labels:config"),
            {
                "nome_impressora": "L42 Caixa 01",
                "dpi": 203,
                "largura_etiqueta": "50",
                "altura_etiqueta": "30",
                "gap_horizontal": "2",
                "gap_vertical": "2",
                "margem_esquerda": "1",
                "margem_superior": "1",
                "offset_horizontal": "0",
                "offset_vertical": "0",
                "mostrar_texto_codigo": "on",
                "quantidade_padrao": 2,
            },
        )
        self.assertEqual(resposta.status_code, 302)
        config = ConfiguracaoEtiqueta.carregar(self.tenant)
        self.assertEqual(str(config.largura_etiqueta), "50.0")
        self.assertEqual(config.quantidade_padrao, 2)


class ProdutosBuscaTest(ViewsBase):
    """Busca em tempo real da listagem de produtos (§1 da task)."""

    def test_busca_por_nome(self):
        resposta = self.client.get(reverse("products:busca"), {"q": "produto a"})
        resultados = resposta.json()["resultados"]
        self.assertEqual(len(resultados), 1)
        self.assertEqual(resultados[0]["nome"], "Produto A")

    def test_busca_por_codigo_barras(self):
        resposta = self.client.get(reverse("products:busca"), {"q": "789000000002"})
        resultados = resposta.json()["resultados"]
        self.assertEqual(len(resultados), 1)
        self.assertEqual(resultados[0]["nome"], "Produto B")

    def test_busca_por_sku(self):
        resposta = self.client.get(reverse("products:busca"), {"q": "C-1"})
        resultados = resposta.json()["resultados"]
        self.assertEqual(len(resultados), 1)
        self.assertEqual(resultados[0]["nome"], "Produto C")

    def test_busca_sem_resultados(self):
        resposta = self.client.get(reverse("products:busca"), {"q": "xyz"})
        self.assertEqual(resposta.json()["resultados"], [])

    def test_isolamento_entre_tenants(self):
        outro = criar_contexto_outro()
        resposta = self.client.get(reverse("products:busca"), {"q": "produto a"})
        uuids = [r["uuid"] for r in resposta.json()["resultados"]]
        self.assertNotIn(str(outro.produto_a.uuid), uuids)
        self.assertIn(str(self.produto_a.uuid), uuids)
