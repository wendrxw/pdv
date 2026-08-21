"""Construtor do XML da NFC-e — leiaute 4.00 (modelo 65).

Regras (docs/general.md §6, tasks/TSK_00008.md):
- geração via objetos de domínio (ElementTree), nunca concatenação manual;
- SEM valores fictícios: falta de dado obrigatório levanta FiscalError;
- grupos: ide, emit(+enderEmit), dest(opcional), det/prod/ICMS, total,
  transp, pag/detPag, infAdic.

Decisões provisórias DOCUMENTADAS (até existir a estrutura fiscal por
produto — fora do escopo desta fase):
- NCM 99999999 ("não aplicável", código oficial) enquanto o cadastro de
  produtos não possui dados fiscais;
- CFOP 5102 (venda de mercadoria, operação interna) para UF única SP;
- CRT 1/2 (Simples Nacional) → ICMSSN102 com CSOSN 102; CRT 3 exige a
  estrutura tributária real e é rejeitado até lá.
"""

import random
from decimal import Decimal
from xml.etree import ElementTree as ET

from django.utils import timezone

ZERO = Decimal("0.00")

# Constantes fiscais provisórias — VER NOTA DO MÓDULO (docstring).
NCM_PROVISORIO = "99999999"
CFOP_VENDA_INTERNA = "5102"
CSOSN_SEM_CREDITO = "102"

TPAG_POR_CODIGO = {
    "DINHEIRO": "01",
    "DEBITO": "04",
    "CREDITO": "03",
    "PIX": "17",
    "BOLETO": "15",
    "TRANSFERENCIA": "16",
    "OUTRO": "90",
}

# Código IBGE da unidade federada (tabela oficial do IBGE).
UF_CODIGO = {
    "AC": "12", "AL": "27", "AP": "16", "AM": "13", "BA": "29",
    "CE": "23", "DF": "53", "ES": "32", "GO": "52", "MA": "21",
    "MT": "51", "MS": "50", "MG": "31", "PA": "15", "PB": "25",
    "PR": "41", "PE": "26", "PI": "22", "RJ": "33", "RN": "24",
    "RS": "43", "RO": "11", "RR": "14", "SC": "42", "SP": "35",
    "SE": "28", "TO": "17",
}

NS_NFE = "http://www.portalfiscal.inf.br/nfe"


class FiscalError(Exception):
    """Erro de domínio do módulo fiscal."""


def _sub(parent, tag, texto=None, **attrs):
    elemento = ET.SubElement(parent, tag, attrs)
    if texto is not None:
        elemento.text = str(texto)
    return elemento


def _obrigatorio(valor, campo):
    if valor is None or (isinstance(valor, str) and not valor.strip()):
        raise FiscalError(f"Dado obrigatório ausente: {campo}.")
    return valor


def _decimal_xml(valor: Decimal) -> str:
    """Formata Decimal com 2 casas, sem notação científica."""
    quantizado = Decimal(valor).quantize(Decimal("0.01"))
    return f"{quantizado:f}"


_RNG = random.SystemRandom()


def gerar_cnf(aleatorio=_RNG) -> str:
    """Número aleatório de 8 dígitos que compõe a chave."""
    return f"{aleatorio.randrange(1, 99999999):08d}"


