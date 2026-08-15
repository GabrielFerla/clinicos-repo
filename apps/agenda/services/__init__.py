"""Camada de serviços da agenda.

Reúne as operações que escrevem na agenda e que têm regra de negócio própria —
hoje só o agendamento `[S3-7]`. Views, Admin, tasks do Celery e as tools do
chatbot passam por aqui; nenhum deles cria ``Consulta`` por conta própria (ver
``apps.agenda.services.agendamento``).
"""
