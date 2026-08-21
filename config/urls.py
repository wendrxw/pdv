from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", include("apps.web.urls")),
    path("", include("apps.accounts.urls")),
    path("app/produtos/", include("apps.products.urls")),
    path("app/estoque/", include("apps.inventory.urls")),
]
