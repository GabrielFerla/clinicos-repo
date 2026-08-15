"""Telas internas da agenda `[S4-4]`.

Hoje há uma: **Consultas do dia**, a grade que a recepção abre de manhã e deixa
aberta. Ela mostra o mesmo dia em duas leituras — a grade por horário, que
responde "o que acontece às 10h e onde ainda há vaga", e a listagem tabular,
que responde "quem marcou o quê, vindo de onde". A recepção usa as duas ao
telefone, e alternar entre telas para ter as duas foi justamente a reclamação
que originou este desenho.

Por que uma view custom e não Django Admin
------------------------------------------
O ADR-0005 elege o Django Admin como UI do CRM no MVP1, e esta tela **diverge**
disso — a divergência está registrada em ``docs/adr/0006-agenda-custom.md``. O
motivo, em uma frase: a grade por horário com os buracos visíveis não é
expressável em ``ModelAdmin``. Um changelist lista o que existe; aqui o que
importa é o que *não* existe — o slot livre entre duas consultas. Os filtros
laterais com contagem por opção têm o mesmo problema.

O ``ConsultaAdmin`` continua existindo e continua sendo onde se **edita**. Esta
tela é de leitura.

Estado na querystring, não em sessão
------------------------------------
``?dia=&status=&origem=&medico=&q=`` — assim um filtro é um link, a recepção
manda a URL do dia para a colega no WhatsApp, e o botão voltar do navegador faz
o que se espera. Nenhum JavaScript participa disso.

Visibilidade
------------
Vale a mesma regra do :class:`~apps.core.admin.RestritoAoMedicoMixin`: ``ADMIN``
e ``RECEPCAO`` veem a clínica inteira, ``MEDICO`` vê só o que passa por ele, e
``MEDICO`` sem ``Medico`` vinculado não vê nada — o default é o fechado. A tela
lista nomes de pacientes, então a regra não é decoração.
"""

from __future__ import annotations

import datetime as dt
from collections import OrderedDict
from typing import Any

from django.contrib.auth.decorators import login_required
from django.db.models import QuerySet
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render
from django.utils import timezone

from apps.agenda.models import AgendaSlot, Consulta
from apps.crm.models import Medico

#: Quantos dias a régua de abas oferece, contando o de hoje.
DIAS_NA_REGUA = 3

#: Rótulos curtos dos dias da semana, para as abas.
_SEMANA_CURTA = ("Seg", "Ter", "Qua", "Qui", "Sex", "Sáb", "Dom")
_SEMANA_LONGA = (
    "Segunda",
    "Terça",
    "Quarta",
    "Quinta",
    "Sexta",
    "Sábado",
    "Domingo",
)
_MESES = (
    "janeiro",
    "fevereiro",
    "março",
    "abril",
    "maio",
    "junho",
    "julho",
    "agosto",
    "setembro",
    "outubro",
    "novembro",
    "dezembro",
)

#: Status → classe de tag do design system. `Cancelada` e `Faltou` não podem
#: usar a mesma tinta: cancelar é rotina administrativa, faltar é perda de
#: receita e é o que a recepção precisa enxergar de longe — daí o magenta,
#: que é o segundo acento e aparece raramente por desenho.
CLASSE_STATUS = {
    Consulta.Status.AGENDADA: "tag tag-neutral",
    Consulta.Status.CONFIRMADA: "tag tag-accent",
    Consulta.Status.REALIZADA: "tag tag-outline",
    Consulta.Status.CANCELADA: "tag tag-outline",
    Consulta.Status.FALTOU: "tag tag-accent-2",
}


def _titulo_do_dia(data: dt.date) -> str:
    """ "Sábado, 15 de agosto" — o cabeçalho da tela."""
    return f"{_SEMANA_LONGA[data.weekday()]}, {data.day} de {_MESES[data.month - 1]}"


