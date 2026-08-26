from django.urls import path

from . import views

app_name = "labels"

urlpatterns = [
    path("", views.selecao, name="selecao"),
    path("preview/", views.preview, name="preview"),
    path("imprimir/", views.imprimir, name="imprimir"),
    path("calibrar/", views.calibrar, name="calibrar"),
    path("config/", views.configuracao, name="config"),
    path("status/<uuid:uuid>/", views.status, name="status"),
    path("status/<uuid:uuid>/json/", views.status_json, name="status_json"),
    path(
        "status/<uuid:uuid>/tentar-novamente/",
        views.tentar_novamente,
        name="tentar_novamente",
    ),
]
