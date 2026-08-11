"""Testes das ferramentas do chatbot.

Rodam em SQLite (CI). A busca vetorial em si depende do Oracle e é coberta em
``test_faq_repository.py``, com ``@pytest.mark.oracle``; aqui o repositório é
substituído por um duplo, para testar o **contrato da tool** — o que ela
devolve ao modelo — sem depender do banco.
"""

from __future__ import annotations

import datetime as dt
import json

import pytest
from django.utils import timezone

from apps.agenda.models import AgendaSlot
from apps.chatbot.models import FaqVector
from apps.chatbot.tools import (
    BuscarFaqTool,
    BuscarSlotsTool,
    ListarEspecialidadesTool,
    ToolError,
    ToolRegistry,
)
from apps.crm.models import Especialidade, Medico, MedicoEspecialidade


@pytest.fixture
def clinica(db):
    """Uma especialidade, um médico e dois slots livres amanhã."""
    esp = Especialidade.objects.create(nome="Retina", slug="retina", descricao="Doenças da retina.")
    medico = Medico.objects.create(nome="Dra. Ana Lima", crm_numero="12345", crm_uf="RS")
    MedicoEspecialidade.objects.create(medico=medico, especialidade=esp, principal=True)
    amanha = timezone.localdate() + dt.timedelta(days=1)
    for hora in (dt.time(9, 0), dt.time(14, 0)):
        AgendaSlot.objects.create(
            medico=medico,
            data=amanha,
            hora_inicio=hora,
            hora_fim=(dt.datetime.combine(amanha, hora) + dt.timedelta(minutes=30)).time(),
        )
    return {"especialidade": esp, "medico": medico, "data": amanha}


class TestListarEspecialidades:
    def test_lista_apenas_ativas(self, clinica):
        Especialidade.objects.create(nome="Desativada", slug="desativada", ativo=False)
        nomes = [e["nome"] for e in ListarEspecialidadesTool().execute()["especialidades"]]
        assert nomes == ["Retina"]


class TestBuscarSlots:
    def test_devolve_slots_livres(self, clinica):
        r = BuscarSlotsTool().execute(especialidade="Retina")
        assert r["encontrada"] is True
        assert [s["hora"] for s in r["slots"]] == ["09:00", "14:00"]
        assert r["slots"][0]["medico"] == "Dra. Ana Lima"

    def test_filtra_por_periodo(self, clinica):
        r = BuscarSlotsTool().execute(especialidade="Retina", periodo_preferido="tarde")
        assert [s["hora"] for s in r["slots"]] == ["14:00"]

    def test_especialidade_inexistente_explica_em_vez_de_devolver_vazio(self, clinica):
        """Vazio silencioso faz o modelo dizer 'não há horários' — o que sugere
        que a clínica atende, mas está lotada. Precisa dizer que não atende."""
        r = BuscarSlotsTool().execute(especialidade="Cardiologia")
        assert r["encontrada"] is False
        assert r["slots"] == []
        assert "Cardiologia" in r["mensagem"]
        assert "Retina" in r["especialidades_atendidas"]

    def test_schema_restringe_ao_vocabulario_do_banco(self, clinica):
        """O `enum` é a defesa contra parâmetro inventado por modelo pequeno."""
        schema = BuscarSlotsTool().input_schema
        assert schema["properties"]["especialidade"]["enum"] == ["Retina"]

    def test_ignora_slot_ocupado(self, clinica):
        AgendaSlot.objects.filter(hora_inicio=dt.time(9, 0)).update(
            status=AgendaSlot.Status.RESERVADO
        )
        r = BuscarSlotsTool().execute(especialidade="Retina")
        assert [s["hora"] for s in r["slots"]] == ["14:00"]

    def test_ignora_slot_no_passado(self, clinica):
        AgendaSlot.objects.update(data=timezone.localdate() - dt.timedelta(days=1))
        assert BuscarSlotsTool().execute(especialidade="Retina")["slots"] == []

    def test_sem_especialidade_levanta_toolerror(self, clinica):
        with pytest.raises(ToolError):
            BuscarSlotsTool().execute(especialidade="")


class _RepositorioFalso:
    def __init__(self, resultados):
        self._resultados = resultados

    def buscar_semantica(self, embedding, top_k=3):
        return self._resultados[:top_k]


class TestBuscarFaq:
    @pytest.fixture
    def faq(self, db):
        return FaqVector.objects.create(
            pergunta="Vocês aceitam convênio?",
            resposta="Sim, atendemos Unimed e Bradesco.",
            categoria="Convênios",
        )

    def test_devolve_faq_relevante(self, faq, monkeypatch):
        monkeypatch.setattr(
            "apps.chatbot.tools.consultas.FAQRepository", _RepositorioFalso([(faq.pk, 0.21)])
        )
        r = BuscarFaqTool().execute(pergunta="aceita Unimed?")
        assert r["encontrou"] is True
        assert r["resultados"][0]["resposta"] == "Sim, atendemos Unimed e Bradesco."

    def test_descarta_resultado_distante(self, faq, monkeypatch):
        """Sem corte de distância, a busca sempre devolve 'o menos distante' —
        e o modelo trata ruído como resposta válida."""
        monkeypatch.setattr(
            "apps.chatbot.tools.consultas.FAQRepository", _RepositorioFalso([(faq.pk, 0.97)])
        )
        assert BuscarFaqTool().execute(pergunta="qual a capital da França?")["encontrou"] is False

    def test_pergunta_vazia_levanta_toolerror(self, faq):
        with pytest.raises(ToolError):
            BuscarFaqTool().execute(pergunta="   ")


class TestToolRegistry:
    """O registry nunca pode propagar exceção: um erro de tool viraria tela de
    erro para o paciente, quando deveria virar uma frase do chatbot."""

    def test_executa_e_serializa(self, clinica):
        registry = ToolRegistry([ListarEspecialidadesTool()])
        payload = json.loads(registry.executar("listar_especialidades_disponiveis", {}))
        assert payload["especialidades"][0]["nome"] == "Retina"

    def test_ferramenta_desconhecida_vira_erro_legivel(self, clinica):
        registry = ToolRegistry([ListarEspecialidadesTool()])
        payload = json.loads(registry.executar("consultar_horoscopo", {}))
        assert "não existe" in payload["erro"]
        assert "listar_especialidades_disponiveis" in payload["disponiveis"]

    def test_argumento_invalido_nao_derruba_o_turno(self, clinica):
        registry = ToolRegistry([BuscarSlotsTool()])
        payload = json.loads(registry.executar("buscar_slots", {"parametro_inventado": 1}))
        assert "erro" in payload

    def test_erro_inesperado_nao_vaza_detalhe_tecnico(self, clinica):
        class Explosiva(ListarEspecialidadesTool):
            def execute(self, **kwargs):
                raise RuntimeError("dsn=oracle://usuario:senha@host/segredo")

        payload = json.loads(
            ToolRegistry([Explosiva()]).executar("listar_especialidades_disponiveis", {})
        )
        assert "senha" not in payload["erro"]
        assert "oracle://" not in payload["erro"]

    def test_schemas_no_formato_do_protocolo(self, clinica):
        schemas = ToolRegistry([ListarEspecialidadesTool(), BuscarSlotsTool()]).schemas()
        assert {s["function"]["name"] for s in schemas} == {
            "listar_especialidades_disponiveis",
            "buscar_slots",
        }
        assert all(s["type"] == "function" for s in schemas)
