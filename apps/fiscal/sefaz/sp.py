"""Cliente SEFAZ-SP homologação/produção — NF-e 4.00.

URLs oficiais CENTRALIZADAS por serviço (nunca espalhadas pelo código).
Fontes: Portal Nacional da NF-e / SEFAZ-SP. Confirmar credenciamento e
URLs vigentes antes de qualquer uso em PRODUÇÃO (fora de escopo).

Envelope SOAP 1.2 com cabeçalho nfeCabecMsg; TLS mútuo com certificado
A1; timeout obrigatório. HTTP 200 ≠ autorizado: decisão SEMPRE pelo
conteúdo interpretado por sefaz/parser.py.
"""

import requests

from ..certificate import CertificadoProvider
from .client import SefazClient, SefazError
from .parser import RetornoSefaz, parse_resposta

# Web services NF-e 4.00 da SEFAZ-SP.
_URLS_SP = {
    "HOMOLOGACAO": {
        "status": (
            "https://homologacao.nfe.fazenda.sp.gov.br/ws/"
            "nfestatusservico4.asmx"
        ),
        "autorizar": (
            "https://homologacao.nfe.fazenda.sp.gov.br/ws/"
            "nfeautorizacao4.asmx"
        ),
        "consulta": (
            "https://homologacao.nfe.fazenda.sp.gov.br/ws/"
            "nfeconsultaprotocolo4.asmx"
        ),
        "eventos": (
            "https://homologacao.nfe.fazenda.sp.gov.br/ws/"
            "nferecepcaoevento4.asmx"
        ),
        "inutilizar": (
            "https://homologacao.nfe.fazenda.sp.gov.br/ws/"
            "nfeinutilizacao4.asmx"
        ),
    },
    "PRODUCAO": {
        "status": "https://nfe.fazenda.sp.gov.br/ws/nfestatusservico4.asmx",
        "autorizar": "https://nfe.fazenda.sp.gov.br/ws/nfeautorizacao4.asmx",
        "consulta": (
            "https://nfe.fazenda.sp.gov.br/ws/nfeconsultaprotocolo4.asmx"
        ),
        "eventos": "https://nfe.fazenda.sp.gov.br/ws/nferecepcaoevento4.asmx",
        "inutilizar": "https://nfe.fazenda.sp.gov.br/ws/nfeinutilizacao4.asmx",
    },
}

VERSAO_DADOS = "4.00"


def urls_sefaz(uf: str = "SP", ambiente: str = "HOMOLOGACAO") -> dict:
    """Retorna o mapa de URLs do UF/ambiente (extensível a outras UFs)."""
    if uf != "SP":
        raise SefazError(
            f"UF {uf} ainda não suportada neste módulo (apenas SP)."
        )
    try:
        return _URLS_SP[ambiente]
    except KeyError as exc:
        raise SefazError(f"Ambiente desconhecido: {ambiente}.") from exc


class SefazSPClient(SefazClient):
    """Implementação SP dos web services NF-e 4.00."""

    def __init__(
        self,
        *,
        uf="SP",
        ambiente="HOMOLOGACAO",
        provider: CertificadoProvider,
        timeout: int = 30,
    ):
        self.uf = uf
        self.ambiente = ambiente
        self.urls = urls_sefaz(uf, ambiente)
        self.provider = provider
        self.timeout = timeout

    # ------------------------------------------------------------------
    # Transporte SOAP
    # ------------------------------------------------------------------

    def _soap(self, servico: str, corpo_xml: bytes) -> RetornoSefaz:
        envelope = _envelope_soap(servico, corpo_xml, self.uf)
        try:
            resposta = requests.post(
                self.urls[servico],
                data=envelope,
                headers={"Content-Type": "application/soap+xml"},
                cert=(self.provider.cert_pem, self.provider.key_pem),
                timeout=self.timeout,
            )
        except requests.Timeout as exc:
            raise SefazError(
                "Timeout na comunicação com a SEFAZ."
            ) from exc
        except requests.RequestException as exc:
            raise SefazError("Falha de conexão com a SEFAZ.") from exc
        if resposta.status_code != 200:
            # Erro HTTP não decide autorização; conteúdo pode trazer fault.
            pass
        return parse_resposta(resposta.text)

    # ------------------------------------------------------------------
    # Operações NF-e 4.00
    # ------------------------------------------------------------------

    def status_servico(self) -> RetornoSefaz:
        cuf = {"SP": "35"}.get(self.uf)
        xml = (
            '<consStatServ xmlns="http://www.portalfiscal.inf.br/nfe" '
            'versao="4.00">'
            f"<tpAmb>{_tp_amb(self.ambiente)}</tpAmb>"
            f"<cUF>{cuf}</cUF><xServ>STATUS</xServ></consStatServ>"
        ).encode()
        return self._soap("status", xml)

    def autorizar(self, lote_xml: bytes, timeout=None):
        return self._soap("autorizar", lote_xml)

    def consultar_protocolo(self, chave_acesso: str) -> RetornoSefaz:
        cuf = {"SP": "35"}.get(self.uf)
        xml = (
            '<consSitNFe xmlns="http://www.portalfiscal.inf.br/nfe" '
            'versao="4.00">'
            f"<tpAmb>{_tp_amb(self.ambiente)}</tpAmb>"
            f"<cUF>{cuf}</cUF><xServ>CONSULTAR</xServ>"
            f"<chNFe>{chave_acesso}</chNFe></consSitNFe>"
        ).encode()
        return self._soap("consulta", xml)

    def receber_evento(self, evento_xml: bytes) -> RetornoSefaz:
        return self._soap("eventos", evento_xml)

    def inutilizar(self, inutilizacao_xml: bytes) -> RetornoSefaz:
        return self._soap("inutilizar", inutilizacao_xml)


def _tp_amb(ambiente: str) -> str:
    return "1" if ambiente == "PRODUCAO" else "2"


def _envelope_soap(servico: str, corpo_xml: bytes, uf: str) -> bytes:
    """Envelope SOAP 1.2 padrão NF-e com nfeCabecMsg."""
    metodo = {
        "status": "nfeStatusServicoNF",
        "autorizar": "nfeAutorizacaoLote",
        "consulta": "nfeConsultaNF",
        "eventos": "nfeRecepcaoEvento",
        "inutilizar": "nfeInutilizacaoNF",
    }.get(servico, servico)
    wsdl = f"http://www.portalfiscal.inf.br/nfe/wsdl/{metodo}"
    cabecalho = (
        f'<nfeCabecMsg xmlns="{wsdl}">'
        f'<cUF>{"35" if uf == "SP" else uf}</cUF>'
        f"<versaoDados>{VERSAO_DADOS}</versaoDados></nfeCabecMsg>"
    )
    return (
        '<?xml version="1.0" encoding="utf-8"?>'
        '<soap12:Envelope '
        'xmlns:soap12="http://schemas.xmlsoap.org/soap/envelope/">'
        f"<soap12:Header>{cabecalho}</soap12:Header>"
        "<soap12:Body>"
        + corpo_xml.decode("utf-8")
        + "</soap12:Body></soap12:Envelope>"
    ).encode("utf-8")
