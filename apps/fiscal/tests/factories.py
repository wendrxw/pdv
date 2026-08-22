"""Fábricas de teste do módulo fiscal.

PFX gerado em memória via cryptography (NUNCA certificado real).
"""

import os
import tempfile
from datetime import timedelta
from decimal import Decimal
from unittest import mock

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.serialization import pkcs12
from cryptography.x509.oid import NameOID
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from django.utils import timezone

from apps.accounts.models import User
from apps.companies.models import Tenant
from apps.financial.models import ContaFinanceira
from apps.financial.services import criar_conta, criar_forma_pagamento
from apps.inventory.services import adicionar_estoque
from apps.products.models import Produto
from apps.sales.services import (
    abrir_caixa,
    abrir_venda,
    adicionar_item,
    adicionar_pagamento,
    finalizar_venda,
)

SENHA_PFX = b"senha-teste-123"

MEDIA_TMP = tempfile.mkdtemp(prefix="pdv-fiscal-media-")


def gerar_pfx(senha: bytes = SENHA_PFX, valido_ate=None) -> bytes:
    """Gera um PFX autoassinado válido (ou expirado, se valido_ate passado)."""
    chave = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    nome = x509.Name(
        [x509.NameAttribute(NameOID.COMMON_NAME, "PDV Fiscal Teste")]
    )
    agora = timezone.now()
    if valido_ate is not None:
        inicio = min(valido_ate - timedelta(days=400), agora - timedelta(days=1))
        fim = valido_ate
    else:
        inicio = agora - timedelta(days=1)
        fim = agora + timedelta(days=365)
    certificado = (
        x509.CertificateBuilder()
        .subject_name(nome)
        .issuer_name(nome)
        .public_key(chave.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(inicio)
        .not_valid_after(fim)
        .add_extension(
            x509.BasicConstraints(ca=False, path_length=None),
            critical=True,
        )
        .add_extension(
            x509.KeyUsage(
                digital_signature=True,
                content_commitment=True,
                key_encipherment=True,
                data_encipherment=False,
                key_agreement=False,
                key_cert_sign=False,
                crl_sign=False,
                encipher_only=False,
                decipher_only=False,
            ),
            critical=True,
        )
        .add_extension(
            x509.ExtendedKeyUsage(
                [x509.oid.ExtendedKeyUsageOID.CLIENT_AUTH]
            ),
            critical=False,
        )
        .sign(chave, hashes.SHA256())
    )
    return pkcs12.serialize_key_and_certificates(
        name=b"pdv-teste",
        key=chave,
        cert=certificado,
        cas=None,
        encryption_algorithm=serialization.BestAvailableEncryption(senha),
    )


class FiscalBaseTestCase:
    """Base comum: tenant, emitente, configuração e venda finalizada."""

    senha_pfx = SENHA_PFX

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._media_override = override_settings(MEDIA_ROOT=MEDIA_TMP)
        cls._media_override.enable()

    @classmethod
    def tearDownClass(cls):
        cls._media_override.disable()
        super().tearDownClass()

    def setUp(self):
        super().setUp()
        # A senha do certificado vive SEMPRE em ambiente (§21); nos
        # testes injetamos a senha do PFX gerado.
        patcher = mock.patch.dict(
            os.environ,
            {"SEFAZ_CERTIFICATE_PASSWORD": self.senha_pfx.decode()},
        )
        patcher.start()
        self.addCleanup(patcher.stop)

        self.tenant = Tenant.objects.create(
            nome="Loja Fiscal", status=Tenant.Status.ATIVO
        )
        self.operador = User.objects.create_user(
            username="fiscalista", password="senha-12345", tenant=self.tenant
        )
        self.conta = criar_conta(
            self.tenant,
            nome="Gaveta Fiscal",
            tipo=ContaFinanceira.Tipo.CAIXA,
            saldo_inicial=Decimal("0.00"),
        )
        self.dinheiro = criar_forma_pagamento(
            self.tenant, nome="Dinheiro", codigo="DINHEIRO"
        )
        self.emitente = self.criar_emitente()
        from ..models import CertificadoDigital, ConfiguracaoFiscal

        # CSC fictício: só alimenta o hash local do QR Code nos testes.
        config = ConfiguracaoFiscal.carregar(self.tenant)
        config.id_csc = "000001"
        config.token_csc = "token-csc-de-teste"
        config.save()
        pfx = SimpleUploadedFile(
            "cert-teste.pfx", gerar_pfx(self.senha_pfx), "application/x-pkcs12"
        )
        self.certificado = CertificadoDigital.objects.create(
            tenant=self.tenant, arquivo=pfx, validade=timezone.now().date()
        )
        self.produto = Produto.objects.create(
            tenant=self.tenant,
            nome="Refrigerante Lata",
            preco_venda=Decimal("10.00"),
        )
        adicionar_estoque(self.produto, Decimal("100"))

    def criar_emitente(self):
        from ..models import Emitente

        return Emitente.objects.create(
            tenant=self.tenant,
            cnpj="12345678000195",
            razao_social="Mercado Teste LTDA",
            ie="123456789012",
            crt=Emitente.Crt.SIMPLES_NACIONAL,
            x_lgr="Rua das Palmeiras",
            nro="100",
            x_bairro="Centro",
            codigo_municipio_ibge="3550308",
            x_municipio="São Paulo",
            uf="SP",
            cep="01001000",
        )

    def _venda_finalizada(self, quantidade=Decimal("2")):
        from apps.sales.models import Caixa

        if not hasattr(self, "_caixa") or self._caixa is None:
            self._caixa = abrir_caixa(
                self.tenant,
                operador=self.operador,
                conta_financeira=self.conta,
                saldo_inicial=Decimal("50.00"),
            )
        else:
            self._caixa.refresh_from_db()
            if self._caixa.status != Caixa.Status.ABERTO:
                self._caixa = abrir_caixa(
                    self.tenant,
                    operador=self.operador,
                    conta_financeira=self.conta,
                )
        venda = abrir_venda(self._caixa)
        adicionar_item(venda, self.produto, quantidade, usuario=self.operador)
        venda.refresh_from_db()
        adicionar_pagamento(venda, self.dinheiro, venda.total)
        return finalizar_venda(venda, usuario=self.operador)
