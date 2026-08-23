from django.urls import path

from . import views

app_name = "printing"

urlpatterns = [
    path("config/", views.configuracao, name="config"),
    path("estacoes/", views.estacoes, name="estacoes"),
    path("status/venda/<uuid:uuid>/", views.status_venda, name="status_venda"),
]
