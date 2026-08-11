"""URL configuration raiz do ClinicOS.

As rotas de domínio são registradas por app, à medida que as sprints avançam.
Hoje: Admin (UI do CRM no MVP1, ADR-0005) e o chatbot público.
"""

from django.contrib import admin
from django.urls import URLPattern, URLResolver, include, path

urlpatterns: list[URLPattern | URLResolver] = [
    path("admin/", admin.site.urls),
    path("chat/", include("apps.chatbot.urls")),
]
