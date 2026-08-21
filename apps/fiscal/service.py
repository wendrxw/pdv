"""FiscalService — orquestra o ciclo de vida da NFC-e.

Fluxo de status (NFCe.Status):
PENDENTE → GERADA → ASSINADA → TRANSMITINDO → AUTORIZADA
                                        └→ REJEITADA (cStat de erro)

Idempotência (regra central, tasks/TSK_00008.md):
- constraint `unique_nfce_ativa_por_venda` impede duas NFC-e ativas;
- timeout/conexão NÃO rejeita: NFC-e fica TRANSMITINDO e é resolvida
  depois por consulta de chave (nunca nova numeração);
- reserva do número usa select_for_update na ConfiguracaoFiscal para
  evitar buracos/duplicidades sob concorrência.
"""

import base64
import hashlib
import logging
import os

from django.db import transaction
from django.utils import timezone

from .certificate import (
    CertificadoError,
    CertificadoExpirado,
    CertificadoProvider,
)
from .chave import ChaveAcesso
from .danfe import url_qrcode_versao2
from .models import CertificadoDigital, ConfiguracaoFiscal, Emitente, NFCe
from .sefaz.client import SefazClient, SefazError
from .sefaz.parser import RetornoSefaz
from .signing import assinar_nfce
from .xml_builder import FiscalError, NFCeBuilder, envelopar_lote, gerar_cnf

logger = logging.getLogger("pdv.fiscal")

CSTAT_AUTORIZADO = {"100", "150"}
CSTAT_PROCESSAMENTO = {"105"}  # lote em processamento → consultar depois


