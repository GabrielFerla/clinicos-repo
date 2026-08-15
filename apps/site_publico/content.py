"""Conteúdo editorial da landing pública — [S4-7].

Tudo aqui é **placeholder**. Os textos, nomes, CRMs e preços vieram do
protótipo de design da clínica fictícia ("Clínica de Olhos Exemplo", Porto
Alegre) e servem para a página existir com o volume de texto certo: a
composição de jornal do design system depende de parágrafos reais, não de
`lorem ipsum` curto. A coleta do conteúdo verdadeiro é a **S4-3**.

Por que constantes em módulo, e não banco
-----------------------------------------
Nesta sprint a landing não tem nenhum modelo por trás: `Medico` e
`Especialidade` moram no `apps.crm`/`apps.agenda` e ainda não carregam foto,
bio nem preço de particular. Trocar constante por queryset é uma mudança
localizada — a view monta o mesmo dicionário de contexto e o template não
muda. Enquanto isso, o conteúdo fica versionado e revisável em code review.

Não importe estas constantes de dentro de templates ou de outros apps: a
fronteira pública é a view `apps.site_publico.views.home`.
"""

from __future__ import annotations

# ── A clínica ────────────────────────────────────────────────────────────────
# Consumido pelo `components/_layout_publico.html` (nav e rodapé) e pelo
# trilho de primeira página da landing. Os nomes dos campos são contrato com
# aquele layout: mudar aqui exige mudar lá.
CLINICA: dict[str, str] = {
    "nome": "Clínica de Olhos Exemplo",
    "endereco_linha1": "Rua Exemplo, 123 — Centro",
    "endereco_linha2": "Porto Alegre / RS",
    "referencia": "Duas quadras da estação Mercado",
    "horario_semana": "Segunda a sexta 08h–19h",
    "horario_sabado": "Sábado 08h–13h",
    "horario_domingo": "Domingos e feriados fechado",
    "convenios_linha1": "Unimed · Bradesco Saúde",
    "convenios_linha2": "SulAmérica · Amil · Hapvida",
    "estacionamento": "Estacionamento com 2h grátis",
    "telefone": "(51) 3000-0000",
    "whatsapp": "(51) 99999-0000",
}

# Versões de uma linha só, para o trilho de dateline sob o hero — onde os três
# dados precisam caber lado a lado em versalete.
DATELINE: dict[str, str] = {
    "endereco": "Rua Exemplo, 123 · Centro · Porto Alegre / RS",
    "horarios": "Seg a sex 08h–19h · Sáb 08h–13h",
    "contato": "(51) 3000-0000 · WhatsApp (51) 99999-0000",
}

# ── Índice de primeira página ────────────────────────────────────────────────
# Seis números que resumem a clínica, com condutor pontilhado até o valor.
# No design isso saía do `renderVals()`; aqui é literal, já que nenhum dos
# valores é calculado.
INDICE: list[dict[str, str]] = [
    {"titulo": "Subespecialidades atendidas", "valor": "05"},
    {"titulo": "Oftalmologistas no corpo clínico", "valor": "05"},
    {"titulo": "Consulta particular, com refração", "valor": "R$ 350"},
    {"titulo": "Convênios credenciados", "valor": "05"},
    {"titulo": "Exames de imagem no mesmo prédio", "valor": "03"},
    {"titulo": "Estacionamento no prédio, horas grátis", "valor": "02"},
]

# ── As três colunas de abertura ──────────────────────────────────────────────
# Respondem, em texto corrido, as três dúvidas que mais chegam na recepção.
# São propositalmente longas: o template as justifica com `hyphens: auto` e
# uma coluna curta abriria rios de espaço em branco.
COLUNAS: list[dict[str, str]] = [
    {
        "titulo": "A consulta",
        "texto": (
            "A consulta particular custa R$ 350,00 e inclui a avaliação "
            "oftalmológica completa com exame de refração — o grau de óculos "
            "sai da mesma visita. Pagamento em PIX, dinheiro ou cartão em até "
            "3x sem juros. Cancelamento e remarcação gratuitos até 24 horas "
            "antes."
        ),
    },
    {
        "titulo": "Convênios",
        "texto": (
            "Atendemos Unimed, Bradesco Saúde, SulAmérica, Amil e Hapvida. "
            "Traga a carteirinha e um documento com foto. A cobertura dos "
            "exames varia conforme o plano e alguns pedem autorização prévia "
            "— a recepção confirma antes da sua vinda. Não atendemos pelo SUS."
        ),
    },
    {
        "titulo": "Como chegar",
        "texto": (
            "Rua Exemplo, 123, no Centro de Porto Alegre, a duas quadras da "
            "estação Mercado do Trensurb. O prédio tem estacionamento "
            "conveniado com duas horas gratuitas: valide o ticket na "
            "recepção. Atendemos de segunda a sexta das 08h às 19h e sábado "
            "das 08h às 13h."
        ),
    },
]

