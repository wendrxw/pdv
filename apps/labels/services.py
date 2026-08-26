"""Serviços do módulo de etiquetas.

Regra fundamental: o rolo físico tem DUAS etiquetas por fileira. A
lógica gera primeiro uma lista LINEAR de etiquetas e depois agrupa em
pares; quantidade ímpar deixa a última posição vazia. O preview e a
impressão usam exatamente a mesma estrutura (fileiras) — o que aparece
na tela é o que vai para a impressora.
"""

from datetime import timedelta

from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from apps.audit.models import registrar
from apps.printing.models import EstacaoImpressao
from apps.printing.services import LEASE_SEGUNDOS, RETRY_BACKOFF
from apps.products.models import Produto

from .models import ConfiguracaoEtiqueta, EtiquetaJob

ETIQUETAS_POR_FILEIRA = 2
QUANTIDADE_MAXIMA = 100


class LabelsError(Exception):
    """Erro de domínio do módulo de etiquetas."""


def _validar_quantidade(quantidade) -> int:
    try:
        quantidade = int(quantidade)
    except TypeError, ValueError:
        raise LabelsError("Quantidade de etiquetas inválida.") from None
    if quantidade < 1 or quantidade > QUANTIDADE_MAXIMA:
        raise LabelsError(
            f"Quantidade de etiquetas deve ser entre 1 e {QUANTIDADE_MAXIMA}."
        )
    return quantidade


def organizar_etiquetas(selecao) -> list:
    """Lista linear de etiquetas a partir de [{nome, codigo_barras, quantidade}].

    Ex.: Produto A ×3, Produto B ×1 → [A, A, A, B].
    """
    etiquetas = []
    for item in selecao:
        quantidade = _validar_quantidade(item.get("quantidade", 1))
        for _ in range(quantidade):
            etiquetas.append(
                {
                    "nome": str(item.get("nome") or ""),
                    "codigo_barras": str(item.get("codigo_barras") or ""),
                }
            )
    return etiquetas


def agrupar_em_fileiras(etiquetas) -> list:
    """Agrupa a lista linear em fileiras de duas posições (None = vazio)."""
    fileiras = []
    for indice in range(0, len(etiquetas), ETIQUETAS_POR_FILEIRA):
        par = etiquetas[indice : indice + ETIQUETAS_POR_FILEIRA]
        if len(par) == 1:
            par.append(None)
        fileiras.append(par)
    return fileiras


def resumo_impressao(selecao) -> dict:
    etiquetas = organizar_etiquetas(selecao)
    fileiras = agrupar_em_fileiras(etiquetas)
    posicoes_vazias = sum(
        1 for fileira in fileiras for posicao in fileira if posicao is None
    )
    return {
        "produtos": len(selecao),
        "etiquetas": len(etiquetas),
        "fileiras": len(fileiras),
        "posicoes_vazias": posicoes_vazias,
    }


def _produtos_dos_itens(tenant, itens) -> list:
    """Valida [{uuid, quantidade}] contra o tenant e devolve a seleção."""
    uuids = [str(item.get("uuid") or "") for item in itens]
    produtos = {
        str(produto.uuid): produto
        for produto in Produto.objects.for_tenant(tenant).filter(uuid__in=uuids)
    }
    selecao = []
    for item in itens:
        produto = produtos.get(str(item.get("uuid") or ""))
        if produto is None:
            raise LabelsError("Produto não encontrado neste tenant.")
        selecao.append(
            {
                "uuid": str(produto.uuid),
                "nome": produto.nome,
                "codigo_barras": produto.codigo_barras,
                "quantidade": _validar_quantidade(item.get("quantidade", 1)),
            }
        )
    if not selecao:
        raise LabelsError("Selecione ao menos um produto.")
    return selecao


