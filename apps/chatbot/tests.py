"""Testes dos models do chatbot (Bloco 1A do ``docs/CHAT_MVP.md``).

Dois pontos merecem teste de verdade:

* ``FaqVector.precisa_reindexar`` — é o que torna a reindexação idempotente
  `[S5-16]` e o que evita o pior modo de falha da busca vetorial: indexar com
  um modelo e consultar com outro devolve lixo **sem erro nenhum**.
* ``UK_INTERACAO_SEQ`` — dois turnos na mesma posição embaralhariam o
  histórico que é reenviado ao modelo a cada turno.

A coluna ``EMBEDDING`` não existe em SQLite (entra por migration guardada por
vendor no Bloco 1B), então nada aqui a toca — de propósito.
"""

from __future__ import annotations

import uuid

import pytest
from django.contrib.admin.sites import AdminSite
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.chatbot.admin import InteracaoChatAdmin
from apps.chatbot.models import FaqVector, InteracaoChat

pytestmark = pytest.mark.django_db

MODELO = "all-minilm"
DIM = 384


@pytest.fixture
def faq() -> FaqVector:
    return FaqVector.objects.create(
        pergunta="A clínica atende convênio?",
        resposta="Atendemos os principais convênios. Consulte a recepção.",
        categoria="convenios",
    )


# ---------------------------------------------------------------------------
# FaqVector
# ---------------------------------------------------------------------------


def test_faq_str_usa_a_pergunta(faq: FaqVector) -> None:
    assert str(faq) == "A clínica atende convênio?"


def test_faq_nasce_ativa_e_sem_embedding(faq: FaqVector) -> None:
    assert faq.ativo is True
    assert faq.embedding_gerado_em is None
    assert faq.embedding_modelo == ""
    assert faq.embedding_dim is None
    assert faq.conteudo_hash == ""


def test_hash_do_conteudo_e_deterministico_e_sensivel_ao_texto(faq: FaqVector) -> None:
    digest = faq.calcular_conteudo_hash()
    assert len(digest) == 64
    assert digest == faq.calcular_conteudo_hash()

    faq.resposta = "Atendemos apenas particular."
    assert faq.calcular_conteudo_hash() != digest


def test_hash_separa_pergunta_de_resposta() -> None:
    """Sem separador, ('ab', 'c') e ('a', 'bc') colidiriam."""
    um = FaqVector(pergunta="ab", resposta="c")
    outro = FaqVector(pergunta="a", resposta="bc")
    assert um.calcular_conteudo_hash() != outro.calcular_conteudo_hash()


def test_faq_nunca_indexada_precisa_reindexar(faq: FaqVector) -> None:
    assert faq.precisa_reindexar(MODELO, DIM) is True


def _marcar_indexada(faq: FaqVector, modelo: str = MODELO, dim: int = DIM) -> None:
    faq.embedding_gerado_em = timezone.now()
    faq.embedding_modelo = modelo
    faq.embedding_dim = dim
    faq.conteudo_hash = faq.calcular_conteudo_hash()
    faq.save()


def test_faq_indexada_e_intocada_nao_precisa_reindexar(faq: FaqVector) -> None:
    _marcar_indexada(faq)
    assert faq.precisa_reindexar(MODELO, DIM) is False


def test_texto_alterado_dispara_reindexacao(faq: FaqVector) -> None:
    _marcar_indexada(faq)
    faq.resposta = "Atendemos Unimed, Bradesco Saúde e Amil."
    assert faq.precisa_reindexar(MODELO, DIM) is True


def test_troca_de_modelo_ou_dimensao_dispara_reindexacao(faq: FaqVector) -> None:
    """A invariante que falha em silêncio: vetor de outro modelo ranqueia lixo."""
    _marcar_indexada(faq)
    assert faq.precisa_reindexar("outro-modelo", DIM) is True
    assert faq.precisa_reindexar(MODELO, 1024) is True


# ---------------------------------------------------------------------------
# InteracaoChat
# ---------------------------------------------------------------------------


