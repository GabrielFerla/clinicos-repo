"""Testes da camada de embeddings — sem rede, sem banco.

O foco é a invariante que ``docs/CHAT_MVP.md`` §Bloco 2 marca como crítica:
indexar com um modelo e consultar com outro devolve **lixo sem erro nenhum**.
A validação de dimensão é a única coisa entre esse silêncio e um ranking
errado, então ela é testada por vários ângulos.

O provedor real é exercitado com um transporte injetado — cobre o parsing da
resposta do Ollama e a tradução de erro, sem tocar na rede.
"""

from __future__ import annotations

import math
import urllib.error

import pytest
from django.core.exceptions import ImproperlyConfigured

from apps.chatbot.services.embeddings import (
    MENSAGEM_INDISPONIVEL,
    DimensaoEmbeddingError,
    EmbeddingError,
    EmbeddingIndisponivelError,
    EmbeddingProvider,
    FakeEmbeddingProvider,
    OllamaEmbeddingProvider,
    get_embedding_provider,
    validar_dimensoes,
)

TEXTO = "A clínica atende convênio?"

# Valor congelado: os três primeiros floats de ``FakeEmbeddingProvider`` (384
# dimensões) para :data:`TEXTO`. Serve de detector de mudança no algoritmo —
# trocar SHA-256 por ``hash()``, mudar a expansão de bytes ou a normalização
# muda estes números, e qualquer índice gerado antes vira lixo.
GOLDEN = [0.041922802422889996, -0.014613704640445422, 0.08165050802279887]


def _transporte(resposta: dict | Exception):
    """Fabrica um transporte que devolve (ou levanta) o que o teste mandar."""

    def transportar(payload: dict) -> dict:
        transportar.payload = payload
        if isinstance(resposta, Exception):
            raise resposta
        return resposta

    transportar.payload = None
    return transportar


# ---------------------------------------------------------------------------
# FakeEmbeddingProvider
# ---------------------------------------------------------------------------
class TestFakeEmbeddingProvider:
    def test_satisfaz_o_protocolo(self):
        assert isinstance(FakeEmbeddingProvider(), EmbeddingProvider)

    def test_usa_a_dimensao_das_settings(self, settings):
        vetores = FakeEmbeddingProvider().gerar([TEXTO])

        assert len(vetores) == 1
        assert len(vetores[0]) == settings.EMBEDDING_DIM == 384

    def test_dimensao_pode_ser_sobrescrita(self):
        assert len(FakeEmbeddingProvider(dim=8).gerar(["x"])[0]) == 8

    def test_e_deterministico_na_mesma_execucao(self):
        provedor = FakeEmbeddingProvider()

        assert provedor.gerar([TEXTO]) == provedor.gerar([TEXTO])
        assert FakeEmbeddingProvider().gerar([TEXTO]) == provedor.gerar([TEXTO])

    def test_e_estavel_entre_execucoes(self):
        """Deriva de SHA-256, não de ``hash()`` (aleatorizado por processo)."""
        vetor = FakeEmbeddingProvider().gerar([TEXTO])[0]

        assert vetor[:3] == pytest.approx(GOLDEN, abs=1e-12)

    def test_textos_diferentes_geram_vetores_diferentes(self):
        primeiro, segundo = FakeEmbeddingProvider().gerar([TEXTO, "outro texto"])

        assert primeiro != segundo

    def test_vetor_normalizado_l2(self):
        """A distância cosseno do Oracle assume norma 1."""
        for vetor in FakeEmbeddingProvider().gerar([TEXTO, "", "outro"]):
            assert math.sqrt(sum(valor * valor for valor in vetor)) == pytest.approx(1.0)

    def test_valores_no_intervalo_esperado(self):
        vetor = FakeEmbeddingProvider().gerar([TEXTO])[0]

        assert all(-1.0 <= valor <= 1.0 for valor in vetor)

    def test_lote_preserva_a_ordem(self):
        textos = ["um", "dois", "três"]
        provedor = FakeEmbeddingProvider()

        lote = provedor.gerar(textos)

        assert lote == [provedor.gerar([texto])[0] for texto in textos]

    def test_lista_vazia(self):
        assert FakeEmbeddingProvider().gerar([]) == []


# ---------------------------------------------------------------------------
# Validação de dimensão — a guarda contra o "lixo sem erro"
# ---------------------------------------------------------------------------
class TestValidarDimensoes:
    def test_aceita_o_esperado(self):
        validar_dimensoes(
            [[0.1] * 384], dim_esperada=384, quantidade_esperada=1, modelo="all-minilm"
        )

    def test_recusa_dimensao_divergente(self):
        with pytest.raises(DimensaoEmbeddingError) as excinfo:
            validar_dimensoes(
                [[0.1] * 768], dim_esperada=384, quantidade_esperada=1, modelo="nomic"
            )

        mensagem = str(excinfo.value)
        assert "768" in mensagem
        assert "384" in mensagem
        assert "nomic" in mensagem
        assert "reindexe" in mensagem

    def test_aponta_qual_texto_divergiu(self):
        vetores = [[0.1] * 384, [0.1] * 384, [0.1] * 3]

        with pytest.raises(DimensaoEmbeddingError, match="#2"):
            validar_dimensoes(vetores, dim_esperada=384, quantidade_esperada=3, modelo="all-minilm")

    def test_recusa_quantidade_divergente(self):
        with pytest.raises(DimensaoEmbeddingError, match="2 vetor"):
            validar_dimensoes(
                [[0.1] * 384] * 2, dim_esperada=384, quantidade_esperada=3, modelo="x"
            )

    def test_e_capturavel_pela_base(self):
        with pytest.raises(EmbeddingError):
            validar_dimensoes([], dim_esperada=384, quantidade_esperada=1, modelo="x")


