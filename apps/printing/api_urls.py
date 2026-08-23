from django.urls import path

from . import api

app_name = "printing_api"

urlpatterns = [
    path("pair/", api.pair, name="pair"),
    path("poll/", api.poll, name="poll"),
    path("jobs/<uuid:uuid>/resultado/", api.resultado, name="resultado"),
]
