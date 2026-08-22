from decimal import Decimal

from django.test import TestCase

from ..models import NFCe
from ..sefaz.client import SefazClient, SefazError
from ..sefaz.parser import RetornoSefaz
from ..service import FiscalService
from .factories import FiscalBaseTestCase


class FakeSefazClient(SefazClient):
    """Dobra o web service: sem rede, sem XML real."""

    def __init__(self, cstat="100", protocolo="135260000123456",
                 falha_autorizar=False):
        self.cstat = cstat
        self.protocolo = protocolo
        self.falha_autorizar = falha_autorizar
        self.consultas = []

    def autorizar(self, lote_xml, timeout=None):
        if self.falha_autorizar:
            raise SefazError("Timeout na comunicação com a SEFAZ.")
        return self._resposta()

    def consultar_protocolo(self, chave_acesso):
        self.consultas.append(chave_acesso)
        retorno = self._resposta()
        retorno.extras["chave"] = chave_acesso
        return retorno

    def _resposta(self):
        autorizado = self.cstat in {"100", "150"}
        return RetornoSefaz(
            cstat=self.cstat,
            xmotivo="Autorizado o uso da NF-e"
            if autorizado
            else "Rejeição: duplicidade de NF-e",
            protocolo=self.protocolo if autorizado else "",
            xml="<retEnviNFe/>",
            autorizado=autorizado,
        )

    def status_servico(self):
        return RetornoSefaz(cstat="107", xmotivo="Serviço em operação",
                            autorizado=True)

    def receber_evento(self, evento_xml):
        raise NotImplementedError

    def inutilizar(self, inutilizacao_xml):
        raise NotImplementedError


class EmissaoTest(FiscalBaseTestCase, TestCase):
    def setUp(self):
        super().setUp()
        self.service = FiscalService(client=FakeSefazClient())

    def test_venda_nao_finalizada_rejeitada(self):
        from apps.sales.services import abrir_caixa, abrir_venda

        caixa = abrir_caixa(
            self.tenant,
            operador=self.operador,
            conta_financeira=self.conta,
        )
        venda = abrir_venda(caixa)
        with self.assertRaises(Exception) as ctx:
            self.service.emitir_nfce(venda)
        self.assertIn("finalizadas", str(ctx.exception))

    def test_fluxo_feliz_autoriza_com_protocolo(self):
        venda = self._venda_finalizada()
        nfce = self.service.emitir_nfce(venda)
        nfce.refresh_from_db()
        self.assertEqual(nfce.status, NFCe.Status.AUTORIZADA)
        self.assertTrue(nfce.protocolo.startswith("135"))
        self.assertEqual(len(nfce.chave_acesso), 44)
        self.assertNotEqual(nfce.xml_enviado, "")
        self.assertNotEqual(nfce.xml_assinado, "")

    def test_numero_reservado_e_incrementado(self):
        from ..models import ConfiguracaoFiscal

        venda = self._venda_finalizada()
        nfce = self.service.emitir_nfce(venda)
        self.assertEqual(nfce.numero, 1)
        config = ConfiguracaoFiscal.carregar(self.tenant)
        self.assertEqual(config.proximo_numero, 2)

    def test_segunda_emissao_mesma_venda_e_idempotente(self):
        venda = self._venda_finalizada()
        primeira = self.service.emitir_nfce(venda)
        segunda = self.service.emitir_nfce(venda)
        self.assertEqual(primeira.pk, segunda.pk)

    def test_numeracao_sequencial_entre_vendas(self):
        venda1 = self._venda_finalizada()
        nfce1 = self.service.emitir_nfce(venda1)
        venda2 = self._venda_finalizada(quantidade=Decimal("1"))
        nfce2 = self.service.emitir_nfce(venda2)
        self.assertEqual(nfce2.numero, nfce1.numero + 1)


class TimeoutERecuperacaoTest(FiscalBaseTestCase, TestCase):
    def test_timeout_mantem_transmitindo(self):
        service = FiscalService(
            client=FakeSefazClient(falha_autorizar=True)
        )
        venda = self._venda_finalizada()
        nfce = service.emitir_nfce(venda)
        nfce.refresh_from_db()
        self.assertEqual(nfce.status, NFCe.Status.TRANSMITINDO)
        # Nenhum código de rejeição gravado em falha de comunicação.
        self.assertEqual(nfce.codigo_rejeicao, "")

    def test_reemissao_apos_timeout_consulta_a_mesma_chave(self):
        client = FakeSefazClient(falha_autorizar=True)
        service = FiscalService(client=client)
        venda = self._venda_finalizada()
        primeira = service.emitir_nfce(venda)
        chave_primeira = primeira.chave_acesso

        client.falha_autorizar = False
        segunda = service.emitir_nfce(venda)
        segunda.refresh_from_db()
        self.assertEqual(segunda.pk, primeira.pk)
        self.assertEqual(segunda.status, NFCe.Status.AUTORIZADA)
        self.assertEqual(segunda.chave_acesso, chave_primeira)
        self.assertIn(chave_primeira, client.consultas)

    def test_rejeicao_204_grava_codigo_e_reemissao_reusa_numero(self):
        client = FakeSefazClient(cstat="204")
        service = FiscalService(client=client)
        venda = self._venda_finalizada()
        primeira = service.emitir_nfce(venda)
        primeira.refresh_from_db()
        self.assertEqual(primeira.status, NFCe.Status.REJEITADA)
        self.assertEqual(primeira.codigo_rejeicao, "204")
        self.assertIn("duplicidade", primeira.motivo_rejeicao.lower())

        client.cstat = "100"
        reemitida = service.emitir_nfce(venda)
        reemitida.refresh_from_db()
        self.assertEqual(reemitida.pk, primeira.pk)
        self.assertEqual(reemitida.numero, primeira.numero)
        self.assertEqual(reemitida.status, NFCe.Status.AUTORIZADA)
