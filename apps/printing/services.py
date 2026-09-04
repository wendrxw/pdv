"""Serviços do módulo de impressão.

- montagem do snapshot do comprovante (payload do PrintJob);
- ciclo de vida do PrintJob (fila, retry, idempotência);
- pareamento e autenticação das estações.

O servidor NUNCA fala com a impressora: ele apenas gerencia a fila. O
Local Print Agent (máquina da loja) faz polling, imprime em /dev/usb/lp0
e reporta o resultado.
"""

import secrets
from datetime import timedelta
from decimal import Decimal

from django.contrib.auth.hashers import check_password, make_password
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from apps.audit.models import registrar
from apps.financial.models import FormaPagamento

from .models import ConfiguracaoImpressao, EstacaoImpressao, PrintJob

ZERO = Decimal("0.00")

# Backoff entre tentativas (segundos), indexado por tentativa - 1.
RETRY_BACKOFF = [5, 15, 60, 300, 900]

# PROCESSING parado há mais tempo que isso volta para a fila (retry).
LEASE_SEGUNDOS = 300

PAREAMENTO_ALFABETO = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
PAREAMENTO_TAMANHO = 6


class PrintingError(Exception):
    """Erro de domínio do módulo de impressão."""


def _emitente(tenant):
    try:
        return tenant.emitente
    except AttributeError:
        return None


def montar_dados_comprovante(venda, config) -> dict:
    """Snapshot serializável da venda para o comprovante.

    Tudo em strings (Decimal nunca vira float no JSON). O cabeçalho cai
    para os dados do Emitente fiscal ou do tenant quando a configuração
    de impressão não preencher.
    """
    tenant = venda.tenant
    emitente = _emitente(tenant)
    nome = (
        config.nome_loja
        or getattr(emitente, "nome_fantasia", "")
        or getattr(emitente, "razao_social", "")
        or tenant.nome
    )
    cnpj = config.cnpj or getattr(emitente, "cnpj", "")
    endereco = config.endereco
    if not endereco and emitente is not None:
        partes = [
            emitente.x_lgr,
            emitente.nro,
            emitente.x_bairro,
            f"{emitente.x_municipio}-{emitente.uf}",
        ]
        endereco = ", ".join(p for p in partes if p)
    telefone = config.telefone or getattr(emitente, "fone", "")

    itens = [
        {
            "nome": item.produto.nome,
            "quantidade": str(item.quantidade),
            "preco_unitario": str(item.preco_unitario),
            "subtotal": str(item.subtotal),
        }
        for item in venda.itens.select_related("produto")
    ]
    pagamentos_qs = list(venda.pagamentos.select_related("forma_pagamento"))
    pagamentos = [
        {"forma": p.forma_pagamento.nome, "valor": str(p.valor)} for p in pagamentos_qs
    ]
    valor_recebido = sum(
        (
            p.valor
            for p in pagamentos_qs
            if p.forma_pagamento.codigo == FormaPagamento.Codigo.DINHEIRO
        ),
        ZERO,
    )
    troco = max(valor_recebido - venda.total, ZERO)
    data_venda = venda.data_finalizacao or venda.data_abertura
    return {
        "versao": 1,
        "largura_mm": config.largura,
        "impressora": config.impressora_fiscal or "",
        "cabecalho": {
            "nome": nome,
            "cnpj": cnpj,
            "endereco": endereco,
            "telefone": telefone,
        },
        "venda": {
            "numero": venda.numero,
            "data": timezone.localtime(data_venda).isoformat(timespec="seconds"),
        },
        "itens": itens,
        "totais": {
            "subtotal": str(venda.subtotal),
            "desconto": str(venda.desconto),
            "total": str(venda.total),
        },
        "pagamentos": pagamentos,
        "valor_recebido": str(valor_recebido),
        "troco": str(troco),
        "mensagem_final": config.mensagem_final or "",
    }


