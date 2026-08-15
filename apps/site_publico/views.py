"""Views do site público da clínica.

Por enquanto só a landing (`home`). Ela é deliberadamente **sem banco**: todo
o conteúdo vem das constantes de `apps.site_publico.content` (ver a docstring
de lá para o porquê), então a página responde sem tocar no Oracle e continua
de pé mesmo com o banco fora do ar — o que importa para uma landing que é a
porta de entrada da clínica.

O formulário de captação da seção "Agendar" é **visual**: não tem `action` e
não existe view de POST. Gravar o `Lead` no CRM é a **S4-11**.
"""

from __future__ import annotations

from django.http import HttpRequest, HttpResponse
from django.shortcuts import render
from django.views.decorators.http import require_GET

from apps.site_publico import content


@require_GET
def home(request: HttpRequest) -> HttpResponse:
    """Renderiza a landing pública.

    O contexto carrega, além do conteúdo das seções, as duas chaves que o
    `components/_layout_publico.html` espera de toda página pública:
    ``clinica`` (nav e rodapé) e ``chat_sugestoes`` (o assistente flutuante).
    Esquecer qualquer uma delas não quebra o template — o Django resolve
    variável ausente como string vazia —, ela só some da tela em silêncio.
    """
    contexto = {
        "clinica": content.CLINICA,
        "dateline": content.DATELINE,
        "indice": content.INDICE,
        "colunas": content.COLUNAS,
        "especialidades": content.ESPECIALIDADES,
        "opcoes_especialidade": content.OPCOES_ESPECIALIDADE,
        "exames": content.EXAMES,
        "medicos": content.MEDICOS,
        "citacao": content.CITACAO,
        "chat_sugestoes": content.CHAT_SUGESTOES,
    }
    return render(request, "site_publico/home.html", contexto)
