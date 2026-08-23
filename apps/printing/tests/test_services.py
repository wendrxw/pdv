"""Testes dos serviços: payload do comprovante, PrintJob, retry e pareamento."""

from datetime import timedelta
from decimal import Decimal

from django.utils import timezone

from apps.companies.models import Tenant
from apps.fiscal.models import Emitente
from apps.sales.services import (
    adicionar_item,
    adicionar_pagamento,
    finalizar_venda,
)

from ..models import ConfiguracaoImpressao, EstacaoImpressao, PrintJob
from ..services import (
    PrintingError,
    autenticar_estacao,
    criar_print_job,
    enfileirar_print_job_automatico,
    gerar_codigo_pareamento,
    marcar_falha,
    marcar_impresso,
    montar_dados_comprovante,
    obter_proximo_job,
    parear_estacao,
    reativar_print_job,
)
from .base import PrintingBaseTestCase


class DadosComprovanteTest(PrintingBaseTestCase):
    def setUp(self):
        super().setUp()
        self.config = ConfiguracaoImpressao.carregar(self.tenant)

    def test_produto_unico_com_centavos(self):
        venda = self.venda_finalizada(quantidade=Decimal("1"))
        dados = montar_dados_comprovante(venda, self.config)
        self.assertEqual(dados["cabecalho"]["nome"], self.tenant.nome)
        self.assertEqual(dados["venda"]["numero"], venda.numero)
        self.assertEqual(len(dados["itens"]), 1)
        self.assertEqual(dados["itens"][0]["preco_unitario"], "9.90")
        self.assertEqual(dados["totais"]["total"], "9.90")

    def test_desconto_e_pagamentos(self):
        from apps.sales.services import abrir_venda, aplicar_desconto

        venda = abrir_venda(self.caixa)
        adicionar_item(venda, self.produto, Decimal("2"), usuario=self.operador)
        venda.refresh_from_db()
        aplicar_desconto(venda, Decimal("1.90"))
        venda.refresh_from_db()
        adicionar_pagamento(venda, self.pix, venda.total)
        finalizar_venda(venda, usuario=self.operador)
        dados = montar_dados_comprovante(venda, self.config)
        self.assertEqual(dados["totais"]["desconto"], "1.90")
        self.assertEqual(dados["totais"]["total"], "17.90")
        self.assertEqual(dados["pagamentos"][0]["forma"], "PIX")
        self.assertEqual(dados["valor_recebido"], "0.00")
        self.assertEqual(dados["troco"], "0.00")

    def test_troco_zero_no_fluxo_atual(self):
        venda = self.venda_finalizada()
        dados = montar_dados_comprovante(venda, self.config)
        self.assertEqual(dados["valor_recebido"], "19.80")
        self.assertEqual(dados["troco"], "0.00")

    def test_nome_com_acentos_e_utf8(self):
        venda = self.venda_finalizada()
        dados = montar_dados_comprovante(venda, self.config)
        self.assertEqual(dados["itens"][0]["nome"], "Café Especial")

    def test_cabecalho_usa_emitente_fiscal_quando_config_vazia(self):
        Emitente.objects.create(
            tenant=self.tenant,
            cnpj="12345678000195",
            razao_social="Mercado Teste LTDA",
            nome_fantasia="Mercadinho do Zé",
            ie="123456789012",
            x_lgr="Rua A",
            nro="10",
            x_bairro="Centro",
            codigo_municipio_ibge="3550308",
            x_municipio="São Paulo",
            uf="SP",
            cep="01001000",
            fone="11999999999",
        )
        venda = self.venda_finalizada()
        dados = montar_dados_comprovante(venda, self.config)
        self.assertEqual(dados["cabecalho"]["nome"], "Mercadinho do Zé")
        self.assertEqual(dados["cabecalho"]["cnpj"], "12345678000195")
        self.assertIn("Rua A, 10, Centro, São Paulo-SP", dados["cabecalho"]["endereco"])

    def test_config_preenchida_tem_prioridade(self):
        self.config.nome_loja = "Loja Configurada"
        self.config.cnpj = "00000000000100"
        self.config.save()
        venda = self.venda_finalizada()
        dados = montar_dados_comprovante(venda, self.config)
        self.assertEqual(dados["cabecalho"]["nome"], "Loja Configurada")
        self.assertEqual(dados["cabecalho"]["cnpj"], "00000000000100")


