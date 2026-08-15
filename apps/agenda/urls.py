"""Rotas internas da agenda `[S4-4]`.

Ficam sob o prefixo ``/agenda/`` (ver ``config/urls.py``) e são todas de acesso
autenticado — a tela lista nomes de pacientes.
"""

from django.urls import path

from apps.agenda import views

app_name = "agenda"

urlpatterns = [
    path("", views.consultas_do_dia, name="consultas"),
]
