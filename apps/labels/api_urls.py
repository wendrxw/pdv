from django.urls import path

from . import api

app_name = "labels_api"

urlpatterns = [
    path("poll/", api.poll, name="poll"),
    path("jobs/<uuid:uuid>/resultado/", api.resultado, name="resultado"),
]
