from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", include("apps.web.urls")),
    path("", include("apps.accounts.urls")),
    path("app/produtos/", include("apps.products.urls")),
    path("app/estoque/", include("apps.inventory.urls")),
    path("app/financeiro/", include("apps.financial.urls")),
    path("app/impressao/", include("apps.printing.urls")),
    path("api/print-agent/", include("apps.printing.api_urls")),
    path("api/print-agent/etiquetas/", include("apps.labels.api_urls")),
    path("app/etiquetas/", include("apps.labels.urls")),
    path("", include("apps.sales.urls")),
]
