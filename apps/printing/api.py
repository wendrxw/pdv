"""API consumida pelo Local Print Agent (máquina da loja).

O agente fica atrás de NAT/firewall: ele abre a conexão de saída e faz
polling. Autenticação por estação: cabeçalhos ``X-Station-UUID`` e
``X-Station-Token`` (token gerado no pareamento, hash bcrypt no banco).

Estes endpoints NUNCA exigem sessão/CSRF do navegador — são máquina a
máquina — e nunca expõem o dispositivo /dev/usb/lp0.
"""

import json
import time

from django.core.cache import cache
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from .models import PrintJob
from .services import (
    PrintingError,
    autenticar_estacao,
    marcar_falha,
    marcar_impresso,
    obter_proximo_job,
    parear_estacao,
)

ATRASO_FALHA_AUTENTICACAO = 0.5

# Throttle básico por IP (produção multi-processo: usar cache compartilhado).
MAX_FALHAS_AUTENTICACAO = 20
JANELA_FALHAS_SEGUNDOS = 300
_PREFIXO_FALHAS = "print-agent-falhas"


def _corpo(request) -> dict:
    try:
        dados = json.loads(request.body or b"{}")
        return dados if isinstance(dados, dict) else {}
    except json.JSONDecodeError, UnicodeDecodeError:
        return {}


def _ip(request) -> str:
    return request.META.get("REMOTE_ADDR", "?")


def _registrar_falha_autenticacao(request) -> None:
    """Conta falhas por IP para frear força bruta (cache, janela deslizante)."""
    chave = f"{_PREFIXO_FALHAS}:{_ip(request)}"
    try:
        cache.incr(chave)
    except ValueError:
        cache.set(chave, 1, JANELA_FALHAS_SEGUNDOS)


_MENSAGEM_THROTTLE = "Muitas tentativas; tente mais tarde."


def _muitas_falhas(request) -> bool:
    return cache.get(f"{_PREFIXO_FALHAS}:{_ip(request)}", 0) >= MAX_FALHAS_AUTENTICACAO


def _resposta_se_bloqueado(request):
    if _muitas_falhas(request):
        return JsonResponse({"erro": _MENSAGEM_THROTTLE}, status=429)
    return None


def _estacao_autenticada(request):
    estacao = autenticar_estacao(
        request.headers.get("X-Station-UUID", "").strip(),
        request.headers.get("X-Station-Token", "").strip(),
    )
    if estacao is None:
        # Freio simples contra força bruta de token/código.
        time.sleep(ATRASO_FALHA_AUTENTICACAO)
        _registrar_falha_autenticacao(request)
        return None
    return estacao


@csrf_exempt
@require_POST
def pair(request):
    """Pareamento: código curto gerado na tela da loja → credencial."""
    resposta_bloqueio = _resposta_se_bloqueado(request)
    if resposta_bloqueio:
        return resposta_bloqueio
    codigo = str(_corpo(request).get("codigo", "")).strip().upper()
    if not codigo:
        return JsonResponse({"erro": "Informe o código de pareamento."}, status=400)
    try:
        estacao, token = parear_estacao(codigo)
    except PrintingError as exc:
        time.sleep(ATRASO_FALHA_AUTENTICACAO)
        _registrar_falha_autenticacao(request)
        return JsonResponse({"erro": str(exc)}, status=400)
    return JsonResponse(
        {
            "estacao": str(estacao.uuid),
            "token": token,
            "nome": estacao.nome,
            "loja": estacao.tenant.nome,
        }
    )


@csrf_exempt
@require_POST
def poll(request):
    """Entrega o próximo PrintJob pendente (ou None) para a estação.

    O agente pode informar ``disponivel: false`` quando a impressora está
    desligada/desconectada: o trabalho permanece na fila sem ser
    reivindicado (não conta tentativa e não é perdido).
    """
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
    job = obter_proximo_job(estacao)
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
        PrintJob.objects.for_tenant(estacao.tenant)
        .filter(uuid=uuid, estacao=estacao)
        .first()
    )
    if job is None:
        return JsonResponse({"erro": "PrintJob não encontrado."}, status=404)
    dados = _corpo(request)
    resultado_agente = str(dados.get("status", "")).upper()
    if resultado_agente == PrintJob.Status.PRINTED:
        marcar_impresso(job, estacao)
    elif resultado_agente == "FAILED":
        marcar_falha(job, estacao, str(dados.get("erro", "")))
    else:
        return JsonResponse(
            {"erro": "status inválido; use PRINTED ou FAILED."}, status=400
        )
    job.refresh_from_db()
    return JsonResponse({"ok": True, "uuid": str(job.uuid), "status": job.status})
