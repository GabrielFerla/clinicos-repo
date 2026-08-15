"""Rotas do site público.

O `app_name` é obrigatório aqui: o `components/_layout_publico.html` resolve
os links da nav e do rodapé por `{% url 'site_publico:home' %}`, e sem o
namespace o template inteiro estoura em `NoReverseMatch`.

O prefixo real (raiz do site) é decidido em `config/urls.py`.
"""

from django.urls import path

from . import views

app_name = "site_publico"

urlpatterns = [
    path("", views.home, name="home"),
]
