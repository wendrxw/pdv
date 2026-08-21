from django.urls import path

from . import views, views_inventario

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
    path("inventarios/", views_inventario.lista, name="inventario_lista"),
    path("inventarios/novo/", views_inventario.novo, name="inventario_novo"),
    path(
        "inventarios/<uuid:uuid>/",
        views_inventario.detalhe,
        name="inventario_detalhe",
    ),
    path(
        "inventarios/<uuid:uuid>/contagem/",
        views_inventario.contagem,
        name="inventario_contagem",
    ),
    path(
        "inventarios/<uuid:uuid>/divergencias/",
        views_inventario.divergencias,
        name="inventario_divergencias",
    ),
    path(
        "inventarios/<uuid:uuid>/finalizar/",
        views_inventario.finalizar_view,
        name="inventario_finalizar",
    ),
    path(
        "inventarios/<uuid:uuid>/<str:acao>/",
        views_inventario.mudar_status,
        name="inventario_acao",
    ),
]
