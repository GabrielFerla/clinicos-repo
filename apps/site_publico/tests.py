"""Testes da landing pública `[S4-7]`.

A página é estática e sem banco, então "renderiza" é quase tudo o que há para
verificar — mas há quatro coisas que quebram em silêncio e custam caro:

* **A raiz responde.** Até esta sprint `/` era 404. É a porta de entrada da
  clínica; um teste que a segure vale o que custa.
* **A página não toca o banco.** É o motivo de o conteúdo morar em constantes:
  a landing continua de pé com o Oracle fora do ar. Uma query que se infiltre
  aqui (um `context_processor`, um `{% templatetag openblock %} for {% templatetag closeblock %}`
  sobre queryset) apaga essa propriedade sem nenhum sintoma visível.
* **O template compõe com o layout.** `home.html` estende
  `components/_layout_publico.html`, que inclui o assistente flutuante e resolve
  `{% templatetag openblock %} url 'site_publico:home' {% templatetag closeblock %}`.
  Um `app_name` esquecido derruba tudo com `NoReverseMatch`.
* **As chapas de impressão não vazam para leitor de tela.** `.cmyk-head` e
  `.cmyk-num` repetem o mesmo texto quatro vezes; três dessas cópias precisam
  ser `aria-hidden`, ou a manchete é lida quatro vezes seguidas.

Rodam em SQLite, como o resto da suíte.
"""

from __future__ import annotations

import pytest
from django.db import connection
from django.test import Client
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from apps.site_publico import content


def test_a_raiz_responde_e_usa_o_template_da_landing(client: Client) -> None:
    resposta = client.get(reverse("site_publico:home"))

    assert resposta.status_code == 200
    usados = {t.name for t in resposta.templates if t.name}
    assert "site_publico/home.html" in usados
    assert "components/_layout_publico.html" in usados
    assert "components/_chat_flutuante.html" in usados


@pytest.mark.django_db
def test_a_landing_nao_toca_o_banco(client: Client) -> None:
    """O conteúdo mora em constantes justamente para isto.

    Se alguém trocar `content.MEDICOS` por `Medico.objects.all()`, a landing
    passa a depender do Oracle — e o sintoma só aparece quando o banco cai.
    """
    with CaptureQueriesContext(connection) as queries:
        client.get(reverse("site_publico:home"))

    assert len(queries) == 0, f"a landing fez {len(queries)} queries; deveria fazer zero"


def test_o_conteudo_das_secoes_chega_na_pagina(client: Client) -> None:
    corpo = client.get(reverse("site_publico:home")).content.decode()

    assert content.CLINICA["nome"] in corpo
    assert content.CLINICA["telefone"] in corpo
    for especialidade in content.ESPECIALIDADES:
        assert especialidade["nome"] in corpo
    for medico in content.MEDICOS:
        assert medico["nome"] in corpo
    for exame in content.EXAMES:
        assert exame["nome"] in corpo


def test_as_ancoras_da_nav_existem_na_pagina(client: Client) -> None:
    """Menu que aponta para âncora inexistente é link morto silencioso."""
    corpo = client.get(reverse("site_publico:home")).content.decode()

    for ancora in ("especialidades", "exames", "corpo-clinico", "agendar"):
        assert f'id="{ancora}"' in corpo, f"a seção #{ancora} sumiu da landing"


def test_as_chapas_repetidas_ficam_fora_do_leitor_de_tela(client: Client) -> None:
    """`.cmyk-head` e `.cmyk-num` repetem o texto uma vez em papel e três em chapa.

    Só a cópia em papel carrega o texto para a tecnologia assistiva; as três
    chapas são `aria-hidden`. Sem isso a manchete do hero é anunciada quatro
    vezes seguidas.
    """
    corpo = client.get(reverse("site_publico:home")).content.decode()

    # Cada `.plate` do documento precisa vir acompanhado de `aria-hidden`.
    assert corpo.count('class="plate plate-c"') == corpo.count(
        'class="plate plate-c" aria-hidden="true"'
    )
    assert 'class="plate plate-m" aria-hidden="true"' in corpo
    assert 'class="plate plate-y" aria-hidden="true"' in corpo


def test_o_assistente_flutuante_aponta_para_o_endpoint_real(client: Client) -> None:
    """O painel usa o chatbot que já existe — não uma cópia local."""
    corpo = client.get(reverse("site_publico:home")).content.decode()

    assert f'data-url-mensagem="{reverse("chatbot:mensagem")}"' in corpo
    assert "chatbot/chat.js" in corpo