class PrintJobTest(PrintingBaseTestCase):
    def test_cria_job_com_payload_e_identificador_unico(self):
        venda = self.venda_finalizada()
        job = criar_print_job(venda, usuario=self.operador)
        self.assertEqual(job.status, PrintJob.Status.PENDING)
        self.assertEqual(job.venda, venda)
        self.assertEqual(job.tentativa, 0)
        self.assertIn("totais", job.payload)
        self.assertIsNotNone(job.uuid)

    def test_venda_aberta_nao_gera_job(self):
        from apps.sales.services import abrir_venda

        venda = abrir_venda(self.caixa)
        with self.assertRaises(PrintingError):
            criar_print_job(venda)

    def test_idempotente_por_venda(self):
        venda = self.venda_finalizada()
        primeiro = criar_print_job(venda)
        segundo = criar_print_job(venda)
        self.assertEqual(primeiro.pk, segundo.pk)
        self.assertEqual(PrintJob.objects.for_tenant(self.tenant).count(), 1)

    def test_reimpressao_apos_impresso_cria_novo_job(self):
        venda = self.venda_finalizada()
        primeiro = criar_print_job(venda)
        primeiro.status = PrintJob.Status.PRINTED
        primeiro.save()
        segundo = criar_print_job(venda)
        self.assertNotEqual(primeiro.pk, segundo.pk)

    def test_automatica_cria_job_apenas_se_configurada(self):
        venda = self.venda_finalizada()
        config = ConfiguracaoImpressao.carregar(self.tenant)
        self.assertTrue(config.impressao_automatica)
        job = enfileirar_print_job_automatico(venda)
        self.assertIsNotNone(job)
        config.impressao_automatica = False
        config.save()
        venda2 = self.venda_finalizada()
        self.assertIsNone(enfileirar_print_job_automatico(venda2))


