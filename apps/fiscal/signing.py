"""Assinatura XMLDSig da NFC-e conforme padrão NF-e.

- assina o elemento infNFe (Reference URI="#NFe{chave}");
- RSA-SHA256, digest SHA-256;
- canonicalização C14N 1.0 (REC-xml-c14n-20010315) exigida pelo manual.

Implementação criptográfica artesanal é PROIBIDA — usamos signxml.
"""

from lxml import etree
from signxml import XMLSigner, XMLVerifier, methods

from .certificate import CertificadoProvider
from .xml_builder import FiscalError

C14N_INCLUSIVE = "http://www.w3.org/TR/2001/REC-xml-c14n-20010315"

# signxml é construído sobre lxml; usar o parser dele evita diferenças
# sutis de canonicalização entre stdlib ET e lxml.
_signer = XMLSigner(
    method=methods.enveloped,
    c14n_algorithm=C14N_INCLUSIVE,
)


def assinar_nfce(xml_nfe: bytes, provider: CertificadoProvider, chave: str) -> bytes:
    """Insere a Signature no XML da NFe e retorna o documento assinado.

    ``chave`` é a chave de acesso de 44 dígitos (usada no Reference).
    """
    try:
        elemento = etree.fromstring(xml_nfe)
        assinado = _signer.sign(
            elemento,
            key=provider.key,
            cert=provider.cert_pem.decode(),
            reference_uri=f"#NFe{chave}",
        )
        return etree.tostring(
            assinado,
            xml_declaration=True,
            encoding="UTF-8",
        )
    except FiscalError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise FiscalError("Falha ao assinar o XML da NFC-e.") from exc


def verificar_assinatura(xml_assinado: bytes, certificado=None) -> bool:
    """Valida criptograficamente a assinatura do documento."""
    try:
        if certificado is None:
            XMLVerifier().verify(xml_assinado)
        else:
            XMLVerifier().verify(xml_assinado, x509_cert=certificado)
        return True
    except Exception:
        return False
