"""Views do módulo de etiquetas (seleção → preparação → preview → impressão)."""

import json

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render

from apps.products.models import Produto

from .forms import ConfiguracaoEtiquetaForm
from .models import ConfiguracaoEtiqueta, EtiquetaJob
from .services import (
    LabelsError,
    classificar_status_etiquetas,
    criar_etiqueta_job,
    criar_job_calibracao,
    montar_preview,
    reativar_job,
)


def _tenant_atual(request):
    tenant = request.user.get_tenant()
    if tenant is None:
        messages.info(
            request,
            "Usuário da plataforma não possui tenant para operar etiquetas.",
        )
    return tenant


def _corpo_json(request) -> dict:
    try:
        dados = json.loads(request.body or b"{}")
        return dados if isinstance(dados, dict) else {}
    except (json.JSONDecodeError, UnicodeDecodeError):
        return {}


def _itens_do_request(request) -> list:
    """Itens [{uuid, quantidade}] do corpo JSON ou do form (ordem preservada)."""
    if request.content_type == "application/json":
        return _corpo_json(request).get("produtos") or []
    uuids = request.POST.getlist("uuid")
    quantidades = request.POST.getlist("quantidade")
    return [
        {
            "uuid": uuid,
            "quantidade": quantidades[indice] if indice < len(quantidades) else 1,
        }
        for indice, uuid in enumerate(uuids)
    ]


@login_required
def selecao(request):
    """Preparação: produtos selecionados, quantidades, preview e confirmação."""
    tenant = _tenant_atual(request)
    if tenant is None:
        return redirect("dashboard")
    config = ConfiguracaoEtiqueta.carregar(tenant)
    itens = _itens_do_request(request)
    produtos = []
    if itens:
        uuids = [item.get("uuid") for item in itens]
        mapa = {
            str(produto.uuid): produto
            for produto in Produto.objects.for_tenant(tenant).filter(uuid__in=uuids)
        }
        for item in itens:
            produto = mapa.get(str(item.get("uuid") or ""))
            if produto is not None:
                produtos.append(
                    {
                        "uuid": str(produto.uuid),
                        "nome": produto.nome,
                        "codigo_barras": produto.codigo_barras,
                        "quantidade": int(
                            item.get("quantidade") or config.quantidade_padrao or 1
                        ),
                    }
                )
    return render(
        request,
        "labels/selecao.html",
        {
            "produtos": produtos,
            "config": config,
            "quantidade_padrao": config.quantidade_padrao,
        },
    )


@login_required
def preview(request):
    """JSON do preview: MESMA estrutura enviada à impressora."""
    tenant = _tenant_atual(request)
    if tenant is None:
        return JsonResponse({"erro": "Tenant indisponível."}, status=403)
    itens = _itens_do_request(request)
    try:
        dados = montar_preview(tenant, itens)
    except LabelsError as exc:
        return JsonResponse({"erro": str(exc)}, status=400)
    return JsonResponse(dados)


@login_required
def imprimir(request):
    """Confirma e enfileira o EtiquetaJob (ordem exata do preview)."""
    tenant = _tenant_atual(request)
    if tenant is None:
        return redirect("dashboard")
    itens = _itens_do_request(request)
    try:
        job = criar_etiqueta_job(tenant, itens, usuario=request.user)
    except LabelsError as exc:
        messages.error(request, str(exc))
        return redirect("labels:selecao")
    messages.success(request, "Impressão de etiquetas enviada.")
    return redirect("labels:status", uuid=job.uuid)


@login_required
def calibrar(request):
    """Enfileira um trabalho de calibração (molduras + código de teste)."""
    tenant = _tenant_atual(request)
    if tenant is None:
        return redirect("dashboard")
    job = criar_job_calibracao(tenant, usuario=request.user)
    messages.success(request, "Calibração de etiquetas enviada.")
    return redirect("labels:status", uuid=job.uuid)


@login_required
def status(request, uuid):
    """Tela de acompanhamento do trabalho (polling)."""
    tenant = _tenant_atual(request)
    if tenant is None:
        return redirect("dashboard")
    job = get_object_or_404(
        EtiquetaJob.objects.for_tenant(tenant).select_related("usuario"), uuid=uuid
    )
    return render(
        request,
        "labels/status.html",
        {
            "job": job,
            "estado": classificar_status_etiquetas(job, tenant),
        },
    )


@login_required
def status_json(request, uuid):
    """JSON do estado do trabalho (polling da tela de status)."""
    tenant = request.user.get_tenant()
    if tenant is None:
        return JsonResponse({"job": None, "estado": "SEM_JOB"})
    job = get_object_or_404(EtiquetaJob.objects.for_tenant(tenant), uuid=uuid)
    return JsonResponse(
        {
            "job": {
                "uuid": str(job.uuid),
                "status": job.status,
                "tentativa": job.tentativa,
                "tentativas_maximas": job.tentativas_maximas,
                "erro": job.erro,
                "data_impressao": (
                    job.data_impressao.isoformat() if job.data_impressao else None
                ),
            },
            "estado": classificar_status_etiquetas(job, tenant),
        }
    )


@login_required
def tentar_novamente(request, uuid):
    tenant = _tenant_atual(request)
    if tenant is None:
        return redirect("dashboard")
    job = get_object_or_404(EtiquetaJob.objects.for_tenant(tenant), uuid=uuid)
    try:
        reativar_job(job, usuario=request.user)
        messages.success(request, "Nova tentativa enviada.")
    except LabelsError as exc:
        messages.error(request, str(exc))
    return redirect("labels:status", uuid=job.uuid)


@login_required
def configuracao(request):
    tenant = _tenant_atual(request)
    if tenant is None:
        return redirect("dashboard")
    config = ConfiguracaoEtiqueta.objects.filter(tenant=tenant).first()
    if request.method == "POST":
        config = ConfiguracaoEtiqueta.carregar(tenant)
        form = ConfiguracaoEtiquetaForm(request.POST, instance=config)
        if form.is_valid():
            form.save()
            messages.success(request, "Configuração de etiquetas salva.")
            return redirect("labels:config")
    else:
        form = ConfiguracaoEtiquetaForm(instance=config)
    return render(request, "labels/config.html", {"form": form})
