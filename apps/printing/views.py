"""Views do painel da loja: configuração de impressão e estações."""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import IntegrityError, models
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render

from apps.sales.models import Venda

from .forms import ConfiguracaoImpressaoForm
from .models import ConfiguracaoImpressao, EstacaoImpressao, PrintJob
from .services import (
    classificar_status_impressao,
    gerar_codigo_pareamento,
)


def _tenant_atual(request):
    tenant = request.user.get_tenant()
    if tenant is None:
        messages.info(
            request,
            "Usuário da plataforma não possui tenant para configurar a impressão.",
        )
    return tenant


@login_required
def configuracao(request):
    """Configuração de impressão da loja (largura, automática, cabeçalho)."""
    tenant = _tenant_atual(request)
    if tenant is None:
        return redirect("dashboard")
    config = ConfiguracaoImpressao.objects.filter(tenant=tenant).first()
    if request.method == "POST":
        config = ConfiguracaoImpressao.carregar(tenant)
        form = ConfiguracaoImpressaoForm(request.POST, instance=config, tenant=tenant)
        if form.is_valid():
            form.save()
            messages.success(request, "Configuração de impressão salva.")
            return redirect("printing:config")
    else:
        form = ConfiguracaoImpressaoForm(instance=config, tenant=tenant)
    return render(request, "printing/config.html", {"form": form})


@login_required
def estacoes(request):
    """Estações/terminais e pareamento com o Local Print Agent."""
    tenant = _tenant_atual(request)
    if tenant is None:
        return redirect("dashboard")
    if request.method == "POST":
        acao = request.POST.get("acao", "")
        if acao == "criar":
            nome = request.POST.get("nome", "").strip()
            if not nome:
                messages.error(request, "Informe o nome da estação.")
            else:
                try:
                    estacao = EstacaoImpressao.objects.create(tenant=tenant, nome=nome)
                except IntegrityError:
                    messages.error(request, "Já existe uma estação com esse nome.")
                else:
                    codigo = gerar_codigo_pareamento(estacao)
                    messages.success(
                        request,
                        f"Estação '{nome}' criada. Código de pareamento: {codigo}",
                    )
        elif acao in ("gerar_codigo", "desparear", "inativar", "ativar", "remover"):
            estacao = get_object_or_404(
                EstacaoImpressao.objects.for_tenant(tenant),
                uuid=request.POST.get("estacao", ""),
            )
            if acao == "gerar_codigo":
                codigo = gerar_codigo_pareamento(estacao)
                messages.success(
                    request, f"Novo código para '{estacao.nome}': {codigo}"
                )
            elif acao == "desparear":
                estacao.token_hash = ""
                estacao.codigo_pareamento = ""
                estacao.data_pareamento = None
                estacao.status = EstacaoImpressao.Status.INATIVA
                estacao.save(
                    update_fields=[
                        "token_hash",
                        "codigo_pareamento",
                        "data_pareamento",
                        "status",
                    ]
                )
                messages.success(request, f"Estação '{estacao.nome}' despareada.")
            elif acao == "inativar":
                estacao.status = EstacaoImpressao.Status.INATIVA
                estacao.save(update_fields=["status"])
                messages.success(request, f"Estação '{estacao.nome}' inativada.")
            elif acao == "ativar":
                estacao.status = EstacaoImpressao.Status.ATIVA
                estacao.save(update_fields=["status"])
                messages.success(request, f"Estação '{estacao.nome}' ativada.")
            elif acao == "remover":
                nome = estacao.nome
                estacao.delete()
                messages.success(request, f"Estação '{nome}' removida.")
        return redirect("printing:estacoes")
    lista = EstacaoImpressao.objects.for_tenant(tenant)
    return render(request, "printing/estacoes.html", {"estacoes": lista})


@login_required
def status_venda(request, uuid):
    """JSON com o estado do último PrintJob da venda (polling do PDV).

    Inclui o estado amigável (classificar_status_impressao) e a situação
    das estações, para o operador saber se falta agente/impressora.
    """
    tenant = request.user.get_tenant()
    if tenant is None:
        return JsonResponse({"job": None, "estado": "SEM_JOB", "estacoes": {}})
    venda = get_object_or_404(Venda.objects.for_tenant(tenant), uuid=uuid)
    job = (
        PrintJob.objects.for_tenant(tenant)
        .filter(venda=venda)
        .order_by("-data_criacao")
        .first()
    )
    estacoes_ativas = EstacaoImpressao.objects.for_tenant(tenant).filter(
        status=EstacaoImpressao.Status.ATIVA
    )
    ultima_atividade = estacoes_ativas.aggregate(models.Max("ultima_atividade"))[
        "ultima_atividade__max"
    ]
    dados_job = None
    if job is not None:
        dados_job = {
            "uuid": str(job.uuid),
            "status": job.status,
            "tentativa": job.tentativa,
            "tentativas_maximas": job.tentativas_maximas,
            "erro": job.erro,
            "data_impressao": (
                job.data_impressao.isoformat() if job.data_impressao else None
            ),
        }
    return JsonResponse(
        {
            "job": dados_job,
            "estado": classificar_status_impressao(job, tenant),
            "estacoes": {
                "ativas": estacoes_ativas.count(),
                "ultima_atividade": (
                    ultima_atividade.isoformat() if ultima_atividade else None
                ),
            },
        }
    )
