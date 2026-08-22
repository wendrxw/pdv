from django.urls import path

from . import views

app_name = "sales"

urlpatterns = [
    # PDV (/app/pdv/)
    path("app/pdv/", views.pdv_home, name="pdv"),
    path("app/pdv/nova-venda/", views.nova_venda, name="nova_venda_rapida"),
    path(
        "app/pdv/caixa/<uuid:caixa_uuid>/nova-venda/",
        views.nova_venda,
        name="nova_venda",
    ),
    path("app/pdv/venda/<uuid:uuid>/", views.venda_tela, name="venda_tela"),
    path(
        "app/pdv/api/produto-busca/",
        views.produto_busca,
        name="produto_busca",
    ),
    # Histórico de vendas (/app/vendas/)
    path("app/vendas/", views.vendas_lista, name="vendas"),
    path("app/vendas/<uuid:uuid>/", views.venda_detalhe, name="venda_detalhe"),
    # Caixas (/app/caixa/)
    path("app/caixa/", views.caixas_lista, name="caixas"),
    path("app/caixa/<uuid:uuid>/", views.caixa_detalhe, name="caixa_detalhe"),
    path(
        "app/caixa/<uuid:uuid>/movimentacao/",
        views.movimentacao_caixa,
        name="movimentacao_caixa",
    ),
]
