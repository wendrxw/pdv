from xml.etree import ElementTree as ET

from django.test import TestCase

from ..certificate import CertificadoProvider
from ..chave import ChaveAcesso
from ..signing import assinar_nfce, verificar_assinatura
from .factories import SENHA_PFX, gerar_pfx


class AssinaturaTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.provider = CertificadoProvider.carregar(
            gerar_pfx(SENHA_PFX), SENHA_PFX
        )
        chave = ChaveAcesso(cuf="35", aamm="2608", cnpj="12345678000195")
        cls.chave_str = chave.completa
        cls.xml = (
            '<NFe xmlns="http://www.portalfiscal.inf.br/nfe">'
            f'<infNFe versao="4.00" Id="NFe{cls.chave_str}">'
            "<ide><nNF>1</nNF></ide></infNFe></NFe>"
        ).encode()

    def test_assina_e_verifica(self):
        assinado = assinar_nfce(self.xml, self.provider, self.chave_str)
        raiz = ET.fromstring(assinado)
        assinatura = raiz.find(
            ".//{http://www.w3.org/2000/09/xmldsig#}Signature"
        )
        self.assertIsNotNone(assinatura)
        # Certificado autoassinado: verificamos contra o próprio
        # certificado (equivale a pinar a cadeia ICP-Brasil).
        self.assertTrue(
            verificar_assinatura(assinado, certificado=self.provider.cert)
        )

    def test_reference_uri_aponta_para_inf_nfe(self):
        assinado = assinar_nfce(self.xml, self.provider, self.chave_str)
        conteudo = assinado.decode()
        self.assertIn(f'Reference URI="#NFe{self.chave_str}"', conteudo)

    def test_xml_adulterado_falha_na_verificacao(self):
        assinado = assinar_nfce(self.xml, self.provider, self.chave_str)
        adulterado = assinado.replace(b"<nNF>1</nNF>", b"<nNF>2</nNF>")
        self.assertFalse(
            verificar_assinatura(adulterado, certificado=self.provider.cert)
        )
