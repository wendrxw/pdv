from django.urls import path

from . import views

app_name = "inventory"

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("entrada/", views.entrada, name="entrada"),
    path("saida/", views.saida, name="saida"),
    path("movimentacoes/", views.movimentacoes, name="movimentacoes"),
    path("saldos/", views.saldos, name="saldos"),
    path(
        "produtos/<uuid:produto_uuid>/",
        views.detalhe_produto,
        name="historico_produto",
    ),
]
