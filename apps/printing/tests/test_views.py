"""Testes das views da loja (config, estações) e integração com o PDV."""

from decimal import Decimal

from django.urls import reverse

from apps.companies.models import Tenant
from apps.sales.models import Venda
from apps.sales.services import abrir_venda, adicionar_item

from ..models import ConfiguracaoImpressao, EstacaoImpressao, PrintJob
from .base import PrintingBaseTestCase


class ViewsBase(PrintingBaseTestCase):
    def setUp(self):
        super().setUp()
        self.client.force_login(self.operador)


class ConfigImpressaoViewTest(ViewsBase):
    def test_requer_login(self):
        self.client.logout()
        resposta = self.client.get(reverse("printing:config"))
        self.assertEqual(resposta.status_code, 302)

    def test_get_mostra_formulario(self):
        resposta = self.client.get(reverse("printing:config"))
        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, "Configuração de impressão")

    def test_post_salva_configuracao(self):
        estacao = EstacaoImpressao.objects.create(tenant=self.tenant, nome="Caixa 01")
        resposta = self.client.post(
            reverse("printing:config"),
            {
                "largura": "80",
                "estacao_padrao": str(estacao.pk),
                "impressora_fiscal": "Elgin i9",
                "tentativas_maximas": 7,
                "nome_loja": "Loja Nova",
                "cnpj": "00000000000100",
                "endereco": "Rua 1",
                "telefone": "(11) 99999-9999",
                "mensagem_final": "Até logo!",
            },
        )
        self.assertEqual(resposta.status_code, 302)
        config = ConfiguracaoImpressao.carregar(self.tenant)
        self.assertEqual(config.largura, "80")
        self.assertEqual(config.nome_loja, "Loja Nova")
        self.assertEqual(config.impressora_fiscal, "Elgin i9")
        self.assertEqual(config.estacao_padrao, estacao)

    def test_usuario_sem_tenant_redireciona(self):
        from apps.accounts.models import User

        staff = User.objects.create_user(username="staff-print", password="senha-12345")
        self.client.force_login(staff)
        resposta = self.client.get(reverse("printing:config"))
        self.assertEqual(resposta.status_code, 302)


class AtalhoCaixaViewTest(ViewsBase):
    def test_requer_login(self):
        self.client.logout()
        resposta = self.client.get(reverse("printing:atalho_caixa"))
        self.assertEqual(resposta.status_code, 302)

    def test_gera_atalho_windows_com_fullscreen(self):
        resposta = self.client.get(
            reverse("printing:atalho_caixa"), HTTP_USER_AGENT="Windows NT 10.0"
        )
        self.assertEqual(resposta.status_code, 200)
        conteudo = resposta.content.decode()
        self.assertIn("[InternetShortcut]", conteudo)
        self.assertIn("fullscreen=1", conteudo)
        self.assertIn("PDV - Frente de Caixa.url", resposta["Content-Disposition"])

    def test_gera_atalho_linux(self):
        resposta = self.client.get(
            reverse("printing:atalho_caixa"), HTTP_USER_AGENT="Linux x86_64"
        )
        self.assertEqual(resposta.status_code, 200)
        self.assertIn("[Desktop Entry]", resposta.content.decode())
        self.assertIn("fullscreen=1", resposta.content.decode())


class EstacoesViewTest(ViewsBase):
    def test_criar_estacao_gera_codigo(self):
        resposta = self.client.post(
            reverse("printing:estacoes"),
            {"acao": "criar", "nome": "Caixa 01"},
            follow=True,
        )
        self.assertEqual(resposta.status_code, 200)
        estacao = EstacaoImpressao.objects.get(tenant=self.tenant)
        self.assertIsNotNone(estacao.codigo_pareamento)
        self.assertContains(resposta, estacao.codigo_pareamento)

    def test_acoes_por_estacao(self):
        estacao = EstacaoImpressao.objects.create(tenant=self.tenant, nome="Caixa 01")
        resposta = self.client.post(
            reverse("printing:estacoes"),
            {"acao": "inativar", "estacao": str(estacao.uuid)},
            follow=True,
        )
        estacao.refresh_from_db()
        self.assertEqual(estacao.status, EstacaoImpressao.Status.INATIVA)
        self.assertEqual(resposta.status_code, 200)

    def test_estacao_de_outro_tenant_inacessivel(self):
        outro = Tenant.objects.create(nome="Outra")
        alheia = EstacaoImpressao.objects.create(tenant=outro, nome="Caixa Alheia")
        resposta = self.client.post(
            reverse("printing:estacoes"),
            {"acao": "remover", "estacao": str(alheia.uuid)},
        )
        self.assertEqual(resposta.status_code, 404)


class StatusVendaViewTest(ViewsBase):
    def test_status_sem_job(self):
        venda = self.venda_finalizada()
        resposta = self.client.get(reverse("printing:status_venda", args=[venda.uuid]))
        self.assertEqual(resposta.json()["estado"], "SEM_JOB")
        self.assertIsNone(resposta.json()["job"])

    def test_status_pendente_sem_estacao(self):
        from ..services import criar_print_job

        venda = self.venda_finalizada()
        job = criar_print_job(venda)
        resposta = self.client.get(reverse("printing:status_venda", args=[venda.uuid]))
        dados = resposta.json()
        self.assertEqual(dados["job"]["status"], "PENDING")
        self.assertEqual(dados["job"]["uuid"], str(job.uuid))
        # Sem estação ativa, o painel avisa que falta o agente.
        self.assertEqual(dados["estado"], "AGUARDANDO_AGENTE")
        self.assertEqual(dados["estacoes"]["ativas"], 0)

    def test_status_pendente_com_estacao_ativa(self):
        from ..services import criar_print_job

        EstacaoImpressao.objects.create(tenant=self.tenant, nome="Caixa 01")
        venda = self.venda_finalizada()
        criar_print_job(venda)
        resposta = self.client.get(reverse("printing:status_venda", args=[venda.uuid]))
        dados = resposta.json()
        self.assertEqual(dados["estado"], "AGUARDANDO_IMPRESSORA")
        self.assertEqual(dados["estacoes"]["ativas"], 1)


