"""Parser das respostas SOAP da SEFAZ → RetornoSefaz.

Distinção fundamental (tasks/TSK_00008.md):
- REJEIÇÃO: resposta válida com cStat de erro de negócio (ex.: 204
  duplicidade) → RetornoSefaz(autorizado=False);
- ERRO: falha de protocolo/comunicação (SOAP Fault, XML inválido) →
  SefazError.
HTTP 200 NÃO significa autorizado — a decisão vem SEMPRE do conteúdo.
"""

from dataclasses import dataclass, field
from xml.etree import ElementTree as ET

from .client import SefazError

NS_NFE = "http://www.portalfiscal.inf.br/nfe"
NS_SOAP_FAULT = "http://schemas.xmlsoap.org/soap/envelope/"


@dataclass
class RetornoSefaz:
    """Resposta estruturada de um web service da SEFAZ."""

    cstat: str
    xmotivo: str
    protocolo: str = ""
    xml: str = ""
    autorizado: bool = False
    extras: dict = field(default_factory=dict)

    CSTAT_AUTORIZACAO = {"100", "150"}  # autorizado / autorizado fora de prazo

    @property
    def rejeitado(self) -> bool:
        return not self.autorizado and self.cstat.isdigit()

    @property
    def duplicidade(self) -> bool:
        return self.cstat == "204"


def _texto(raiz, caminho: str) -> str:
    no = raiz.find(caminho, {"nfe": NS_NFE})
    return (no.text or "").strip() if no is not None and no.text else ""


def parse_resposta(xml_texto: str) -> RetornoSefaz:
    """Interpreta qualquer retorno NF-e conhecido.

    Procura na ordem: retConsStatServ, retEnviNFe (com protNFe),
    retConsReciNFe, retConsSitNFe, retEvento, retInutNFe.
    """
    try:
        raiz = ET.fromstring(xml_texto.encode("utf-8"))
    except ET.ParseError as exc:
        raise SefazError("Resposta SEFAZ não é XML válido.") from exc

    fault = raiz.find(f".//{{{NS_SOAP_FAULT}}}Fault")
    if fault is not None:
        motivo = fault.findtext(".//faultstring", default="SOAP Fault")
        raise SefazError(f"Falha SOAP da SEFAZ: {motivo}")

    xml_str = xml_texto if isinstance(xml_texto, str) else xml_texto.decode()

    # Consulta status do serviço
    no = raiz.find(f".//{{{NS_NFE}}}retConsStatServ")
    if no is not None:
        return RetornoSefaz(
            cstat=_texto(no, ".//xStat") or _texto(no, "cStat"),
            xmotivo=_texto(no, "xMotivo"),
            xml=xml_str,
            autorizado=_texto(no, "cStat") in {"107"},
            extras={"dhRetorno": _texto(no, "dhRetorno")},
        )

    # Autorização síncrona / consulta recibo / consulta situação
    for tag in ("retEnviNFe", "retConsReciNFe", "retConsSitNFe"):
        no = raiz.find(f".//{{{NS_NFE}}}{tag}")
        if no is None:
            continue
        cstat_no = no.find(f".//{{{NS_NFE}}}protNFe/{{{NS_NFE}}}infProt")
        if cstat_no is not None:
            cstat = _texto(cstat_no, "cStat")
            return RetornoSefaz(
                cstat=cstat,
                xmotivo=_texto(cstat_no, "xMotivo"),
                protocolo=_texto(cstat_no, "nProt"),
                xml=xml_str,
                autorizado=cstat in RetornoSefaz.CSTAT_AUTORIZACAO,
                extras={
                    "chave": _texto(cstat_no, "chNFe"),
                    "data_recebimento": _texto(cstat_no, "dhRecbto"),
                },
            )
        cstat = _texto(no, "cStat")
        return RetornoSefaz(
            cstat=cstat,
            xmotivo=_texto(no, "xMotivo"),
            xml=xml_str,
            autorizado=False,
        )

    # Eventos (cancelamento)
    no = raiz.find(f".//{{{NS_NFE}}}retEvento")
    if no is not None:
        inf_evento = no.find(f".//{{{NS_NFE}}}infEvento")
        cstat = _texto(inf_evento, "cStat") if inf_evento is not None else ""
        return RetornoSefaz(
            cstat=cstat,
            xmotivo=_texto(inf_evento, "xMotivo") if inf_evento is not None else "",
            protocolo=_texto(inf_evento, "nProt") if inf_evento is not None else "",
            xml=xml_str,
            autorizado=cstat in {"135", "136", "155"},
        )

    # Inutilização
    no = raiz.find(f".//{{{NS_NFE}}}retInutNFe")
    if no is not None:
        inf_inut = no.find(f".//{{{NS_NFE}}}infInut")
        cstat = _texto(inf_inut, "cStat") if inf_inut is not None else ""
        return RetornoSefaz(
            cstat=cstat,
            xmotivo=_texto(inf_inut, "xMotivo") if inf_inut is not None else "",
            xml=xml_str,
            autorizado=cstat in {"102"},
        )

    raise SefazError("Formato de resposta SEFAZ desconhecido.")
