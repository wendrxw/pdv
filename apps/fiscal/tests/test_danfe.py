from decimal import Decimal

from django.test import TestCase

from ..danfe import montar_dados_danfe, url_qrcode_versao2
from ..models import NFCe
from ..service import hash_sha1
from ..xml_builder import FiscalError
from .factories import FiscalBaseTestCase


class QrCodeTest(TestCase):
    CHAVE = "35260812345678000195650010000001231000000420"

    def _url(self, id_csc="000001", token="csc-segredo"):
        return url_qrcode_versao2(
            chave=self.CHAVE,
            tp_amb="2",
            dh_emissao_epoch=1725200000,
            valor_total=Decimal("25.50"),
            digest_hex="ABCDEF0123",
            id_csc=id_csc,
            csc_token=token,
        )

    def test_url_deterministica_e_ordenada(self):
        url1 = self._url()
        url2 = self._url()
        self.assertEqual(url1, url2)
        self.assertIn(f"p={self.CHAVE}", url1)
        self.assertIn("|2|2|", url1)

    def test_token_csc_nunca_aparece_na_url(self):
        url = self._url(token="SEGREDO-DO-TOKEN")
        self.assertNotIn("SEGREDO-DO-TOKEN", url)

    def test_hash_sha1_inclui_componentes_oficiais(self):
        esperado = hash_sha1(
            f"{self.CHAVE}|2|2|1725200000|25.50|ABCDEF0123|000001|csc-segredo"
        )
        self.assertIn(esperado, self._url())

    def test_csc_ausente_rejeitado(self):
        with self.assertRaises(FiscalError):
            self._url(id_csc="", token="")


class MontarDanfeTest(FiscalBaseTestCase, TestCase):
    def test_nfce_nao_autorizada_sem_danfe(self):
        venda = self._venda_finalizada()
        nfce = NFCe.objects.create(
            tenant=self.tenant,
            venda=venda,
            numero=1,
            chave_acesso="3" * 44,
            dv=0,
            status=NFCe.Status.PENDENTE,
        )
        with self.assertRaises(FiscalError):
            montar_dados_danfe(nfce=nfce, emitente=self.emitente)
