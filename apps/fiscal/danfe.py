"""DANFE NFC-e — dados estruturados + URL do QR Code (versão 2).

O token CSC NUNCA entra na URL pública: apenas seu SHA-1 concatenado
ao hash da chave. A renderização visual fica para a camada de template.
"""

import hashlib
from urllib.parse import quote

from django.conf import settings

from .models import ConfiguracaoFiscal, NFCe
from .xml_builder import FiscalError


def url_qrcode_versao2(
    *,
    chave: str,
    tp_amb: str,
    dh_emissao_epoch: int,
    valor_total,
    digest_hex: str,
    id_csc: str,
    csc_token: str,
) -> str:
    """Monta a URL do QR Code conforme Manual de QR Code versão 2.

    Formato oficial:
    {base}?p={chave}|{versao}|{tpAmb}|{dhEmi epoch}|{vNF}|{digestHex}|{idCSC}|{cscHash}
    """
    if not id_csc or not csc_token:
        raise FiscalError(
            "CSC não configurado — impossível gerar QR Code da NFC-e."
        )
    base = getattr(
        settings,
        "SEFAZ_URL_QRCODE",
        "https://www.sefaz.rs.gov.br/NFCE/NFCE-COM.aspx",
    )
    # Hash oficial: SHA-1 sobre a concatenação com separadores "|".
    csc_hash = hashlib.sha1(
        f"{chave}|2|{tp_amb}|{dh_emissao_epoch}|"
        f"{valor_total:.2f}|{digest_hex}|{id_csc}|{csc_token}".encode()
    ).hexdigest()
    return (
        f"{base}?p={quote(chave)}|2|{tp_amb}|{dh_emissao_epoch}"
        f"|{valor_total:.2f}|{digest_hex}|{quote(id_csc)}|{csc_hash}"
    )


def montar_dados_danfe(*, nfce, emitente) -> dict:
    """Estrutura pronta para o template DANFE simplificada."""
    if nfce.status != NFCe.Status.AUTORIZADA or not nfce.protocolo:
        raise FiscalError("NFC-e não autorizada não possui DANFE.")
    config = ConfiguracaoFiscal.carregar(nfce.tenant)
    itens = [
        {
            "descricao": item.produto.nome,
            "quantidade": item.quantidade,
            "unidade": item.produto.get_unidade_medida_display(),
            "valor_unitario": item.preco_unitario,
            "subtotal": item.subtotal,
        }
        for item in nfce.venda.itens.select_related("produto")
    ]
    pagamentos = [
        {
            "meio": pagamento.forma_pagamento.nome,
            "valor": pagamento.valor,
        }
        for pagamento in nfce.venda.pagamentos.select_related(
            "forma_pagamento"
        )
    ]
    return {
        "emitente": {
            "razao_social": emitente.razao_social,
            "cnpj": emitente.cnpj,
            "ie": emitente.ie,
            "endereco": f"{emitente.x_lgr}, {emitente.nro} - "
            f"{emitente.x_bairro} - {emitente.x_municipio}/{emitente.uf}",
        },
        "numero": nfce.numero,
        "serie": nfce.serie,
        "data_emissao": nfce.data_emissao,
        "protocolo": nfce.protocolo,
        "data_autorizacao": nfce.data_autorizacao,
        "chave": nfce.chave_acesso,
        "itens": itens,
        "pagamentos": pagamentos,
        "total": nfce.valor_total,
        "url_qrcode": nfce.url_qrcode or "",
        "homologacao": config.ambiente
        == ConfiguracaoFiscal.Ambiente.HOMOLOGACAO,
        "consumidor": None,  # venda sem consumidor identificado nesta fase
    }
