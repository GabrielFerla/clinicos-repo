"""Rotas do chat público."""

from django.urls import path

from . import views

app_name = "chatbot"

urlpatterns = [
    path("", views.index, name="index"),
    path("mensagem/", views.mensagem, name="mensagem"),
    path("stream/<uuid:conversa_id>/", views.stream, name="stream"),
]