def criar_print_job(venda, *, estacao=None, usuario=None) -> PrintJob:
    """Enfileira um PrintJob para a venda (idempotente por venda).

    Se já existir trabalho ativo para a venda, retorna o existente em vez
    de duplicar. Venda finalizada (persistida) é pré-requisito.
    """
    from apps.sales.models import Venda

    if venda.status != Venda.Status.FINALIZADA:
        raise PrintingError(
            "Somente vendas finalizadas geram comprovante de impressão."
        )
    config = ConfiguracaoImpressao.carregar(venda.tenant)
    ativos = (
        PrintJob.Status.PENDING,
        PrintJob.Status.RETRYING,
        PrintJob.Status.PROCESSING,
    )
    existente = (
        PrintJob.objects.for_tenant(venda.tenant)
        .filter(venda=venda, status__in=ativos)
        .first()
    )
    if existente is not None:
        return existente
    job = PrintJob.objects.create(
        tenant=venda.tenant,
        venda=venda,
        estacao=estacao if estacao is not None else config.estacao_padrao,
        payload=montar_dados_comprovante(venda, config),
        tentativas_maximas=config.tentativas_maximas,
    )
    registrar(
        "enfileirou impressão",
        entidade=venda,
        usuario=usuario,
        tenant=venda.tenant,
        descricao=f"PrintJob {job.uuid} para a venda {venda.numero}.",
        dados={"uuid": str(job.uuid), "venda": str(venda.uuid)},
    )
    return job


