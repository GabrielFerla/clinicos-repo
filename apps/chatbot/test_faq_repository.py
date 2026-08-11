"""Testes da busca vetorial — exigem Oracle 23ai real.

Auto-pulados fora do ambiente com Oracle (ver ``conftest.py`` na raiz). Rode
com ``make test-oracle``.

Não há como fingir isto em SQLite: ``VECTOR_DISTANCE`` e o tipo ``VECTOR`` são
do Oracle. E é justamente aqui que moram as armadilhas — bind do vetor,
dimensão e ordenação — então o teste precisa ser contra o banco de verdade.

Estes testes leem a base de **desenvolvimento**, já populada por
``seed_initial`` + ``reindexar_faq``, e são estritamente somente-leitura.

Isso foge do padrão do pytest-django, que criaria um banco de teste isolado, e
a razão é prática: no Oracle, criar o banco de teste exige que o usuário da
aplicação tenha privilégio para criar outro usuário — o ``clinicos`` não tem,
e conceder DBA a ele só para rodar teste seria pior. Some-se que popular os
embeddings do zero custaria uma chamada ao modelo por FAQ a cada execução.

O acesso é liberado por ``django_db_blocker.unblock()`` na fixture abaixo. Como
contrapartida, **nenhum teste deste arquivo escreve** — se algum precisar
escrever um dia, ele muda de arquivo e passa a usar ``django_db``.
"""

from __future__ import annotations

import pytest
from django.conf import settings

from apps.chatbot.models import FaqVector
from apps.chatbot.repositories.faq import (
    FAQRepository,
    VetorIncompativelError,
    _para_vetor_oracle,
)
from apps.chatbot.services.embeddings import get_embedding_provider

pytestmark = pytest.mark.oracle

# Baseline de relevância da S5-17: cada pergunta, com as palavras de um
# paciente, precisa trazer o FAQ correto em primeiro lugar. A asserção é sobre
# **ranking**, nunca sobre o valor exato da distância — esse número muda com o
# modelo de embedding e tornaria o teste falso-vermelho a cada troca.
#
# Os dois primeiros casos são guardas de regressão do modelo de embedding: com
# `all-minilm` (treinado em inglês) eles casavam por sobreposição lexical e
# devolviam "Vocês atendem pelo SUS?" e "Vocês aceitam convênio?". Se voltarem
# a falhar, alguém trocou o modelo por um não-multilíngue.
BASELINE_RELEVANCIA = [
    ("que horas vocês abrem?", "Qual o horário de funcionamento da clínica?"),
    ("horário de atendimento", "Qual o horário de funcionamento da clínica?"),
    ("Quanto custa?", "Quanto custa uma consulta particular?"),
    ("vocês aceitam Unimed?", "Vocês aceitam convênio?"),
    ("posso dirigir depois?", "Posso dirigir depois da consulta?"),
    ("meu olho está vermelho", "Estou com o olho vermelho, devo me preocupar?"),
    ("tem estacionamento?", "Onde fica a clínica e tem estacionamento?"),
    ("preciso tirar a lente antes?", "Preciso tirar a lente de contato antes da consulta?"),
    ("atende criança?", "Vocês atendem crianças?"),
]


@pytest.fixture(autouse=True)
def _banco_de_desenvolvimento(django_db_blocker):
    """Libera leitura da base real (ver docstring do módulo)."""
    with django_db_blocker.unblock():
        yield


@pytest.fixture(scope="module")
def provider():
    return get_embedding_provider()


def _embedding(provider, texto: str) -> list[float]:
    return provider.gerar([texto])[0]


class TestBuscaSemantica:
    @pytest.mark.parametrize(("consulta", "esperado"), BASELINE_RELEVANCIA)
    def test_traz_o_faq_certo_em_primeiro_lugar(self, provider, consulta, esperado):
        resultados = FAQRepository.buscar_semantica(_embedding(provider, consulta), top_k=1)
        assert resultados, f"nenhum resultado para {consulta!r} — a base foi reindexada?"
        assert FaqVector.objects.get(pk=resultados[0][0]).pergunta == esperado

    def test_resultados_vem_ordenados_por_distancia(self, provider):
        distancias = [
            d for _, d in FAQRepository.buscar_semantica(_embedding(provider, "convênio"), top_k=5)
        ]
        assert distancias == sorted(distancias)

    def test_distancia_de_cosseno_fica_no_intervalo_valido(self, provider):
        for _, dist in FAQRepository.buscar_semantica(_embedding(provider, "preço"), top_k=3):
            assert 0.0 <= dist <= 2.0

    def test_respeita_o_top_k(self, provider):
        assert len(FAQRepository.buscar_semantica(_embedding(provider, "consulta"), top_k=2)) == 2

    def test_pergunta_fora_de_assunto_fica_distante(self, provider):
        """Não existe 'nenhum resultado' na busca vetorial — ela sempre devolve
        o menos distante. É o corte de distância na tool que separa sinal de
        ruído, e ele só funciona se assunto alheio pontuar mal de fato."""
        ((_, dist_ruido),) = FAQRepository.buscar_semantica(
            _embedding(provider, "qual a capital da Mongólia"), top_k=1
        )
        ((_, dist_boa),) = FAQRepository.buscar_semantica(
            _embedding(provider, "vocês aceitam convênio"), top_k=1
        )
        assert dist_ruido > dist_boa


class TestValidacaoDeDimensao:
    def test_dimensao_errada_e_rejeitada_antes_de_ir_ao_banco(self):
        """Indexar com um modelo e consultar com outro devolve ranking errado
        sem erro nenhum. A checagem local transforma isso em falha explícita."""
        with pytest.raises(VetorIncompativelError):
            _para_vetor_oracle([0.1] * (settings.EMBEDDING_DIM - 1))

    def test_dimensao_correta_vira_float32(self):
        vetor = _para_vetor_oracle([0.1] * settings.EMBEDDING_DIM)
        assert vetor.typecode == "f"
        assert len(vetor) == settings.EMBEDDING_DIM


class TestBindDoVetor:
    def test_cursor_do_driver_aceita_array(self):
        """Regressão do achado que definiu o desenho do repositório: o cursor do
        Django embrulha o parâmetro em OracleParam e falha com
        `TypeError: unhashable type: 'array.array'`. O cursor do driver aceita."""
        from apps.chatbot.repositories.faq import _cursor_driver

        vetor = _para_vetor_oracle([1.0] + [0.0] * (settings.EMBEDDING_DIM - 1))
        with _cursor_driver() as cursor:
            cursor.execute("SELECT VECTOR_DISTANCE(:a, :b, COSINE) FROM DUAL", a=vetor, b=vetor)
            (distancia,) = cursor.fetchone()
        assert distancia == pytest.approx(0.0, abs=1e-6)