def montar_preview(tenant, itens) -> dict:
    """Estrutura do preview (a MESMA que vai para o payload/impressora)."""
    selecao = _produtos_dos_itens(tenant, itens)
    config = ConfiguracaoEtiqueta.carregar(tenant)
    etiquetas = organizar_etiquetas(selecao)
    fileiras = agrupar_em_fileiras(etiquetas)
    resumo = resumo_impressao(selecao)
    return {
        "impressora": config.nome_impressora,
        "mostrar_texto_codigo": config.mostrar_texto_codigo,
        "fileiras": fileiras,
        "resumo": resumo,
    }


def montar_payload_etiquetas(tenant, itens) -> dict:
    """Payload do EtiquetaJob (dimensões + fileiras + resumo)."""
    selecao = _produtos_dos_itens(tenant, itens)
    config = ConfiguracaoEtiqueta.carregar(tenant)
    etiquetas = organizar_etiquetas(selecao)
    return {
        "versao": 1,
        "tipo": "etiquetas",
        "impressora": config.nome_impressora,
        "dimensoes": config.dimensoes_mm(),
        "mostrar_texto_codigo": config.mostrar_texto_codigo,
        "fileiras": agrupar_em_fileiras(etiquetas),
        "resumo": resumo_impressao(selecao),
    }


def montar_payload_calibracao(tenant) -> dict:
    config = ConfiguracaoEtiqueta.carregar(tenant)
    return {
        "versao": 1,
        "tipo": "calibracao",
        "impressora": config.nome_impressora,
        "dimensoes": config.dimensoes_mm(),
        "mostrar_texto_codigo": True,
        "fileiras": [],
        "resumo": {"produtos": 0, "etiquetas": 1, "fileiras": 1, "posicoes_vazias": 1},
    }


def criar_etiqueta_job(tenant, itens, *, usuario=None) -> EtiquetaJob:
    """Persiste um EtiquetaJob com o payload validado."""
    payload = montar_payload_etiquetas(tenant, itens)
    job = EtiquetaJob.objects.create(tenant=tenant, usuario=usuario, payload=payload)
    registrar(
        "enfileirou etiquetas",
        entidade=job,
        usuario=usuario,
        tenant=tenant,
        descricao=(
            f"EtiquetaJob {job.uuid}: {payload['resumo']['etiquetas']} "
            f"etiqueta(s) em {payload['resumo']['fileiras']} fileira(s)."
        ),
        dados={"uuid": str(job.uuid)},
    )
    return job


def criar_job_calibracao(tenant, *, usuario=None) -> EtiquetaJob:
    job = EtiquetaJob.objects.create(
        tenant=tenant, usuario=usuario, payload=montar_payload_calibracao(tenant)
    )
    registrar(
        "enfileirou calibração de etiquetas",
        entidade=job,
        usuario=usuario,
        tenant=tenant,
        descricao=f"EtiquetaJob de calibração {job.uuid}.",
        dados={"uuid": str(job.uuid)},
    )
    return job


def obter_proximo_job_etiquetas(estacao):
    """Reivindica atômicamente o próximo trabalho de etiquetas (como o
    PrintJob: lease de PROCESSING órfão, backoff de RETRYING, uuid)."""
    agora = timezone.now()
    with transaction.atomic():
        presos = (
            EtiquetaJob.objects.for_tenant(estacao.tenant)
            .select_for_update(skip_locked=True)
            .filter(
                status=EtiquetaJob.Status.PROCESSING,
                estacao=estacao,
                data_processamento__lte=agora - timedelta(seconds=LEASE_SEGUNDOS),
            )
        )
        for job in presos:
            job.status = EtiquetaJob.Status.RETRYING
            job.tentativa += 1
            job.erro = "Impressão interrompida (lease expirado); retry agendado."
            job.proxima_tentativa = _proxima_tentativa_em(job)
            job.save(update_fields=["status", "tentativa", "erro", "proxima_tentativa"])
        candidatos = (
            EtiquetaJob.objects.for_tenant(estacao.tenant)
            .filter(Q(estacao__isnull=True) | Q(estacao=estacao))
            .filter(
                Q(status=EtiquetaJob.Status.PENDING)
                | Q(
                    status=EtiquetaJob.Status.RETRYING,
                    proxima_tentativa__lte=agora,
                )
            )
        )
        job = (
            candidatos.select_for_update(skip_locked=True)
            .order_by("data_criacao")
            .first()
        )
        if job is None:
            return None
        job.status = EtiquetaJob.Status.PROCESSING
        job.estacao = estacao
        job.tentativa += 1
        job.data_processamento = agora
        job.erro = ""
        job.save(
            update_fields=[
                "status",
                "estacao",
                "tentativa",
                "data_processamento",
                "erro",
            ]
        )
    return job