def classificar_status_impressao(job, tenant) -> str:
    """Estado amigável do painel do PDV para o PrintJob (ou sua ausência).

    - SEM_JOB: nenhum job para a venda (botão de imprimir);
    - PROCESSING: agente reivindicou e está imprimindo;
    - PRINTED / FAILED: estados finais;
    - AGUARDANDO_IMPRESSORA: job na fila/retry e existe estação ativa
      (o agente pega em segundos);
    - AGUARDANDO_AGENTE: job na fila/retry mas NENHUMA estação ativa —
      sem agente a loja nunca imprime (diagnóstico exibido no painel).
    """
    if job is None:
        return "SEM_JOB"
    if job.status in (
        PrintJob.Status.PROCESSING,
        PrintJob.Status.PRINTED,
        PrintJob.Status.FAILED,
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


def obter_proximo_job(estacao) -> PrintJob | None:
    """Reivindica atômicamente o próximo trabalho da estação.

    - devolve apenas PENDING ou RETRYING cujo backoff já venceu;
    - recoloca na fila PROCESSING parado além do lease (impressora pode
      ter morrido no meio — o uuid garante a idempotência no agente);
    - incrementa a tentativa e marca PROCESSING sob lock.
    """
    agora = timezone.now()
    with transaction.atomic():
        presos = (
            PrintJob.objects.for_tenant(estacao.tenant)
            .select_for_update(skip_locked=True)
            .filter(
                status=PrintJob.Status.PROCESSING,
                estacao=estacao,
                data_processamento__lte=agora - timedelta(seconds=LEASE_SEGUNDOS),
            )
        )
        for job in presos:
            job.status = PrintJob.Status.RETRYING
            job.tentativa += 1
            job.erro = "Impressão interrompida (lease expirado); retry agendado."
            job.proxima_tentativa = _proxima_tentativa_em(job)
            job.save(
                update_fields=[
                    "status",
                    "tentativa",
                    "erro",
                    "proxima_tentativa",
                ]
            )
        candidatos = (
            PrintJob.objects.for_tenant(estacao.tenant)
            .filter(Q(estacao__isnull=True) | Q(estacao=estacao))
            .filter(
                Q(status=PrintJob.Status.PENDING)
                | Q(status=PrintJob.Status.RETRYING, proxima_tentativa__lte=agora)
            )
        )
        job = (
            candidatos.select_for_update(skip_locked=True)
            .order_by("data_criacao")
            .first()
        )
        if job is None:
            return None
        job.status = PrintJob.Status.PROCESSING
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


def marcar_impresso(job, estacao) -> PrintJob:
    """Registra sucesso (idempotente: PRINTED repetido é aceito)."""
    with transaction.atomic():
        job = PrintJob.objects.select_for_update().get(pk=job.pk)
        if job.estacao_id != estacao.pk:
            raise PrintingError("PrintJob pertence a outra estação.")
        if job.status == PrintJob.Status.PRINTED:
            return job
        job.status = PrintJob.Status.PRINTED
        job.data_impressao = timezone.now()
        job.erro = ""
        job.save(update_fields=["status", "data_impressao", "erro"])
    registrar(
        "imprimiu comprovante",
        entidade=job,
        usuario=None,
        tenant=job.tenant,
        descricao=f"PrintJob {job.uuid} impresso pela estação {estacao.nome}.",
        dados={"uuid": str(job.uuid)},
    )
    return job


def marcar_falha(job, estacao, erro: str) -> PrintJob:
    """Registra falha com retry (backoff) ou FAILED quando esgotado.

    Nunca reimprime automaticamente sem idempotência: a térmica pode ter
    recebido parte do trabalho antes da falha; o uuid protege o agente.
    """
    with transaction.atomic():
        job = PrintJob.objects.select_for_update().get(pk=job.pk)
        if job.estacao_id != estacao.pk:
            raise PrintingError("PrintJob pertence a outra estação.")
        job.erro = (erro or "Falha desconhecida na impressão.")[:2000]
        if job.tentativa >= job.tentativas_maximas:
            job.status = PrintJob.Status.FAILED
            job.proxima_tentativa = None
        else:
            job.status = PrintJob.Status.RETRYING
            job.proxima_tentativa = _proxima_tentativa_em(job)
        job.save(update_fields=["status", "erro", "proxima_tentativa"])
    registrar(
        "falha na impressão",
        entidade=job,
        usuario=None,
        tenant=job.tenant,
        descricao=f"PrintJob {job.uuid} falhou: {job.erro[:200]}",
        dados={"uuid": str(job.uuid), "status": job.status},
    )
    return job


def reativar_print_job(job, *, usuario=None) -> PrintJob:
    """'Tentar novamente' manual: volta o job para a fila do zero."""
    with transaction.atomic():
        job = PrintJob.objects.select_for_update().get(pk=job.pk)
        if job.status == PrintJob.Status.PRINTED:
            raise PrintingError("Comprovante já impresso; use 'imprimir novamente'.")
        if job.status == PrintJob.Status.PROCESSING:
            raise PrintingError("O comprovante está sendo impresso agora; aguarde.")
        job.status = PrintJob.Status.PENDING
        job.tentativa = 0
        job.erro = ""
        job.proxima_tentativa = None
        job.save(update_fields=["status", "tentativa", "erro", "proxima_tentativa"])
    return job


def _proxima_tentativa_em(job):
    indice = min(max(job.tentativa - 1, 0), len(RETRY_BACKOFF) - 1)
    return timezone.now() + timedelta(seconds=RETRY_BACKOFF[indice])


def gerar_codigo_pareamento(estacao) -> str:
    """Gera um código curto de uso único (A-Z2-9, sem 0/O/1/I)."""
    for _ in range(10):
        codigo = "".join(
            secrets.choice(PAREAMENTO_ALFABETO) for _ in range(PAREAMENTO_TAMANHO)
        )
        if not EstacaoImpressao.objects.filter(codigo_pareamento=codigo).exists():
            break
    estacao.codigo_pareamento = codigo
    estacao.save(update_fields=["codigo_pareamento"])
    return codigo


def parear_estacao(codigo: str):
    """Consome o código de pareamento e emite a credencial da estação.

    Retorna (estacao, token). O token trafega em claro uma única vez e é
    armazenado apenas como hash bcrypt no servidor.
    """
    with transaction.atomic():
        estacao = (
            EstacaoImpressao.objects.filter(codigo_pareamento=codigo)
            .select_for_update()
            .first()
        )
        if estacao is None:
            raise PrintingError("Código de pareamento inválido ou já utilizado.")
        token = secrets.token_urlsafe(32)
        estacao.token_hash = make_password(token)
        estacao.status = EstacaoImpressao.Status.ATIVA
        estacao.codigo_pareamento = ""
        estacao.data_pareamento = timezone.now()
        estacao.save(
            update_fields=[
                "token_hash",
                "status",
                "codigo_pareamento",
                "data_pareamento",
            ]
        )
    registrar(
        "pareou estação de impressão",
        entidade=estacao,
        usuario=None,
        tenant=estacao.tenant,
        descricao=f"Estação '{estacao.nome}' pareada com o agente local.",
        dados={"uuid": str(estacao.uuid)},
    )
    return estacao, token


def autenticar_estacao(uuid_estacao: str, token: str):
    """Valida a credencial da estação (comparação bcrypt, tempo constante)."""
    try:
        estacao = EstacaoImpressao.objects.get(uuid=uuid_estacao)
    except (EstacaoImpressao.DoesNotExist, ValidationError, ValueError):
        return None
    if estacao.status != EstacaoImpressao.Status.ATIVA:
        return None
    if not estacao.token_hash or not check_password(token, estacao.token_hash):
        return None
    return estacao
