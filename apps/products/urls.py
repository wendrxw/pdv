from django.urls import path

from . import views

app_name = "products"

urlpatterns = [
    path("", views.lista, name="lista"),
    path("novo/", views.novo, name="novo"),
    path("gerar-codigo-barras/", views.gerar_codigo_barras, name="gerar_codigo_barras"),
    path("<uuid:uuid>/", views.detalhe, name="detalhe"),
    path("<uuid:uuid>/editar/", views.editar, name="editar"),
    path(
        "<uuid:uuid>/codigo-barras.svg",
        views.codigo_barras_svg,
        name="codigo_barras_svg",
    ),
    path("<uuid:uuid>/alternar-status/", views.alternar_status, name="alternar_status"),
]