class PdvIntegracaoTest(ViewsBase):
    def test_finalizar_venda_sempre_enfileira_comprovante(self):
        venda = abrir_venda(self.caixa)
        adicionar_item(venda, self.produto, Decimal("1"), usuario=self.operador)
        venda.refresh_from_db()
        resposta = self.client.post(
            reverse("sales:venda_tela", args=[venda.uuid]),
            {
                "acao": "finalizar",
                "forma_pagamento": str(self.dinheiro.uuid),
            },
        )
        self.assertEqual(resposta.status_code, 302)
        venda.refresh_from_db()
        self.assertEqual(venda.status, Venda.Status.FINALIZADA)
        self.assertEqual(
            PrintJob.objects.for_tenant(self.tenant).filter(venda=venda).count(),
            1,
        )

    def test_finalizar_sem_configuracao_tambem_enfileira(self):
        # Impressão é OBRIGATÓRIA: mesmo sem nenhuma configuração manual,
        # finalizar a venda enfileira o comprovante.
        venda = abrir_venda(self.caixa)
        adicionar_item(venda, self.produto, Decimal("1"), usuario=self.operador)
        venda.refresh_from_db()
        self.client.post(
            reverse("sales:venda_tela", args=[venda.uuid]),
            {
                "acao": "finalizar",
                "forma_pagamento": str(self.dinheiro.uuid),
            },
        )
        self.assertEqual(
            PrintJob.objects.for_tenant(self.tenant).filter(venda=venda).count(),
            1,
        )

    def test_detalhe_imprimir_cria_job_manual(self):
        venda = self.venda_finalizada()
        resposta = self.client.post(
            reverse("sales:venda_detalhe", args=[venda.uuid]),
            {"acao": "imprimir"},
        )
        self.assertEqual(resposta.status_code, 302)
        self.assertEqual(
            PrintJob.objects.for_tenant(self.tenant).filter(venda=venda).count(),
            1,
        )

    def test_detalhe_tentar_novamente_reativa_job_falho(self):
        from ..services import criar_print_job, marcar_falha

        venda = self.venda_finalizada()
        estacao = EstacaoImpressao.objects.create(tenant=self.tenant, nome="Caixa 01")
        job = criar_print_job(venda, estacao=estacao)
        job.status = PrintJob.Status.PROCESSING
        job.tentativa = job.tentativas_maximas
        job.save()
        marcar_falha(job, estacao, "Sem papel")
        resposta = self.client.post(
            reverse("sales:venda_detalhe", args=[venda.uuid]),
            {"acao": "tentar_novamente"},
        )
        self.assertEqual(resposta.status_code, 302)
        job.refresh_from_db()
        self.assertEqual(job.status, PrintJob.Status.PENDING)

    def test_detalhe_mostra_painel_de_impressao(self):
        venda = self.venda_finalizada()
        resposta = self.client.get(reverse("sales:venda_detalhe", args=[venda.uuid]))
        self.assertContains(resposta, "Imprimir comprovante")

    def test_detalhe_com_job_sem_estacao_mostra_aguardando_agente(self):
        # Venda finalizada gera job obrigatório; sem estação ativa o
        # painel deve explicar que falta o agente (não só "Imprimindo...").
        venda = abrir_venda(self.caixa)
        adicionar_item(venda, self.produto, Decimal("1"), usuario=self.operador)
        venda.refresh_from_db()
        self.client.post(
            reverse("sales:venda_tela", args=[venda.uuid]),
            {"acao": "finalizar", "forma_pagamento": str(self.dinheiro.uuid)},
        )
        resposta = self.client.get(reverse("sales:venda_detalhe", args=[venda.uuid]))
        self.assertContains(resposta, "Aguardando o agente de impressão")

    def test_detalhe_com_job_e_estacao_mostra_aguardando_impressora(self):
        EstacaoImpressao.objects.create(tenant=self.tenant, nome="Caixa 01")
        venda = abrir_venda(self.caixa)
        adicionar_item(venda, self.produto, Decimal("1"), usuario=self.operador)
        venda.refresh_from_db()
        self.client.post(
            reverse("sales:venda_tela", args=[venda.uuid]),
            {"acao": "finalizar", "forma_pagamento": str(self.dinheiro.uuid)},
        )
        resposta = self.client.get(reverse("sales:venda_detalhe", args=[venda.uuid]))
        self.assertContains(resposta, "Aguardando impressora…")

    def test_cancelamento_pelo_detalhe_continua_funcionando(self):
        venda = abrir_venda(self.caixa)
        adicionar_item(venda, self.produto, Decimal("1"), usuario=self.operador)
        venda.refresh_from_db()
        resposta = self.client.post(
            reverse("sales:venda_detalhe", args=[venda.uuid]),
            {"motivo": "Erro"},
        )
        venda.refresh_from_db()
        self.assertEqual(venda.status, Venda.Status.CANCELADA)
        self.assertEqual(resposta.status_code, 302)