class FiscalService:
    """Ponto único de entrada das operações fiscais."""

    def __init__(self, client: SefazClient | None = None):
        self._client_injetado = client

    # ------------------------------------------------------------------
    # Infra (tenant explícito em toda a cadeia — docs/general.md §4)
    # ------------------------------------------------------------------

    @staticmethod
    def _emitente(tenant) -> Emitente:
        emitente = Emitente.objects.for_tenant(tenant).first()
        if emitente is None:
            raise FiscalError(
                "Emitente não cadastrado. Configure antes de emitir."
            )
        return emitente

    @staticmethod
    def _provider(tenant) -> CertificadoProvider:
        certificado = CertificadoDigital.pegar_ativo(tenant)
        if certificado is None:
            raise FiscalError("Certificado digital não configurado.")
        senha = os.environ.get("SEFAZ_CERTIFICATE_PASSWORD")
        if not senha:
            raise FiscalError(
                "Senha do certificado ausente em SEFAZ_CERTIFICATE_PASSWORD."
            )
        try:
            return CertificadoProvider.carregar(
                certificado.arquivo.path, senha.encode()
            )
        except CertificadoExpirado:
            raise
        except CertificadoError:
            raise

    def _client(self, tenant) -> SefazClient:
        if self._client_injetado is not None:
            return self._client_injetado
        from django.conf import settings

        from .sefaz.sp import SefazSPClient

        config = ConfiguracaoFiscal.carregar(tenant)
        return SefazSPClient(
            uf=settings.SEFAZ_UF,
            ambiente=config.ambiente or settings.SEFAZ_AMBIENTE,
            provider=self._provider(tenant),
            timeout=settings.SEFAZ_TIMEOUT,
        )

    # ------------------------------------------------------------------
    # Emissão
    # ------------------------------------------------------------------

    def emitir_nfce(self, venda) -> NFCe:
        """Emite NFC-e para a venda FINALIZADA. Idempotente por venda."""
        from apps.sales.models import Venda

        if venda.status != Venda.Status.FINALIZADA:
            raise FiscalError("Somente vendas finalizadas podem gerar NFC-e.")

        existente = (
            NFCe.objects.filter(venda=venda)
            .filter(status__in=NFCe.STATUS_ATIVOS)
            .first()
        )
        if existente is not None:
            return self._resolver_existente(existente)

        autorizada = NFCe.objects.filter(
            venda=venda, status__in=[NFCe.Status.AUTORIZADA]
        ).first()
        if autorizada is not None:
            return autorizada

        rejeitada = NFCe.objects.filter(
            venda=venda, status=NFCe.Status.REJEITADA
        ).first()
        if rejeitada is not None:
            # Reemissão reusa MESMO número/chave (rejeição não consome
            # numeração; o documento é corrigido e retransmitido).
            rejeitada.status = NFCe.Status.PENDENTE
            rejeitada.codigo_rejeicao = ""
            rejeitada.motivo_rejeicao = ""
            rejeitada.save(
                update_fields=["status", "codigo_rejeicao", "motivo_rejeicao"]
            )
            return self._transmitir(rejeitada)

        with transaction.atomic():
            config = ConfiguracaoFiscal.carregar(venda.tenant)
            config = ConfiguracaoFiscal.objects.select_for_update().get(
                pk=config.pk
            )
            numero = config.proximo_numero
            config.proximo_numero += 1
            config.save(update_fields=["proximo_numero"])

            chave = ChaveAcesso(
                cuf="35",
                aamm=timezone.localtime().strftime("%y%m"),
                cnpj=self._emitente(venda.tenant).cnpj,
                serie=config.serie,
                numero=numero,
                cnf=gerar_cnf(),
            )
            nfce = NFCe.objects.create(
                tenant=venda.tenant,
                venda=venda,
                numero=numero,
                serie=config.serie,
                chave_acesso=chave.completa,
                dv=chave.dv,
                valor_total=venda.total,
                status=NFCe.Status.PENDENTE,
            )
        return self._transmitir(nfce)

    # ------------------------------------------------------------------
    # Pipeline interno
    # ------------------------------------------------------------------

    def _transmitir(self, nfce: NFCe) -> NFCe:
        """GERA → ASSINA → TRANSMITE mantendo estados persistidos."""
        venda = nfce.venda
        emitente = self._emitente(venda.tenant)
        chave = ChaveAcesso.da_string(nfce.chave_acesso)

        builder = NFCeBuilder(
            venda=venda,
            emitente=emitente,
            numero=nfce.numero,
            serie=nfce.serie,
            cnf=nfce.chave_acesso[35:43],
        )
        builder.chave = chave

        xml_bruto = builder.montar()
        nfce.xml_enviado = xml_bruto.decode("utf-8")
        nfce.status = NFCe.Status.GERADA
        nfce.save(update_fields=["xml_enviado", "status"])

        provider = self._provider(venda.tenant)
        xml_assinado = assinar_nfce(xml_bruto, provider, nfce.chave_acesso)
        nfce.xml_assinado = xml_assinado.decode("utf-8")
        nfce.status = NFCe.Status.ASSINADA
        nfce.save(update_fields=["xml_assinado", "status"])

        lote = envelopar_lote(xml_assinado)
        nfce.status = NFCe.Status.TRANSMITINDO
        nfce.save(update_fields=["status"])

        try:
            retorno = self._client(venda.tenant).autorizar(lote)
        except SefazError:
            logger.warning(
                "SEFAZ indisponível; NFC-e %s aguarda consulta.",
                nfce.chave_acesso,
            )
            return NFCe.objects.get(pk=nfce.pk)  # permanece TRANSMITINDO

        return self._aplicar_retorno(nfce, retorno)

    def _aplicar_retorno(self, nfce: NFCe, retorno: RetornoSefaz) -> NFCe:
        nfce.codigo_rejeicao = "" if retorno.autorizado else retorno.cstat[:4]
        nfce.motivo_rejeicao = "" if retorno.autorizado else retorno.xmotivo[:255]
        if retorno.autorizado and retorno.cstat in CSTAT_AUTORIZADO:
            nfce.protocolo = retorno.protocolo
            nfce.data_autorizacao = timezone.now()
            nfce.status = NFCe.Status.AUTORIZADA
            nfce.xml_autorizado = retorno.xml[:100000]
        elif retorno.rejeitado and retorno.cstat not in CSTAT_PROCESSAMENTO:
            nfce.status = NFCe.Status.REJEITADA
        else:
            logger.info(
                "NFC-e %s segue em processamento (cStat %s).",
                nfce.chave_acesso,
                retorno.cstat,
            )
        nfce.save()
        if nfce.status == NFCe.Status.AUTORIZADA:
            self._preencher_qrcode(nfce)
        return nfce

    def _resolver_existente(self, nfce: NFCe) -> NFCe:
        """Reemissão idempotente: reaproveita a chave já atribuída."""
        if nfce.status == NFCe.Status.AUTORIZADA:
            return nfce
        if nfce.status in {NFCe.Status.PENDENTE, NFCe.Status.GERADA,
                           NFCe.Status.ASSINADA}:
            return self._transmitir(nfce)
        if nfce.status == NFCe.Status.TRANSMITINDO:
            nfce.tentativas_consulta += 1
            nfce.save(update_fields=["tentativas_consulta"])
            retorno = self._client(nfce.tenant).consultar_protocolo(
                nfce.chave_acesso
            )
            return self._aplicar_retorno(nfce, retorno)
        return nfce  # REJEITADA exige intervenção manual

    # ------------------------------------------------------------------
    # QR Code / DANFE
    # ------------------------------------------------------------------

    def _preencher_qrcode(self, nfce: NFCe) -> None:
        config = ConfiguracaoFiscal.carregar(nfce.tenant)
        digest_hex = ""
        marcador = 'DigestValue>'
        xml = nfce.xml_assinado or ""
        inicio = xml.find(marcador)
        if inicio != -1:
            fim = xml.find("</", inicio + len(marcador))
            bruto_b64 = xml[inicio + len(marcador):fim].strip()
            digest_hex = base64.b64decode(bruto_b64).hex().upper()
        dh_epoch = int(nfce.data_emissao.timestamp())
        tp_amb = "1" if config.ambiente == "PRODUCAO" else "2"
        nfce.url_qrcode = url_qrcode_versao2(
            chave=nfce.chave_acesso,
            tp_amb=tp_amb,
            dh_emissao_epoch=dh_epoch,
            valor_total=float(nfce.valor_total),
            digest_hex=digest_hex,
            id_csc=config.id_csc or "",
            csc_token=config.token_csc or "",
        )
        nfce.save(update_fields=["url_qrcode"])

    # ------------------------------------------------------------------
    # Consulta / eventos
    # ------------------------------------------------------------------

    def consultar_nfce(self, tenant, chave_acesso: str) -> RetornoSefaz:
        return self._client(tenant).consultar_protocolo(chave_acesso)

    def status_sefaz(self, tenant) -> RetornoSefaz:
        return self._client(tenant).status_servico()


def hash_sha1(texto: str) -> str:
    """Utilidade pública para testes do QR Code."""
    return hashlib.sha1(texto.encode()).hexdigest()