def _rotulo_da_aba(data: dt.date, hoje: dt.date) -> str:
    """ "Hoje" para o dia corrente, "Seg 17/08" para os demais."""
    if data == hoje:
        return "Hoje"
    return f"{_SEMANA_CURTA[data.weekday()]} {data:%d/%m}"


def _visiveis_para(usuario: Any, queryset: QuerySet) -> QuerySet:
    """Aplica o recorte por perfil, na mesma ordem do ``RestritoAoMedicoMixin``.

    A ordem importa: o superusuário sai antes de qualquer coisa, inclusive um
    superusuário cujo ``perfil`` seja ``MEDICO`` — sem essa saída antecipada um
    administrador que também atende perderia a tela inteira.
    """
    if usuario.is_superuser or not getattr(usuario, "eh_medico", False):
        return queryset

    medico = Medico.objects.filter(usuario=usuario).first()
    if medico is None:
        # Perfil MEDICO ainda sem vínculo: o default é o fechado. Cair no
        # `else` aqui entregaria a clínica inteira a um cadastro pela metade.
        return queryset.none()
    return queryset.filter(medico=medico)


def _contar(consultas: list[Consulta], campo: str, valor: Any) -> str:
    """Contagem zero-padded ("07") para a coluna de números do filtro."""
    if valor is None:
        return f"{len(consultas):02d}"
    return f"{sum(1 for c in consultas if getattr(c, campo) == valor):02d}"


def _grupo_de_filtro(
    titulo: str,
    campo: str,
    opcoes: list[tuple[Any, str]],
    selecionado: Any,
    do_dia: list[Consulta],
    parametros: dict[str, str],
    campo_modelo: str | None = None,
) -> dict[str, Any]:
    """Um bloco da barra lateral: título + opções com contagem e link.

    ``campo`` é a chave na querystring; ``campo_modelo`` é o atributo em que
    contar, quando os dois diferem. É o caso do médico: o parâmetro é ``medico``
    e carrega uma pk, mas ``Consulta.medico`` é a instância — contar por ele
    compararia objeto com inteiro e devolveria zero em toda linha.
    """
    atributo = campo_modelo or campo
    linhas = []
    for valor, rotulo in [(None, "Tudo"), *opcoes]:
        query = {k: v for k, v in parametros.items() if k != campo and v}
        if valor is not None:
            query[campo] = str(valor)
        linhas.append(
            {
                "rotulo": rotulo,
                "contagem": _contar(do_dia, atributo, valor),
                "ativo": selecionado == valor,
                "query": "?" + "&".join(f"{k}={v}" for k, v in query.items()) if query else "?",
            }
        )
    return {"titulo": titulo, "opcoes": linhas}


