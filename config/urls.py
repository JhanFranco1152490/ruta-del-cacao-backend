"""
URL configuration for config project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/6.1/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""

from django.conf import settings
from django.contrib import admin
from django.urls import include, path

handler404 = "apps.common.views.not_found"
handler500 = "apps.common.views.server_error"

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/auth/", include("apps.accounts.auth.urls")),
    path("api/", include("apps.accounts.roles.urls")),
    path("api/", include("apps.accounts.users.urls")),
    path("api/", include("apps.accounts.access_switch.urls")),
    path("api/", include("apps.producers.urls")),
    path("api/", include("apps.farms.urls")),
    path("api/", include("apps.plots.urls")),
    path("api/", include("apps.crops.urls")),
    path("api/", include("apps.common.urls")),
]

if settings.DEBUG:
    from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

    urlpatterns += [
        path("api/schema", SpectacularAPIView.as_view(), name="schema"),
        path("api/docs", SpectacularSwaggerView.as_view(url_name="schema"), name="docs"),
    ]
