from django.urls import path

from . import views

app_name = "web"

urlpatterns = [
    path("", views.landing, name="landing"),
    path("contato/", views.contato, name="contato"),
    path("contato/obrigado/", views.contato_sucesso, name="contato_sucesso"),
    path("painel/contatos/", views.contatos, name="contatos"),
    path("painel/contatos/<uuid:uuid>/", views.contato_detalhe, name="contato_detalhe"),
]
