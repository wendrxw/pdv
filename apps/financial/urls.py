from django.urls import path

from . import views

app_name = "financial"

urlpatterns = [
    path("", views.analise, name="analise"),
    path("entradas/", views.entradas, name="entradas"),
    path("entradas/nova/", views.entrada_nova, name="entrada_nova"),
    path("entradas/<uuid:uuid>/", views.entrada_detalhe, name="entrada_detalhe"),
    path("saidas/", views.saidas, name="saidas"),
    path("saidas/nova/", views.saida_nova, name="saida_nova"),
    path("saidas/<uuid:uuid>/", views.saida_detalhe, name="saida_detalhe"),
    path("receber/", views.receber, name="receber"),
    path("receber/nova/", views.receber_nova, name="receber_nova"),
    path("receber/<uuid:uuid>/", views.receber_detalhe, name="receber_detalhe"),
    path("contas/", views.contas, name="contas"),
]