# ---------------------------------------------------------------------------
# OllamaEmbeddingProvider com transporte injetado
# ---------------------------------------------------------------------------
class TestOllamaEmbeddingProvider:
    def test_monta_o_payload_do_endpoint_nativo(self):
        transporte = _transporte({"embeddings": [[0.1] * 4, [0.2] * 4]})
        provedor = OllamaEmbeddingProvider(modelo="all-minilm", dim=4, transporte=transporte)

        provedor.gerar(["um", "dois"])

        assert transporte.payload == {"model": "all-minilm", "input": ["um", "dois"]}

    def test_url_aponta_para_api_embed(self, settings):
        settings.EMBEDDING_BASE_URL = "http://host.docker.internal:11434/"

        assert OllamaEmbeddingProvider().url == "http://host.docker.internal:11434/api/embed"

    def test_converte_a_resposta_em_floats(self):
        transporte = _transporte({"embeddings": [[1, 0, 0, 0]]})
        provedor = OllamaEmbeddingProvider(dim=4, transporte=transporte)

        vetores = provedor.gerar(["um"])

        assert vetores == [[1.0, 0.0, 0.0, 0.0]]
        assert all(isinstance(valor, float) for valor in vetores[0])

    def test_lista_vazia_nao_chama_a_rede(self):
        transporte = _transporte(AssertionError("não deveria ter chamado a rede"))
        provedor = OllamaEmbeddingProvider(dim=4, transporte=transporte)

        assert provedor.gerar([]) == []

    def test_dimensao_divergente_do_provedor_e_recusada(self):
        """Modelo trocado sem migrar: precisa explodir, não devolver ranking ruim."""
        transporte = _transporte({"embeddings": [[0.1] * 768]})
        provedor = OllamaEmbeddingProvider(modelo="nomic", dim=384, transporte=transporte)

        with pytest.raises(DimensaoEmbeddingError):
            provedor.gerar([TEXTO])

    def test_resposta_sem_a_chave_embeddings(self):
        provedor = OllamaEmbeddingProvider(dim=4, transporte=_transporte({"erro": "x"}))

        with pytest.raises(EmbeddingIndisponivelError):
            provedor.gerar(["um"])

    def test_falha_de_rede_vira_mensagem_amigavel(self):
        erro = urllib.error.URLError("[Errno 111] Connection refused")
        provedor = OllamaEmbeddingProvider(dim=4, transporte=_transporte(erro))

        with pytest.raises(EmbeddingIndisponivelError) as excinfo:
            provedor.gerar(["um"])

        assert str(excinfo.value) == MENSAGEM_INDISPONIVEL

    def test_mensagem_de_erro_nao_vaza_host(self):
        erro = urllib.error.URLError("host.docker.internal:11434 recusou conexão")
        provedor = OllamaEmbeddingProvider(dim=4, transporte=_transporte(erro))

        with pytest.raises(EmbeddingIndisponivelError) as excinfo:
            provedor.gerar(["um"])

        assert "host.docker.internal" not in str(excinfo.value)
        assert "11434" not in str(excinfo.value)

    def test_url_com_esquema_invalido_e_erro_de_configuracao(self):
        with pytest.raises(ImproperlyConfigured, match="http"):
            OllamaEmbeddingProvider(base_url="file:///etc/passwd")


# ---------------------------------------------------------------------------
# Fábrica
# ---------------------------------------------------------------------------
class TestGetEmbeddingProvider:
    def test_provedor_fake(self, settings):
        settings.EMBEDDING_PROVIDER = "fake"

        assert isinstance(get_embedding_provider(), FakeEmbeddingProvider)

    def test_provedor_ollama(self, settings):
        settings.EMBEDDING_PROVIDER = "ollama"

        assert isinstance(get_embedding_provider(), OllamaEmbeddingProvider)

    def test_nome_e_normalizado(self, settings):
        settings.EMBEDDING_PROVIDER = " Fake "

        assert isinstance(get_embedding_provider(), FakeEmbeddingProvider)

    def test_provedor_desconhecido_falha_com_as_opcoes_validas(self, settings):
        settings.EMBEDDING_PROVIDER = "sentence-transformers"

        with pytest.raises(ImproperlyConfigured, match="fake, ollama"):
            get_embedding_provider()


# ---------------------------------------------------------------------------
# Smoke contra o Ollama real (auto-pulado; CLINICOS_TEST_LLM=1 habilita)
# ---------------------------------------------------------------------------
@pytest.mark.llm
class TestOllamaEmbeddingReal:
    def test_gera_384_dimensoes(self, settings):
        vetores = OllamaEmbeddingProvider().gerar([TEXTO, "Qual o horário de funcionamento?"])

        assert len(vetores) == 2
        assert all(len(vetor) == settings.EMBEDDING_DIM for vetor in vetores)

    def test_textos_iguais_geram_o_mesmo_vetor(self):
        provedor = OllamaEmbeddingProvider()

        primeiro, segundo = provedor.gerar([TEXTO, TEXTO])

        assert primeiro == pytest.approx(segundo)