class NFCeBuilder:
    """Monta o XML da NFC-e a partir da venda e do cadastro fiscal."""

    def __init__(self, *, venda, emitente, numero, serie, cnf, dh_emissao=None):
        self.venda = venda
        self.emitente = emitente
        self.numero = _obrigatorio(numero, "nNF")
        self.serie = _obrigatorio(serie, "série")
        self.cnf = cnf or gerar_cnf()
        self.dh_emissao = dh_emissao or timezone.now()
        self.chave = None  # definida pelo serviço antes de montar

    # ------------------------------------------------------------------
    # Grupos
    # ------------------------------------------------------------------

    def _ide(self, raiz):
        emi = self.emitente
        ide = _sub(raiz, "ide")
        uf = _obrigatorio(emi.uf, "UF do emitente")
        if uf not in UF_CODIGO:
            raise FiscalError(f"UF desconhecida: {uf}.")
        _sub(ide, "cUF", UF_CODIGO[uf])
        _sub(ide, "cNF", self.cnf)
        _sub(ide, "natOp", "Venda de mercadoria")
        _sub(ide, "mod", "65")
        _sub(ide, "serie", f"{self.serie:03d}")
        _sub(ide, "nNF", f"{int(self.numero):09d}")
        dh = timezone.localtime(self.dh_emissao)
        _sub(
            ide,
            "dhEmi",
            dh.strftime("%Y-%m-%dT%H:%M:%S") + "-03:00",
        )
        _sub(ide, "tpNF", "1")
        _sub(ide, "idDest", "1")
        _sub(ide, "cMunFG", _obrigatorio(emi.codigo_municipio_ibge, "cMunFG"))
        _sub(ide, "tpImp", "4")
        _sub(ide, "tpEmis", "1")
        _sub(ide, "cDV", str(self.chave.dv))
        _sub(ide, "tpAmb", "2")  # homologação nesta fase
        _sub(ide, "finNFe", "1")
        _sub(ide, "indFinal", "1")
        _sub(ide, "indPres", "1")
        _sub(ide, "procEmi", "0")
        _sub(ide, "verProc", "pdv-nfce-4.00")

    def _emit(self, raiz):
        emi = _obrigatorio(self.emitente, "emitente")
        cnpj = _obrigatorio(emi.cnpj, "CNPJ do emitente")
        if len(cnpj) != 14 or not cnpj.isdigit():
            raise FiscalError("CNPJ do emitente deve ter 14 dígitos.")
        _obrigatorio(emi.ie, "inscrição estadual")
        emit = _sub(raiz, "emit")
        _sub(emit, "CNPJ", cnpj)
        _sub(emit, "xNome", _obrigatorio(emi.razao_social, "razão social"))
        if emi.nome_fantasia:
            _sub(emit, "xFant", emi.nome_fantasia)
        ender = _sub(emit, "enderEmit")
        _sub(ender, "xLgr", _obrigatorio(emi.x_lgr, "logradouro"))
        _sub(ender, "nro", _obrigatorio(emi.nro, "número"))
        if emi.x_cpl:
            _sub(ender, "xCpl", emi.x_cpl)
        _sub(ender, "xBairro", _obrigatorio(emi.x_bairro, "bairro"))
        _sub(ender, "cMun", emi.codigo_municipio_ibge)
        _sub(ender, "xMun", emi.x_municipio)
        _sub(ender, "UF", _obrigatorio(emi.uf, "UF"))
        _sub(ender, "CEP", emi.cep)
        _sub(ender, "cPais", "1058")
        _sub(ender, "xPais", "Brasil")
        if emi.fone:
            _sub(ender, "fone", emi.fone)
        _sub(emit, "IE", emi.ie)
        _sub(emit, "CRT", emi.crt)

    def _det_prod(self, det, item):
        produto = item.produto
        _obrigatorio(produto.nome, f"nome do produto {produto.pk}")
        prod = _sub(det, "prod")
        _sub(prod, "cProd", produto.sku or str(produto.uuid))
        _sub(prod, "cEAN", produto.codigo_barras or "SEM GTIN")
        _sub(prod, "xProd", produto.nome)
        _sub(prod, "NCM", NCM_PROVISORIO)
        _sub(prod, "CFOP", CFOP_VENDA_INTERNA)
        _sub(prod, "uCom", produto.get_unidade_medida_display())
        _sub(prod, "qCom", f"{item.quantidade.quantize(Decimal('0.0001')):f}")
        _sub(
            prod,
            "vUnCom",
            f"{item.preco_unitario.quantize(Decimal('0.0001')):f}",
        )
        _sub(prod, "vProd", _decimal_xml(item.subtotal))
        _sub(prod, "cEANTrib", produto.codigo_barras or "SEM GTIN")
        _sub(prod, "qTrib", f"{item.quantidade.quantize(Decimal('0.0001')):f}")
        _sub(
            prod,
            "vUnTrib",
            f"{item.preco_unitario.quantize(Decimal('0.0001')):f}",
        )
        _sub(prod, "indTot", "1")

    def _icms_por_crt(self, det):
        icms = _sub(_sub(det, "imposto"), "ICMS")
        crt = self.emitente.crt
        if crt in ("1", "2"):
            sn = _sub(icms, "ICMSSN102")
            _sub(sn, "orig", "0")
            _sub(sn, "CSOSN", CSOSN_SEM_CREDITO)
        else:
            raise FiscalError(
                "Regime normal (CRT 3) exige estrutura tributária por "
                "produto ainda não disponível neste módulo."
            )

    def _total(self, raiz, soma_produtos, soma_desconto_itens=ZERO):
        total = _sub(raiz, "total")
        icms_tot = _sub(total, "ICMSTot")
        _sub(icms_tot, "vBC", _decimal_xml(ZERO))
        _sub(icms_tot, "vICMS", _decimal_xml(ZERO))
        _sub(icms_tot, "vICMSDeson", _decimal_xml(ZERO))
        _sub(icms_tot, "vFCP", _decimal_xml(ZERO))
        _sub(icms_tot, "vBCST", _decimal_xml(ZERO))
        _sub(icms_tot, "vST", _decimal_xml(ZERO))
        _sub(icms_tot, "vFCPST", _decimal_xml(ZERO))
        _sub(icms_tot, "vFCPSTRet", _decimal_xml(ZERO))
        _sub(icms_tot, "vProd", _decimal_xml(soma_produtos))
        _sub(icms_tot, "vFrete", _decimal_xml(ZERO))
        _sub(icms_tot, "vSeg", _decimal_xml(ZERO))
        _sub(icms_tot, "vDesc", _decimal_xml(soma_desconto_itens))
        _sub(icms_tot, "vII", _decimal_xml(ZERO))
        _sub(icms_tot, "vIPI", _decimal_xml(ZERO))
        _sub(icms_tot, "vIPIDevol", _decimal_xml(ZERO))
        _sub(icms_tot, "vPIS", _decimal_xml(ZERO))
        _sub(icms_tot, "vCOFINS", _decimal_xml(ZERO))
        _sub(icms_tot, "vOutro", _decimal_xml(ZERO))
        _sub(icms_tot, "vNF", _decimal_xml(self.venda.total))

    def _transp(self, raiz):
        transp = _sub(raiz, "transp")
        _sub(transp, "modFrete", "9")

    def _pag(self, raiz, troco):
        pag = _sub(raiz, "pag")
        _obrigatorio(list(self.venda.pagamentos.all()), "pagamentos da venda")
        for pagamento in self.venda.pagamentos.select_related("forma_pagamento"):
            codigo = pagamento.forma_pagamento.codigo
            if codigo not in TPAG_POR_CODIGO:
                raise FiscalError(
                    f"Código de meio de pagamento não mapeado: {codigo}."
                )
            det_pag = _sub(pag, "detPag")
            _sub(det_pag, "tPag", TPAG_POR_CODIGO[codigo])
            _sub(det_pag, "vPag", _decimal_xml(pagamento.valor))
        if troco > ZERO:
            _sub(pag, "vTroco", _decimal_xml(troco))

    # ------------------------------------------------------------------
    # Montagem
    # ------------------------------------------------------------------

    def montar(self) -> bytes:
        if self.chave is None:
            raise FiscalError(
                "ChaveAcesso não informada ao builder antes da montagem."
            )
        itens = list(self.venda.itens.select_related("produto"))
        if not itens:
            raise FiscalError("Venda sem itens não pode gerar NFC-e.")

        raiz = ET.Element("NFe", {"xmlns": NS_NFE})
        inf = _sub(
            raiz, "infNFe", versao="4.00", Id=f"NFe{self.chave.completa}"
        )
        self._ide(inf)
        self._emit(inf)

        soma_produtos = ZERO
        for ordem, item in enumerate(itens, start=1):
            det = _sub(inf, "det", nItem=str(ordem))
            self._det_prod(det, item)
            self._icms_por_crt(det)
            soma_produtos += item.subtotal

        self._total(inf, soma_produtos)
        self._transp(inf)
        pago = sum((p.valor for p in self.venda.pagamentos.all()), ZERO)
        troco = max(pago - self.venda.total, ZERO)
        self._pag(inf, troco)

        ET.indent(raiz)
        return b'<?xml version="1.0" encoding="UTF-8"?>' + ET.tostring(
            raiz, encoding="utf-8"
        )


def envelopar_lote(xml_nfe: bytes, id_lote: int = 1) -> bytes:
    """Envolve a NFe em enviNFe (lote de 1) para autorização."""
    raiz = ET.Element("enviNFe", {"xmlns": NS_NFE, "versao": "4.00"})
    _sub(raiz, "idLote", str(id_lote))
    _sub(raiz, "indSinc", "1")
    conteudo = ET.fromstring(xml_nfe.decode("utf-8"))
    raiz.append(conteudo)
    return b'<?xml version="1.0" encoding="UTF-8"?>' + ET.tostring(
        raiz, encoding="utf-8"
    )