# ── Especialidades ───────────────────────────────────────────────────────────
# O numeral zero-padded ("01".."05") é conteúdo, não enfeite: ele é impresso
# como chapa CMYK e o template repete o mesmo texto quatro vezes. Deixá-lo
# pronto aqui evita aritmética de índice dentro do template, que o Django não
# faz sem filtro extra.
ESPECIALIDADES: list[dict[str, str]] = [
    {
        "indice": "01",
        "nome": "Oftalmologia Geral",
        "descricao": "Consulta completa, refração e triagem.",
    },
    {
        "indice": "02",
        "nome": "Retina",
        "descricao": ("Doenças da retina: diabetes, descolamento e degeneração macular."),
    },
    {
        "indice": "03",
        "nome": "Glaucoma",
        "descricao": "Diagnóstico e acompanhamento da pressão intraocular.",
    },
    {
        "indice": "04",
        "nome": "Córnea",
        "descricao": ("Ceratocone, transplante e avaliação para cirurgia refrativa."),
    },
    {
        "indice": "05",
        "nome": "Oftalmologia Pediátrica",
        "descricao": "Atendimento de crianças a partir de 6 meses.",
    },
]

# ── Exames ───────────────────────────────────────────────────────────────────
EXAMES: list[dict[str, str]] = [
    {
        "nome": "Exame de refração",
        "uso": "Grau de óculos e acuidade visual",
        "preco": "incluso na consulta",
    },
    {
        "nome": "Retinografia",
        "uso": "Registro fotográfico do fundo de olho",
        "preco": "R$ 180,00",
    },
    {
        "nome": "Campimetria computadorizada",
        "uso": "Campo visual — acompanhamento de glaucoma",
        "preco": "R$ 240,00",
    },
    {
        "nome": "OCT de mácula",
        "uso": "Corte tomográfico da retina central",
        "preco": "R$ 320,00",
    },
]

# ── Corpo clínico ────────────────────────────────────────────────────────────
# `slot_id` identifica a caixa de foto de cada retrato. Enquanto não houver
# fotografia, o template só desenha a caixa vazia com a proporção 4/5; quando
# as fotos chegarem, o `slot_id` vira o nome do arquivo estático.
MEDICOS: list[dict[str, str]] = [
    {
        "slot_id": "medico-1",
        "nome": "Dra. Ana Lima",
        "crm": "CRM 12345 / RS",
        "areas": "Oftalmologia Geral · Retina",
    },
    {
        "slot_id": "medico-2",
        "nome": "Dr. Bruno Carvalho",
        "crm": "CRM 23456 / RS",
        "areas": "Glaucoma · Oftalmologia Geral",
    },
    {
        "slot_id": "medico-3",
        "nome": "Dra. Carla Menezes",
        "crm": "CRM 34567 / RS",
        "areas": "Córnea",
    },
    {
        "slot_id": "medico-4",
        "nome": "Dr. Diego Rocha",
        "crm": "CRM 45678 / RS",
        "areas": "Oft. Pediátrica · Oft. Geral",
    },
    {
        "slot_id": "medico-5",
        "nome": "Dra. Elisa Prado",
        "crm": "CRM 56789 / RS",
        "areas": "Retina · Glaucoma",
    },
]

# ── Citação em destaque ──────────────────────────────────────────────────────
# A orientação de preparo que mais gera reclamação quando não é dada antes: o
# paciente dilatado que veio dirigindo. As aspas curvas fazem parte do texto —
# o template as pendura na margem com `text-indent` negativo.
CITACAO: dict[str, str] = {
    "texto": (
        "“Em boa parte das consultas usamos colírio para dilatar a pupila: a "
        "visão fica embaçada por 4 a 6 horas e você não deve dirigir na "
        "volta.”"
    ),
    "autoria": (
        "— Orientação de preparo da clínica, também dada pelo assistente "
        "antes de fechar o horário"
    ),
}

# ── Chat ─────────────────────────────────────────────────────────────────────
# Consumido pelo `components/_chat_flutuante.html`. São as quatro perguntas do
# design; todas caem em respostas de FAQ que o chatbot já sabe responder.
CHAT_SUGESTOES: list[str] = [
    "Atende meu convênio?",
    "Quanto custa a consulta?",
    "Tem horário de manhã?",
    "Posso dirigir depois?",
]
