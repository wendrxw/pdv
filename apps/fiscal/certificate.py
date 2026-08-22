"""Certificado digital A1 (PFX/P12) para assinatura fiscal.

Regras de segurança (docs/general.md §5/§21):
- a senha vive APENAS em variável de ambiente (`SEFAZ_CERTIFICATE_PASSWORD`);
- nunca registrar senha, chave privada ou material criptográfico em logs;
- erros são reportados com mensagens claras sem vazar segredos.
"""

import logging
from datetime import datetime
from datetime import timezone as dt_timezone

from cryptography import x509
from cryptography.hazmat.primitives.serialization import Encoding, pkcs12

logger = logging.getLogger("pdv.fiscal")


class CertificadoError(Exception):
    """Falha ao carregar/validar certificado A1."""


class CertificadoExpirado(CertificadoError):
    """Certificado fora da validade."""


class CertificadoProvider:
    """Carrega um PFX/P12 e expõe chave/certificado prontos para uso.

    Uso::

        provider = CertificadoProvider.carregar(caminho, senha)
        provider.key          # chave privada
        provider.cert         # certificado x509
        provider.cert_pem     # certificado serializado em PEM (bytes)
        provider.expires_at   # datetime UTC
    """

    def __init__(self, key, cert, expires_at):
        self._key = key
        self._cert = cert
        self._expires_at = expires_at
        self._validar_validade()

    @classmethod
    def carregar(cls, arquivo_bytes_or_path, senha: bytes) -> "CertificadoProvider":
        """Aceita caminho no disco ou conteúdo bruto do PFX."""
        if isinstance(arquivo_bytes_or_path, (bytes, bytearray)):
            conteudo = bytes(arquivo_bytes_or_path)
        else:
            try:
                with open(arquivo_bytes_or_path, "rb") as fh:
                    conteudo = fh.read()
            except OSError as exc:
                raise CertificadoError(
                    f"Não foi possível ler o certificado: {exc.strerror}."
                ) from exc
        try:
            key, cert, _extras = pkcs12.load_key_and_certificates(
                conteudo, senha
            )
        except ValueError as exc:
            logger.info(
                "Falha ao abrir certificado A1 (senha incorreta ou arquivo "
                "inválido)."
            )
            raise CertificadoError(
                "Certificado inválido ou senha incorreta."
            ) from exc
        if key is None or cert is None:
            raise CertificadoError("Certificado não contém chave privada.")
        expires = cls._extrair_validade(cert)
        return cls(key=key, cert=cert, expires_at=expires)

    @staticmethod
    def _extrair_validade(cert) -> datetime:
        campo = getattr(cert, "not_valid_after_utc", None)
        if campo is None:  # cryptography < 42
            campo = cert.not_valid_after.replace(tzinfo=dt_timezone.utc)
        return campo

    def _validar_validade(self):
        agora = datetime.now(dt_timezone.utc)
        if self._expires_at <= agora:
            raise CertificadoExpirado(
                "Certificado digital expirado em "
                f"{self._expires_at:%d/%m/%Y}."
            )
        dias_restantes = (self._expires_at - agora).days
        if 0 <= dias_restantes < 30:
            logger.warning(
                "Certificado digital vence em menos de 30 dias (%s).",
                self._expires_at.date(),
            )

    @property
    def key(self):
        return self._key

    @property
    def cert(self):
        return self._cert

    @property
    def cert_pem(self) -> bytes:
        return self._cert.public_bytes(Encoding.PEM)

    @property
    def key_pem(self) -> bytes:
        """Chave privada serializada em PEM sem criptografia.

        Exportada apenas para uso interno da conexão TLS/SOAP — jamais
        logada ou persistida.
        """
        from cryptography.hazmat.primitives.serialization import (
            NoEncryption,
            PrivateFormat,
        )

        return self._key.private_bytes(
            encoding=Encoding.PEM,
            format=PrivateFormat.TraditionalOpenSSL,
            encryption_algorithm=NoEncryption(),
        )

    @property
    def expires_at(self) -> datetime:
        return self._expires_at

    @staticmethod
    def extrair_certificado_de_pfx(
        conteudo_pfx: bytes, senha: bytes
    ) -> x509.Certificate:
        """Helper para testes/utilitários: retorna apenas o certificado."""
        cert, *_ = pkcs12.load_key_and_certificates(conteudo_pfx, senha)[:3]
        return cert