@login_required
def consultas_do_dia(request: HttpRequest) -> HttpResponse:
    """Grade e listagem das consultas de um dia, com filtros na querystring."""
    hoje = timezone.localdate()

    try:
        indice_dia = max(0, min(DIAS_NA_REGUA - 1, int(request.GET.get("dia", 0))))
    except (TypeError, ValueError):
        indice_dia = 0
    data = hoje + dt.timedelta(days=indice_dia)

    status = request.GET.get("status") or None
    origem = request.GET.get("origem") or None
    termo = (request.GET.get("q") or "").strip()
    try:
        medico_id = int(request.GET["medico"]) if request.GET.get("medico") else None
    except (TypeError, ValueError):
        medico_id = None

    # `select_related` nos quatro caminhos que o template percorre por linha.
    # Sem ele a grade dispara um SELECT por consulta — e a tela é justamente a
    # que a recepção deixa aberta o dia inteiro.
    base = (
        Consulta.objects.select_related("paciente", "medico", "slot", "slot__medico")
        .filter(slot__data=data)
        .order_by("slot__hora_inicio", "paciente__nome")
    )
    do_dia = list(_visiveis_para(request.user, base))

    # A classe da tag é resolvida aqui, e não no template: o Django não tem
    # filtro de indexação por chave, e criar um `templatetag` só para ler um
    # dicionário de cinco linhas seria mais peça para manter do que este laço.
    for consulta in do_dia:
        consulta.classe_tag = CLASSE_STATUS[consulta.status]

    # Os filtros recortam a listagem, mas as CONTAGENS da barra lateral sempre
    # falam do dia inteiro: um filtro que zerasse os próprios números impediria
    # de ver para onde ir em seguida.
    linhas = do_dia
    if status:
        linhas = [c for c in linhas if c.status == status]
    if origem:
        linhas = [c for c in linhas if c.origem == origem]
    if medico_id is not None:
        linhas = [c for c in linhas if c.medico_id == medico_id]
    if termo:
        alvo = termo.lower()
        linhas = [
            c for c in linhas if alvo in c.paciente.nome.lower() or alvo in c.medico.nome.lower()
        ]

    # A grade sai dos SLOTS do dia, não de uma lista fixa de horários: assim o
    # "livre" é o slot que existe e está vago, e não um horário inventado em que
    # a clínica talvez nem atenda.
    slots = AgendaSlot.objects.filter(data=data).order_by("hora_inicio")
    if medico_id is not None:
        slots = slots.filter(medico_id=medico_id)

    grade: OrderedDict[dt.time, list[Consulta]] = OrderedDict(
        (hora, []) for hora in slots.values_list("hora_inicio", flat=True).distinct()
    )
    for consulta in linhas:
        grade.setdefault(consulta.slot.hora_inicio, []).append(consulta)

    parametros = {
        "dia": str(indice_dia),
        "status": status or "",
        "origem": origem or "",
        "medico": str(medico_id) if medico_id is not None else "",
        "q": termo,
    }

    medicos = list(Medico.objects.filter(ativo=True).order_by("nome"))
    do_chat = sum(1 for c in do_dia if c.origem == Consulta.Origem.CHAT)
    confirmadas = sum(1 for c in do_dia if c.status == Consulta.Status.CONFIRMADA)
    perdidas = sum(
        1 for c in do_dia if c.status in {Consulta.Status.FALTOU, Consulta.Status.CANCELADA}
    )

    contexto = {
        "titulo_dia": _titulo_do_dia(data),
        "abas": [
            {
                "rotulo": _rotulo_da_aba(hoje + dt.timedelta(days=i), hoje),
                "indice": i,
                "ativa": i == indice_dia,
            }
            for i in range(DIAS_NA_REGUA)
        ],
        "resumo": [
            {"valor": f"{len(do_dia):02d}", "rotulo": "Consultas no dia"},
            {"valor": f"{confirmadas:02d}", "rotulo": "Já confirmadas"},
            {"valor": f"{do_chat:02d}", "rotulo": "Vindas do chat"},
            {"valor": f"{perdidas:02d}", "rotulo": "Falta ou cancelamento"},
        ],
        "grade": [
            {"hora": hora, "itens": itens, "vazio": not itens} for hora, itens in grade.items()
        ],
        "consultas": linhas,
        "contagem": f"{len(linhas)} de {len(do_dia)} consultas no dia",
        "chat_titulo": f"{do_chat} de {len(do_dia)} consultas do dia",
        "termo": termo,
        "filtros": [
            _grupo_de_filtro(
                "Status", "status", list(Consulta.Status.choices), status, do_dia, parametros
            ),
            _grupo_de_filtro(
                "Origem", "origem", list(Consulta.Origem.choices), origem, do_dia, parametros
            ),
            _grupo_de_filtro(
                "Médico",
                "medico",
                [(m.pk, m.nome) for m in medicos],
                medico_id,
                do_dia,
                parametros,
                campo_modelo="medico_id",
            ),
        ],
        "parametros": parametros,
    }
    return render(request, "agenda/consultas.html", contexto)
