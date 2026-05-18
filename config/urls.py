"""
URL configuration for best_seller project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.2/topics/http/urls/
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

from django.contrib import admin
from django.http import HttpResponse
from django.urls import path
from rest_framework import permissions
from drf_yasg.views import get_schema_view
from drf_yasg import openapi
from django.urls import include

def health_check(request):
    return HttpResponse("OK")

urlpatterns = [
    path("admin/", admin.site.urls),
    path("health/", health_check),
]
schema_view = get_schema_view(
    openapi.Info(
        title="InvenIQ Backend API",
        default_version='v1',
        description="A Django project built with modern best practices",
    ),
    public=True,
    permission_classes=(permissions.AllowAny,),
)

urlpatterns += [
    path("api/auth/", include("dj_rest_auth.urls")),
    path("api/swagger<format>/", schema_view.without_ui(cache_timeout=0), name='schema-json'),
    path("api/swagger/", schema_view.with_ui('swagger', cache_timeout=0), name='schema-swagger-ui'),
    path("api/redoc/", schema_view.with_ui('redoc', cache_timeout=0), name='schema-redoc'),
]
