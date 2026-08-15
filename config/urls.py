"""URL configuration raiz do ClinicOS.

As rotas de domínio são registradas por app, à medida que as sprints avançam.
Hoje: o site público na raiz `[S4-7]`, o chatbot, as telas internas da agenda
`[S4-4]` e o Admin (UI do CRM no MVP1, ADR-0005).

A raiz fica por último de propósito. O `path("")` do `site_publico` só casa com
a string vazia, então não engoliria os prefixos acima de qualquer forma — mas a
ordem deixa legível que o site institucional é o fallback da árvore, e não o
dono dela.
"""

from django.contrib import admin
from django.urls import URLPattern, URLResolver, include, path

urlpatterns: list[URLPattern | URLResolver] = [
    path("admin/", admin.site.urls),
    path("chat/", include("apps.chatbot.urls")),
    path("agenda/", include("apps.agenda.urls")),
    path("", include("apps.site_publico.urls")),
]