def marcar_impresso(job, estacao) -> EtiquetaJob:
    with transaction.atomic():
        job = EtiquetaJob.objects.select_for_update().get(pk=job.pk)
        if job.estacao_id != estacao.pk:
            raise LabelsError("EtiquetaJob pertence a outra estação.")
        if job.status == EtiquetaJob.Status.PRINTED:
            return job
        job.status = EtiquetaJob.Status.PRINTED
        job.data_impressao = timezone.now()
        job.erro = ""
        job.save(update_fields=["status", "data_impressao", "erro"])
    registrar(
        "imprimiu etiquetas",
        entidade=job,
        usuario=None,
        tenant=job.tenant,
        descricao=f"EtiquetaJob {job.uuid} impresso pela estação {estacao.nome}.",
        dados={"uuid": str(job.uuid)},
    )
    return job


def marcar_falha(job, estacao, erro: str) -> EtiquetaJob:
    with transaction.atomic():
        job = EtiquetaJob.objects.select_for_update().get(pk=job.pk)
        if job.estacao_id != estacao.pk:
            raise LabelsError("EtiquetaJob pertence a outra estação.")
        job.erro = (erro or "Falha desconhecida.")[:2000]
        if job.tentativa >= job.tentativas_maximas:
            job.status = EtiquetaJob.Status.FAILED
            job.proxima_tentativa = None
        else:
            job.status = EtiquetaJob.Status.RETRYING
            job.proxima_tentativa = _proxima_tentativa_em(job)
        job.save(update_fields=["status", "erro", "proxima_tentativa"])
    registrar(
        "falha na impressão de etiquetas",
        entidade=job,
        usuario=None,
        tenant=job.tenant,
        descricao=f"EtiquetaJob {job.uuid} falhou: {job.erro[:200]}",
        dados={"uuid": str(job.uuid), "status": job.status},
    )
    return job


def reativar_job(job, *, usuario=None) -> EtiquetaJob:
    with transaction.atomic():
        job = EtiquetaJob.objects.select_for_update().get(pk=job.pk)
        if job.status == EtiquetaJob.Status.PROCESSING:
            raise LabelsError("O trabalho está sendo impresso agora; aguarde.")
        job.status = EtiquetaJob.Status.PENDING
        job.tentativa = 0
        job.erro = ""
        job.proxima_tentativa = None
        job.save(update_fields=["status", "tentativa", "erro", "proxima_tentativa"])
    return job


def _proxima_tentativa_em(job):
    indice = min(max(job.tentativa - 1, 0), len(RETRY_BACKOFF) - 1)
    return timezone.now() + timedelta(seconds=RETRY_BACKOFF[indice])


def classificar_status_etiquetas(job, tenant) -> str:
    """Estado amigável do painel (mesmos estados dos comprovantes)."""
    if job is None:
        return "SEM_JOB"
    if job.status in (
        EtiquetaJob.Status.PROCESSING,
        EtiquetaJob.Status.PRINTED,
        EtiquetaJob.Status.FAILED,
    ):
        return job.status
    tem_estacao_ativa = (
        EstacaoImpressao.objects.for_tenant(tenant)
        .filter(status=EstacaoImpressao.Status.ATIVA)
        .exists()
    )
    if tem_estacao_ativa:
        return "AGUARDANDO_IMPRESSORA"
    return "AGUARDANDO_AGENTE"
