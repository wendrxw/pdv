from decimal import Decimal
from xml.etree import ElementTree as ET

from django.test import TestCase

from ..chave import ChaveAcesso
from ..xml_builder import (
    FiscalError,
    NFCeBuilder,
    envelopar_lote,
    gerar_cnf,
)
from .factories import FiscalBaseTestCase

NS = {"nfe": "http://www.portalfiscal.inf.br/nfe"}


class BuilderBase(FiscalBaseTestCase, TestCase):
    def _builder(self, venda):
        chave = ChaveAcesso(
            cuf="35",
            aamm="2608",
            cnpj=self.emitente.cnpj,
            serie=1,
            numero=7,
            cnf="00000042",
        )
        builder = NFCeBuilder(
            venda=venda,
            emitente=self.emitente,
            numero=7,
            serie=1,
            cnf="00000042",
        )
        builder.chave = chave
        return builder, chave


class MontagemXmlTest(BuilderBase):
    def test_estrutura_completa_leiaute_400(self):
        venda = self._venda_finalizada()
        builder, chave = self._builder(venda)
        raiz = ET.fromstring(builder.montar())
        inf = raiz.find("nfe:infNFe", NS)
        self.assertIsNotNone(inf)
        self.assertEqual(inf.get("Id"), f"NFe{chave.completa}")
        self.assertEqual(inf.get("versao"), "4.00")
        for grupo in ("ide", "emit", "enderEmit", "total", "ICMSTot",
                      "transp", "pag"):
            self.assertIsNotNone(inf.find(f".//nfe:{grupo}", NS), grupo)
        self.assertEqual(inf.findtext(".//nfe:natOp", namespaces=NS),
                         "Venda de mercadoria")
        self.assertEqual(inf.findtext(".//nfe:mod", namespaces=NS), "65")
        self.assertEqual(inf.findtext(".//nfe:tpAmb", namespaces=NS), "2")

    def test_multiplos_itens_geram_multiplos_det(self):
        from apps.inventory.services import adicionar_estoque
        from apps.products.models import Produto
        from apps.sales.services import abrir_caixa, abrir_venda, adicionar_item

        outro = Produto.objects.create(
            tenant=self.tenant,
            nome="Chocolate",
            preco_venda=Decimal("7.50"),
        )
        adicionar_estoque(outro, Decimal("50"))
        caixa = abrir_caixa(
            self.tenant,
            operador=self.operador,
            conta_financeira=self.conta,
        )
        venda = abrir_venda(caixa)
        adicionar_item(venda, self.produto, Decimal("1"), usuario=self.operador)
        adicionar_item(venda, outro, Decimal("2"), usuario=self.operador)
        builder, _ = self._builder(venda)
        raiz = ET.fromstring(builder.montar())
        dets = raiz.findall(".//nfe:det", NS)
        self.assertEqual(len(dets), 2)

    def test_icmssn102_para_simples_nacional(self):
        venda = self._venda_finalizada()
        builder, _ = self._builder(venda)
        raiz = ET.fromstring(builder.montar())
        csosn = raiz.findtext(".//nfe:ICMSSN102/nfe:CSOSN", namespaces=NS)
        self.assertEqual(csosn, "102")

    def test_crt_regime_normal_rejeitado_sem_estrutura(self):
        from ..models import Emitente

        self.emitente.crt = Emitente.Crt.REGIME_NORMAL
        self.emitente.save()
        venda = self._venda_finalizada()
        builder, _ = self._builder(venda)
        with self.assertRaises(FiscalError):
            builder.montar()

    def test_total_confere_com_venda(self):
        venda = self._venda_finalizada(quantidade=Decimal("3"))
        builder, _ = self._builder(venda)
        raiz = ET.fromstring(builder.montar())
        vnf = raiz.findtext(".//nfe:vNF", namespaces=NS)
        self.assertEqual(Decimal(vnf), venda.total)

    def test_pagamento_dinheiro_mapeia_tpag_01(self):
        venda = self._venda_finalizada()
        builder, _ = self._builder(venda)
        raiz = ET.fromstring(builder.montar())
        tpag = raiz.findtext(".//nfe:detPag/nfe:tPag", namespaces=NS)
        self.assertEqual(tpag, "01")

    def test_frete_sem_ocorrencia_modfrete_9(self):
        venda = self._venda_finalizada()
        builder, _ = self._builder(venda)
        raiz = ET.fromstring(builder.montar())
        self.assertEqual(
            raiz.findtext(".//nfe:transp/nfe:modFrete", namespaces=NS), "9"
        )


class RejeicoesBuilderTest(BuilderBase):
    def test_venda_sem_itens_rejeitada(self):
        from apps.sales.services import abrir_caixa, abrir_venda

        caixa = abrir_caixa(
            self.tenant,
            operador=self.operador,
            conta_financeira=self.conta,
        )
        venda = abrir_venda(caixa)
        builder, _ = self._builder(venda)
        with self.assertRaises(FiscalError):
            builder.montar()

    def test_chave_obrigatoria_antes_de_montar(self):
        venda = self._venda_finalizada()
        builder = NFCeBuilder(
            venda=venda, emitente=self.emitente, numero=1, serie=1, cnf=None
        )
        with self.assertRaises(FiscalError):
            builder.montar()


class UtilidadesTest(TestCase):
    def test_cnf_tem_oito_digitos(self):
        cnf = gerar_cnf()
        self.assertEqual(len(cnf), 8)
        self.assertTrue(cnf.isdigit())

    def test_envelopar_lote_contem_nfe_e_ind_sinc(self):
        bruto = (
            '<NFe xmlns="http://www.portalfiscal.inf.br/nfe">'
            '<infNFe versao="4.00" Id="NFe123"/></NFe>'
        ).encode()
        lote = ET.fromstring(envelopar_lote(bruto))
        self.assertEqual(lote.tag, f"{{{NS['nfe']}}}enviNFe")
        self.assertEqual(lote.findtext(f"{{{NS['nfe']}}}indSinc"), "1")
        self.assertIsNotNone(lote.find(f".//{{{NS['nfe']}}}NFe"))
