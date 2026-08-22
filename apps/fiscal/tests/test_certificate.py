import tempfile
from datetime import timedelta

from django.test import TestCase, override_settings
from django.utils import timezone

from ..certificate import (
    CertificadoError,
    CertificadoExpirado,
    CertificadoProvider,
)
from .factories import SENHA_PFX, gerar_pfx


class CarregamentoTest(TestCase):
    def test_carregar_de_bytes(self):
        pfx = gerar_pfx()
        provider = CertificadoProvider.carregar(pfx, SENHA_PFX)
        self.assertIsNotNone(provider.key)
        self.assertIsNotNone(provider.cert)
        futuro = provider.expires_at > timezone.now()
        self.assertTrue(futuro)

    def test_carregar_de_caminho_em_disco(self):
        with tempfile.NamedTemporaryFile(suffix=".pfx") as arquivo:
            arquivo.write(gerar_pfx())
            arquivo.flush()
            provider = CertificadoProvider.carregar(
                arquivo.name, SENHA_PFX
            )
        self.assertIn("BEGIN CERTIFICATE", provider.cert_pem.decode())

    def test_senha_errada_levanta_erro_claro_sem_vazar_segredo(self):
        with self.assertRaises(CertificadoError) as ctx:
            CertificadoProvider.carregar(gerar_pfx(), b"errada")
        mensagem = str(ctx.exception)
        self.assertNotIn(SENHA_PFX.decode(), mensagem)

    def test_arquivo_inexistente(self):
        with self.assertRaises(CertificadoError):
            CertificadoProvider.carregar("/tmp/inexistente.pfx", SENHA_PFX)


class ValidadeTest(TestCase):
    def test_certificado_expirado_rejeitado(self):
        expirado = gerar_pfx(valido_ate=timezone.now() - timedelta(days=1))
        with self.assertRaises(CertificadoExpirado):
            CertificadoProvider.carregar(expirado, SENHA_PFX)

    @override_settings()
    def test_vencimento_proximo_emite_warning(self):
        quase = gerar_pfx(
            valido_ate=timezone.now() + timedelta(days=10)
        )
        with self.assertLogs("pdv.fiscal", level="WARNING"):
            CertificadoProvider.carregar(quase, SENHA_PFX)