def test_interacao_tem_pk_uuid_e_defaults_vazios() -> None:
    interacao = InteracaoChat.objects.create(
        conversa_id=uuid.uuid4(), pergunta="Tem horário com oftalmologista?"
    )

    assert isinstance(interacao.pk, uuid.UUID)
    assert interacao.sequencia == 1
    assert interacao.resposta == ""
    assert interacao.tools_usadas == []
    assert interacao.faq_ids == []
    assert interacao.alucinacao_detectada is False
    assert interacao.erro == ""


def test_interacao_str_identifica_conversa_e_turno() -> None:
    conversa = uuid.uuid4()
    interacao = InteracaoChat.objects.create(conversa_id=conversa, sequencia=3, pergunta="oi")
    assert str(interacao) == f"{conversa} #3"


def test_json_fields_persistem_listas() -> None:
    interacao = InteracaoChat.objects.create(
        conversa_id=uuid.uuid4(),
        pergunta="A clínica atende convênio?",
        tools_usadas=["buscar_faq"],
        faq_ids=[7, 12],
    )
    interacao.refresh_from_db()

    assert interacao.tools_usadas == ["buscar_faq"]
    assert interacao.faq_ids == [7, 12]


def test_sequencia_nao_repete_na_mesma_conversa() -> None:
    conversa = uuid.uuid4()
    InteracaoChat.objects.create(conversa_id=conversa, sequencia=1, pergunta="oi")
    with pytest.raises(IntegrityError), transaction.atomic():
        InteracaoChat.objects.create(conversa_id=conversa, sequencia=1, pergunta="de novo")


def test_mesma_sequencia_em_conversas_diferentes_e_valida() -> None:
    InteracaoChat.objects.create(conversa_id=uuid.uuid4(), sequencia=1, pergunta="oi")
    InteracaoChat.objects.create(conversa_id=uuid.uuid4(), sequencia=1, pergunta="oi")
    assert InteracaoChat.objects.count() == 2


def test_turnos_ordenam_por_conversa_e_sequencia() -> None:
    conversa = uuid.uuid4()
    InteracaoChat.objects.create(conversa_id=conversa, sequencia=2, pergunta="segunda")
    InteracaoChat.objects.create(conversa_id=conversa, sequencia=1, pergunta="primeira")

    sequencias = list(
        InteracaoChat.objects.filter(conversa_id=conversa).values_list("sequencia", flat=True)
    )
    assert sequencias == [1, 2]


# ---------------------------------------------------------------------------
# Admin — auditoria é somente leitura
# ---------------------------------------------------------------------------


def test_admin_de_interacao_e_somente_leitura() -> None:
    """Turno editável pela mão humana destruiria o valor do log de alucinação."""
    admin = InteracaoChatAdmin(InteracaoChat, AdminSite())

    assert admin.has_add_permission(None) is False
    assert admin.has_change_permission(None) is False
    assert admin.has_delete_permission(None) is False

    readonly = admin.get_readonly_fields(None)
    concretos = {field.name for field in InteracaoChat._meta.fields}
    assert concretos.issubset(set(readonly))


# ---------------------------------------------------------------------------
# Convenções de schema (Oracle)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("model", "tabela"), [(FaqVector, "FAQ_VECTOR"), (InteracaoChat, "INTERACAO_CHAT")]
)
def test_tabelas_em_upper_snake_case(model: type, tabela: str) -> None:
    assert model._meta.db_table == tabela


def test_faq_vector_nao_declara_a_coluna_embedding() -> None:
    """A coluna VECTOR(384, FLOAT32) entra por migration guardada por vendor (Bloco 1B).

    Declará-la no ORM quebraria o CI, que roda em SQLite.
    """
    assert "embedding" not in {field.name for field in FaqVector._meta.fields}


@pytest.mark.parametrize("model", [FaqVector, InteracaoChat])
def test_indices_e_constraints_tem_nome_explicito_e_curto(model: type) -> None:
    nomes = [c.name for c in model._meta.constraints] + [i.name for i in model._meta.indexes]
    for nome in nomes:
        assert nome == nome.upper(), f"{nome} deveria estar em UPPER_SNAKE_CASE"
        assert len(nome) <= 30, f"{nome} tem {len(nome)} chars (limite do Oracle é 30)"