class FilaTest(PrintingBaseTestCase):
    def setUp(self):
        super().setUp()
        self.estacao = EstacaoImpressao.objects.create(
            tenant=self.tenant, nome="Caixa 01"
        )
        self.venda = self.venda_finalizada()

    def test_entrega_o_mais_antigo_e_marca_processando(self):
        criar_print_job(self.venda)
        venda2 = self.venda_finalizada()
        criar_print_job(venda2)
        job = obter_proximo_job(self.estacao)
        self.assertEqual(job.venda, self.venda)
        self.assertEqual(job.status, PrintJob.Status.PROCESSING)
        self.assertEqual(job.estacao, self.estacao)
        self.assertEqual(job.tentativa, 1)
        self.assertIsNotNone(job.data_processamento)

    def test_job_atribuido_a_outra_estacao_nao_vaza(self):
        outra = EstacaoImpressao.objects.create(tenant=self.tenant, nome="Caixa 02")
        job = criar_print_job(self.venda, estacao=outra)
        self.assertIsNone(obter_proximo_job(self.estacao))
        entregue = obter_proximo_job(outra)
        self.assertEqual(entregue.pk, job.pk)

    def test_isolamento_entre_tenants(self):
        outro_tenant = Tenant.objects.create(nome="Outra Loja")
        EstacaoImpressao.objects.create(tenant=outro_tenant, nome="Caixa Alheia")
        # Estação do outro tenant nunca recebe job deste tenant.
        criar_print_job(self.venda)
        estacao_outra = EstacaoImpressao.objects.get(tenant=outro_tenant)
        self.assertIsNone(obter_proximo_job(estacao_outra))

    def test_retrying_respeita_backoff(self):
        job = criar_print_job(self.venda)
        job.status = PrintJob.Status.RETRYING
        job.proxima_tentativa = timezone.now() + timedelta(minutes=5)
        job.save()
        self.assertIsNone(obter_proximo_job(self.estacao))
        job.proxima_tentativa = timezone.now() - timedelta(seconds=1)
        job.save()
        self.assertEqual(obter_proximo_job(self.estacao).pk, job.pk)

    def test_processando_parado_volta_para_fila(self):
        job = criar_print_job(self.venda)
        entregue = obter_proximo_job(self.estacao)
        self.assertEqual(entregue.pk, job.pk)
        # Impressora morreu no meio: lease expirado → retry agendado.
        entregue.data_processamento = timezone.now() - timedelta(minutes=10)
        entregue.save()
        self.assertIsNone(obter_proximo_job(self.estacao))
        entregue.refresh_from_db()
        self.assertEqual(entregue.status, PrintJob.Status.RETRYING)
        self.assertEqual(entregue.tentativa, 2)
        # Após o backoff, o mesmo job volta a ser entregue.
        entregue.proxima_tentativa = timezone.now() - timedelta(seconds=1)
        entregue.save()
        reprocessado = obter_proximo_job(self.estacao)
        self.assertEqual(reprocessado.pk, job.pk)
        self.assertEqual(reprocessado.status, PrintJob.Status.PROCESSING)
        self.assertEqual(reprocessado.tentativa, 3)

    def test_marcar_impresso(self):
        criar_print_job(self.venda)
        entregue = obter_proximo_job(self.estacao)
        marcar_impresso(entregue, self.estacao)
        entregue.refresh_from_db()
        self.assertEqual(entregue.status, PrintJob.Status.PRINTED)
        self.assertIsNotNone(entregue.data_impressao)

    def test_marcar_falha_agenda_retry_e_depois_falha_definitiva(self):
        criar_print_job(self.venda)
        entregue = obter_proximo_job(self.estacao)
        marcar_falha(entregue, self.estacao, "Sem papel")
        entregue.refresh_from_db()
        self.assertEqual(entregue.status, PrintJob.Status.RETRYING)
        self.assertIn("Sem papel", entregue.erro)
        self.assertGreater(entregue.proxima_tentativa, timezone.now())
        # Esgota as tentativas.
        entregue.tentativa = entregue.tentativas_maximas
        entregue.save()
        marcar_falha(entregue, self.estacao, "Sem papel de novo")
        entregue.refresh_from_db()
        self.assertEqual(entregue.status, PrintJob.Status.FAILED)

    def test_reativar_falha_volta_para_fila(self):
        criar_print_job(self.venda)
        entregue = obter_proximo_job(self.estacao)
        entregue.tentativa = entregue.tentativas_maximas
        entregue.save()
        marcar_falha(entregue, self.estacao, "x")
        entregue.refresh_from_db()
        reativar_print_job(entregue)
        entregue.refresh_from_db()
        self.assertEqual(entregue.status, PrintJob.Status.PENDING)
        self.assertEqual(entregue.tentativa, 0)
        self.assertEqual(entregue.erro, "")


class PareamentoTest(PrintingBaseTestCase):
    def test_fluxo_completo_de_pareamento(self):
        estacao = EstacaoImpressao.objects.create(tenant=self.tenant, nome="Caixa 01")
        codigo = gerar_codigo_pareamento(estacao)
        self.assertEqual(len(codigo), 6)
        self.assertNotIn("0", codigo)
        self.assertNotIn("O", codigo)
        pareada, token = parear_estacao(codigo)
        self.assertEqual(pareada.pk, estacao.pk)
        self.assertNotEqual(token, "")
        self.assertNotEqual(pareada.token_hash, token)
        self.assertEqual(pareada.codigo_pareamento, "")
        self.assertTrue(autenticar_estacao(str(estacao.uuid), token))
        # Código é de uso único.
        with self.assertRaises(PrintingError):
            parear_estacao(codigo)

    def test_codigo_invalido_rejeitado(self):
        with self.assertRaises(PrintingError):
            parear_estacao("ZZZZZZ")

    def test_token_errado_ou_estacao_inativa_nao_autentica(self):
        estacao = EstacaoImpressao.objects.create(tenant=self.tenant, nome="Caixa 01")
        codigo = gerar_codigo_pareamento(estacao)
        _, token = parear_estacao(codigo)
        self.assertIsNone(autenticar_estacao(str(estacao.uuid), "token-errado"))
        estacao.status = EstacaoImpressao.Status.INATIVA
        estacao.save()
        self.assertIsNone(autenticar_estacao(str(estacao.uuid), token))
        self.assertIsNone(autenticar_estacao("uuid-que-nao-existe", token))
