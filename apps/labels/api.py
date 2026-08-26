"""API de etiquetas consumida pelo Local Print Agent.

Reutiliza a autenticação e o throttle da API de comprovantes (mesma
estação, mesmo token). O agente polla separadamente: etiquetas vão para
a impressora de etiquetas (Elgin L42 Pro Full), comprovantes para a
térmica de 58/80mm.
"""

from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from apps.printing.api import _corpo, _estacao_autenticada, _resposta_se_bloqueado

from .models import EtiquetaJob
from .services import (
    LabelsError,
    marcar_falha,
    marcar_impresso,
    obter_proximo_job_etiquetas,
)


@csrf_exempt
@require_POST
def poll(request):
    """Entrega o próximo EtiquetaJob pendente (ou None) para a estação."""
    resposta_bloqueio = _resposta_se_bloqueado(request)
    if resposta_bloqueio:
        return resposta_bloqueio
    estacao = _estacao_autenticada(request)
    if estacao is None:
        return JsonResponse({"erro": "Credencial da estação inválida."}, status=401)
    estacao.ultima_atividade = timezone.now()
    estacao.save(update_fields=["ultima_atividade"])
    disponivel = _corpo(request).get("disponivel", True)
    if not disponivel:
        return JsonResponse({"job": None, "disponivel": False})
    job = obter_proximo_job_etiquetas(estacao)
    if job is None:
        return JsonResponse({"job": None, "disponivel": True})
    return JsonResponse(
        {
            "job": {
                "uuid": str(job.uuid),
                "payload": job.payload,
                "tentativa": job.tentativa,
            },
            "disponivel": True,
        }
    )


@csrf_exempt
@require_POST
def resultado(request, uuid):
    """Reporte do agente: PRINTED (sucesso) ou FAILED (erro → retry)."""
    resposta_bloqueio = _resposta_se_bloqueado(request)
    if resposta_bloqueio:
        return resposta_bloqueio
    estacao = _estacao_autenticada(request)
    if estacao is None:
        return JsonResponse({"erro": "Credencial da estação inválida."}, status=401)
    job = (
        EtiquetaJob.objects.for_tenant(estacao.tenant)
        .filter(uuid=uuid, estacao=estacao)
        .first()
    )
    if job is None:
        return JsonResponse({"erro": "EtiquetaJob não encontrado."}, status=404)
    dados = _corpo(request)
    resultado_agente = str(dados.get("status", "")).upper()
    if resultado_agente == EtiquetaJob.Status.PRINTED:
        try:
            marcar_impresso(job, estacao)
        except LabelsError:
            pass
    elif resultado_agente == "FAILED":
        try:
            marcar_falha(job, estacao, str(dados.get("erro", "")))
        except LabelsError:
            pass
    else:
        return JsonResponse(
            {"erro": "status inválido; use PRINTED ou FAILED."}, status=400
        )
    job.refresh_from_db()
    return JsonResponse({"ok": True, "uuid": str(job.uuid), "status": job.status})
