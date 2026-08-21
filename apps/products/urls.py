from django.urls import path

from . import views

app_name = "products"

urlpatterns = [
    path("", views.lista, name="lista"),
    path("novo/", views.novo, name="novo"),
    path("<uuid:uuid>/", views.detalhe, name="detalhe"),
    path("<uuid:uuid>/editar/", views.editar, name="editar"),
    path("<uuid:uuid>/alternar-status/", views.alternar_status, name="alternar_status"),
]
