from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render

from .forms import ContatoForm


def landing(request):
    return render(request, "web/landing.html")


def contato(request):
    if request.method == "POST":
        form = ContatoForm(request.POST)
        if form.is_valid():
            lead = form.save(commit=False)
            lead.ip_origem = request.META.get("REMOTE_ADDR") or None
            lead.save()
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
