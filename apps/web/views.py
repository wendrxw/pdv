"""Views do site público (landing/contato) e do painel da plataforma.

A tela de contato apenas coleta o lead (nunca cria tenant/cliente). A
leitura e a gestão desses contatos ficam no painel da equipe da
plataforma (usuários ``is_staff``).
"""

import logging

from django.conf import settings
from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.decorators import login_required
from django.core.mail import send_mail
from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404, redirect, render

from apps.clients.models import LeadContato
from apps.clients.services import ClientServiceError, converter_lead

from .forms import ContatoForm

logger = logging.getLogger(__name__)

ITENS_POR_PAGINA = 20


def landing(request):
    return render(request, "web/landing.html")


def _notificar_contato(lead: LeadContato) -> None:
    """Envia um e-mail de aviso para a equipe da plataforma (se configurado).

    O envio é melhor-esforço: qualquer falha é registrada no log e nunca
    interrompe o salvamento do lead.
    """
    destinatario = getattr(settings, "PDV_CONTATO_EMAIL", "")
    if not destinatario:
        return
    try:
        send_mail(
            subject=f"[PDV] Novo contato: {lead.nome}",
            message=(
                f"Nome: {lead.nome}\n"
                f"E-mail: {lead.email}\n"
                f"Telefone: {lead.telefone}\n"
                f"Empresa: {lead.empresa or '—'}\n\n"
                f"Mensagem:\n{lead.mensagem}\n"
            ),
            from_email=None,
            recipient_list=[destinatario],
            fail_silently=True,
        )
    except Exception as exc:  # noqa: BLE001 - notificação nunca bloqueia
        logger.warning("Falha ao notificar contato por e-mail: %s", exc)


def contato(request):
    if request.method == "POST":
        form = ContatoForm(request.POST)
        if form.is_valid():
            lead = form.save(commit=False)
            lead.ip_origem = request.META.get("REMOTE_ADDR") or None
            lead.save()
            _notificar_contato(lead)
            return redirect("web:contato_sucesso")
    else:
        form = ContatoForm()
    return render(request, "web/contato.html", {"form": form})


def contato_sucesso(request):
    return render(request, "web/contato_sucesso.html")


@login_required
def dashboard(request):
    tenant = request.user.get_tenant()
    contexto = {
        "tenant": tenant,
        "is_plataforma": request.user.is_plataforma,
    }
    return render(request, "web/dashboard.html", contexto)


@staff_member_required
def contatos(request):
    """Lista os pedidos de contato (leads) para a equipe da plataforma."""
    leads = LeadContato.objects.select_related("cliente_convertido").all()
    status = request.GET.get("status", "")
    busca = request.GET.get("q", "")
    if status:
        leads = leads.filter(status=status)
    if busca:
        from django.db.models import Q

        leads = leads.filter(
            Q(nome__icontains=busca)
            | Q(email__icontains=busca)
            | Q(empresa__icontains=busca)
            | Q(telefone__icontains=busca)
        )
    paginador = Paginator(leads, ITENS_POR_PAGINA)
    pagina = paginador.get_page(request.GET.get("page"))
    return render(
        request,
        "web/contatos.html",
        {
            "pagina": pagina,
            "status": status,
            "busca": busca,
            "statuses": LeadContato.Status.choices,
        },
    )


@staff_member_required
def contato_detalhe(request, uuid):
    """Detalhe completo de um contato + ações de gestão do funil."""
    lead = get_object_or_404(
        LeadContato.objects.select_related("cliente_convertido"), uuid=uuid
    )
    if request.method == "POST":
        acao = request.POST.get("acao", "")
        try:
            if acao == "converter":
                converter_lead(lead, usuario=request.user)
                messages.success(request, "Lead convertido em cliente da plataforma.")
            elif acao == "em_atendimento":
                lead.status = LeadContato.Status.EM_ATENDIMENTO
                lead.save(update_fields=["status"])
                messages.success(request, "Lead marcado como 'Em atendimento'.")
            elif acao == "descartar":
                lead.status = LeadContato.Status.DESCARTADO
                lead.save(update_fields=["status"])
                messages.success(request, "Lead descartado.")
            else:
                messages.error(request, "Ação desconhecida.")
        except ClientServiceError as exc:
            messages.error(request, str(exc))
        return redirect("web:contato_detalhe", uuid=lead.uuid)
    return render(request, "web/contato_detalhe.html", {"lead": lead})
