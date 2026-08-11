"""Filtros determinísticos aplicados **antes** de a pergunta chegar ao modelo.

Por que não deixar isso no system prompt
----------------------------------------
Foi onde estava, e saiu de lá por medição. Com o `qwen2.5:3b` e as três
ferramentas registradas::

    system prompt de 2.935 chars (com guardrails) -> chamou ferramenta em 0/5
    system prompt de   230 chars (sem guardrails) -> chamou ferramenta em 4/6

Num modelo pequeno, cada instrução no prompt disputa atenção com a decisão de
usar ferramenta. E o efeito colateral era o oposto do pretendido: com o prompt
longo, o modelo passou a responder de memória sobre convênio e estacionamento —
exatamente a alucinação que o texto tentava impedir.

Há um segundo motivo, mais forte que o desempenho: **regra em prompt é
negociável, regra em código não é**. Uma instrução do tipo "recuse pedidos de
receita" pode ser contornada por prompt injection; uma lista de padrões não.
Isso atende ao risco R6 do ``docs/RISCOS.md`` de forma verificável.

Escopo
------
Só o que é objetivamente reconhecível por padrão textual. Julgamento sutil
continua sendo do modelo — e é coberto pelos testes adversariais da S5-32.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

TELEFONE_CLINICA = "(51) 3000-0000"

RESPOSTA_URGENCIA = (
    "Isso pode ser urgente. Procure atendimento oftalmológico imediatamente, "
    f"ou ligue para a clínica no {TELEFONE_CLINICA}. Não espere pelo agendamento online."
)

RESPOSTA_CONDUTA_MEDICA = (
    "Não posso orientar sobre medicamento, dosagem ou diagnóstico — isso precisa "
    "de avaliação presencial com o oftalmologista. Posso te ajudar a marcar uma "
    f"consulta, ou você pode falar com a recepção no {TELEFONE_CLINICA}."
)

# Sinais de emergência oftalmológica. Verificados **antes** de conduta médica:
# quem descreve perda súbita de visão precisa da orientação de urgência, não de
# uma recusa educada.
#
# Os padrões são tolerantes à ordem das palavras: a primeira versão exigia
# "dor forte no olho" e deixou passar "meu olho está com dor muito forte", que
# é como as pessoas de fato escrevem. Em guardrail de urgência, falso positivo
# (mandar procurar atendimento sem necessidade) é muito mais barato que falso
# negativo.
_URGENCIA = re.compile(
    r"\b(?:"
    r"perd(?:i|a)\s+(?:a\s+)?vis[ãa]o"
    r"|n[ãa]o\s+(?:estou\s+|consigo\s+)?enxerg"
    r"|cegue"
    r"|olho.{0,30}\bdor\s+(?:muito\s+|bem\s+)?(?:forte|intensa|aguda)"
    r"|dor\s+(?:muito\s+|bem\s+)?(?:forte|intensa|aguda).{0,30}\bolho"
    r"|trauma|bati\s+(?:o\s+|no\s+)?olho|acertei\s+o\s+olho"
    r"|produto\s+qu[íi]mico|queimad"
    r"|flashes?\s+de\s+luz|clar[õo]es"
    r"|cortina\s+(?:preta|escura)|sombra\s+na\s+vis[ãa]o"
    r")",
    re.IGNORECASE,
)

# Pedido de conduta clínica. Focado em verbo de pedido + objeto clínico, para
# não capturar quem está só descrevendo um sintoma (esses vão para o FAQ).
_CONDUTA = re.compile(
    r"\b((me\s+)?(d[êe]|da|passa|prescrev|receit|indica|recomend)\w*\s+"
    r"(uma\s+|um\s+|o\s+|a\s+)?(receita|rem[ée]dio|col[íi]rio|medicament|antibi[óo]tic|dosagem)"
    r"|qual\s+(o\s+)?(rem[ée]dio|col[íi]rio|medicament|dosagem|grau)"
    r"|quantas?\s+gotas"
    r"|posso\s+(tomar|usar)\s+\w*\s*(col[íi]rio|rem[ée]dio|medicament))",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class Interceptacao:
    """Resposta pronta que dispensa a ida ao modelo."""

    motivo: str
    resposta: str


def interceptar(pergunta: str) -> Interceptacao | None:
    """Devolve uma resposta canned quando a pergunta não deve ir ao modelo.

    Args:
        pergunta: Texto do paciente.

    Returns:
        A :class:`Interceptacao` correspondente, ou ``None`` para seguir o
        fluxo normal — que é o caso da grande maioria das perguntas.
    """
    if _URGENCIA.search(pergunta):
        return Interceptacao("urgencia", RESPOSTA_URGENCIA)
    if _CONDUTA.search(pergunta):
        return Interceptacao("conduta_medica", RESPOSTA_CONDUTA_MEDICA)
    return None
