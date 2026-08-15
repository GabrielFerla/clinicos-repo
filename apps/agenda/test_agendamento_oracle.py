"""Anti-overbooking contra o Oracle real `[S3-6]` `[S3-8]`.

Auto-pulados fora do ambiente com Oracle (ver ``conftest.py`` da raiz). Rode com
``make test-oracle``.

Por que este arquivo existe, se ``test_agendamento.py`` já cobre o service
------------------------------------------------------------------------
Porque em SQLite duas coisas centrais deste fluxo **não acontecem**:

1. ``select_for_update()`` é no-op — o backend não suporta lock de linha e o
   Django omite a cláusula em silêncio. Só aqui se verifica que o ``SELECT ...
   FOR UPDATE`` de fato roda (e não estoura ``TransactionManagementError`` nem
   ``NotSupportedError``) no banco que vai para produção.
2. A constraint que segura o overbooking é a do schema Oracle, não a do SQLite.
   O ``UNIQUE`` do ``OneToOneField`` de ``Consulta.slot`` precisa recusar o
   segundo ``INSERT`` **lá**, com ``ORA-00001`` — é esse o item de Definition of
   Done da sprint, e é o que sobrevive a um bug futuro no service.

Como em ``apps/prontuario/test_imutabilidade.py``, os testes escrevem na base de
**desenvolvimento**: no Oracle não há banco de teste isolado, porque o usuário
``clinicos`` não tem privilégio para criar outro usuário (ver a docstring de
``apps/chatbot/test_faq_repository.py``). A contrapartida é a transação — tudo
nasce dentro de um ``atomic`` que termina em ``set_rollback(True)``, e nenhuma
linha destes testes sobrevive à execução.
"""

from __future__ import annotations

import datetime as dt
from types import SimpleNamespace

import pytest
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.agenda.models import AgendaSlot, Consulta
from apps.agenda.services.agendamento import AgendamentoService, SlotIndisponivelError
from apps.crm.models import Medico, Paciente

pytestmark = pytest.mark.oracle


@pytest.fixture
def cenario(django_db_blocker):
    """Médico + paciente + slot livre, tudo desfeito no fim (ver docstring)."""
    with django_db_blocker.unblock(), transaction.atomic():
        medico = Medico.objects.create(
            nome="Médico de Teste S3-8", crm_numero="S38TEST", crm_uf="SP"
        )
        paciente = Paciente(nome="Paciente de Teste S3-8", data_nascimento=dt.date(1980, 5, 3))
        paciente.definir_cpf("00000000272")
        paciente.save()
        slot = AgendaSlot.objects.create(
            medico=medico,
            # Data futura: o slot precisa passar pela checagem de "não é
            # passado" do service, e a folga evita depender do fuso do container.
            data=timezone.localdate() + dt.timedelta(days=7),
            hora_inicio=dt.time(9, 0),
            hora_fim=dt.time(9, 30),
        )

        yield SimpleNamespace(medico=medico, paciente=paciente, slot=slot)

        transaction.set_rollback(True)


def test_agendar_funciona_com_lock_de_linha_real(cenario) -> None:
    """O ``SELECT ... FOR UPDATE`` roda no Oracle e o fluxo completa."""
    consulta = AgendamentoService.agendar(
        paciente=cenario.paciente,
        slot_id=cenario.slot.pk,
        origem=Consulta.Origem.CHAT,
    )

    assert consulta.pk is not None
    assert consulta.medico == cenario.medico
    cenario.slot.refresh_from_db()
    assert cenario.slot.status == AgendaSlot.Status.RESERVADO


def test_segunda_consulta_no_mesmo_slot_e_recusada_pelo_oracle(cenario) -> None:
    """[S3-8] O item de Definition of Done: o overbooking morre no banco.

    Sem passar pelo service — é o ``INSERT`` que um script, uma migração de
    dados ou um bug de concorrência produziria.
    """
    AgendamentoService.agendar(
        paciente=cenario.paciente,
        slot_id=cenario.slot.pk,
        origem=Consulta.Origem.RECEPCAO,
    )

    with pytest.raises(IntegrityError), transaction.atomic():
        Consulta.objects.create(
            paciente=cenario.paciente,
            slot=cenario.slot,
            medico=cenario.medico,
        )


def test_corrida_perdida_vira_mensagem_amigavel_no_oracle(cenario) -> None:
    """O ``ORA-00001`` do driver chega ao paciente como frase, não como erro.

    Ocupa o slot pelas costas do service, **sem** mexer no status: é o estado
    que a transação perdedora enxerga entre a checagem e o ``INSERT``.
    """
    Consulta.objects.create(
        paciente=cenario.paciente,
        slot=cenario.slot,
        medico=cenario.medico,
    )

    with pytest.raises(SlotIndisponivelError) as erro:
        AgendamentoService.agendar(
            paciente=cenario.paciente,
            slot_id=cenario.slot.pk,
            origem=Consulta.Origem.CHAT,
        )

    assert "ORA-" not in str(erro.value)
