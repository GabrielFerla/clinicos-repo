"""Popula o banco com dados realistas de clínica oftalmológica — S1-16.

Idempotente por construção: **toda** escrita passa por ``get_or_create`` (ou por
uma checagem de existência explícita) e nenhuma delas atualiza linha já gravada.
Rodar duas vezes seguidas não duplica nada e não levanta exceção — é por isso
que ``infra/scripts/setup.sh`` pode chamá-lo em todo ``make setup``.

Cobertura do DoD da S1-16: 5 médicos com subespecialidades distintas, 50
pacientes, 200+ slots futuros e 20 FAQs. Em volta disso vêm os dados que dão o
que demonstrar nas sprints seguintes: regras de agenda `[S3-3]`, consultas nos
cinco status e nas três origens, funil de leads `[S5-23]` e prontuário com
evolução para o paciente já atendido.

Duas restrições moldam o código e valem ser lidas antes de mexer:

* **Determinismo.** Nomes, datas de nascimento e telefones saem de um
  ``random.Random`` com semente fixa (:data:`SEMENTE`), nunca do ``random``
  global. Dado que muda entre execuções torna a idempotência impossível de
  garantir — na segunda rodada o registro "novo" não seria reconhecido como o
  mesmo e viraria duplicata.
* **``EVOLUCAO`` é append-only no banco.** O trigger ``TRG_EVOLUCAO_IMUTAVEL``
  (S1-10) recusa ``UPDATE`` e ``DELETE`` com ``ORA-20001``. Logo: nada de
  ``update_or_create`` nessa tabela, e a checagem de existência é por
  ``consulta`` — chave curta e indexada — e **não** por ``texto``, que no Oracle
  é ``CLOB`` e nem sequer pode aparecer num ``WHERE``.

**``LOG_ACESSO`` fica de fora de propósito**: é trilha de auditoria LGPD escrita
pelo middleware da Sprint 6. Semear acesso que nunca aconteceu poluiria a prova
que a tabela existe para dar.

Depois deste comando, rode ``reindexar_faq`` para gerar os embeddings; sem
isso a busca semântica não devolve nada.
"""

from __future__ import annotations

import datetime as dt
import json
import os
import random
import unicodedata
import uuid
from pathlib import Path
from typing import Any

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from apps.agenda.models import AgendaRegra, AgendaSlot, Consulta
from apps.chatbot.models import FaqVector
from apps.crm.models import Especialidade, Lead, Medico, MedicoEspecialidade, Paciente
from apps.prontuario.models import Evolucao, Prontuario

ARQUIVO_FAQ = Path(__file__).resolve().parents[3] / "core" / "fixtures" / "faq_oftalmologia.json"

# Semente do gerador pseudoaleatório. Qualquer valor serve; o que importa é ser
# **fixo**, para que a mesma execução produza sempre os mesmos 50 pacientes.
SEMENTE = 20260101

# Namespace dos UUIDs determinísticos de conversa dos leads (ver ``_conversa_id``).
NAMESPACE_SEED = uuid.uuid5(uuid.NAMESPACE_DNS, "seed.clinicos.local")

# Superusuário de desenvolvimento. Os nomes das variáveis de ambiente são os
# mesmos do ``createsuperuser`` do Django de propósito — quem já conhece a
# convenção não precisa aprender outra.
#
# `admin`/`admin` era o que o passo 6 do ``infra/scripts/setup.sh`` criava, e é
# o que ``docs/SETUP.md`` documenta desde a S1-3; a credencial fica como estava
# para não invalidar a documentação. O que mudou é que agora **só** nasce com
# ``DEBUG=True`` — ver ``_criar_superusuario``.
SUPERUSUARIO_PADRAO = "admin"
SENHA_DEV_PADRAO = "admin"  # noqa: S105 — credencial de dev, barrada fora de DEBUG

ESPECIALIDADES: list[tuple[str, str, str]] = [
    ("Oftalmologia Geral", "oftalmologia-geral", "Consulta completa, refração e triagem."),
    ("Retina", "retina", "Doenças da retina: diabetes, descolamento e degeneração macular."),
    ("Glaucoma", "glaucoma", "Diagnóstico e acompanhamento da pressão intraocular."),
    ("Córnea", "cornea", "Ceratocone, transplante e avaliação para cirurgia refrativa."),
    (
        "Oftalmologia Pediátrica",
        "oftalmologia-pediatrica",
        "Atendimento de crianças a partir de 6 meses.",
    ),
]

MEDICOS: list[tuple[str, str, str, list[str]]] = [
    ("Dra. Ana Lima", "12345", "RS", ["Oftalmologia Geral", "Retina"]),
    ("Dr. Bruno Carvalho", "23456", "RS", ["Glaucoma", "Oftalmologia Geral"]),
    ("Dra. Carla Menezes", "34567", "RS", ["Córnea"]),
    ("Dr. Diego Rocha", "45678", "RS", ["Oftalmologia Pediátrica", "Oftalmologia Geral"]),
    ("Dra. Elisa Prado", "56789", "RS", ["Retina", "Glaucoma"]),
]

# Grade de atendimento: seg-sex 08h-19h, sáb 08h-13h (bate com a FAQ).
HORARIOS_SEMANA = [dt.time(h, m) for h in range(8, 19) for m in (0, 30)]
HORARIOS_SABADO = [dt.time(h, m) for h in range(8, 13) for m in (0, 30)]
DIAS_A_GERAR = 14
DURACAO_CONSULTA_MIN = 30

# ---------------------------------------------------------------------------
# Regras de agenda
# ---------------------------------------------------------------------------
# Janelas semanais plausíveis por médico. ``dia_semana`` segue a convenção de
# ``AgendaRegra``: 0 = segunda … 6 = domingo (igual a ``date.weekday()``).
#
# O intervalo 12h-13h fica de fora das janelas de dia útil de propósito: é o
# almoço, e é ele que explica por que alguns slots já semeados continuam sem
# regra depois do vínculo (ver ``_vincular_slots_as_regras``).
MANHA = (dt.time(8, 0), dt.time(12, 0))
TARDE = (dt.time(13, 0), dt.time(19, 0))
MANHA_SABADO = (dt.time(8, 0), dt.time(13, 0))

# Data fixa, e não ``timezone.localdate()``: ``vigencia_inicio`` faz parte da
# chave única de ``AgendaRegra``, então uma data móvel criaria um jogo novo de
# regras a cada dia em que o seed rodasse.
VIGENCIA_INICIO = dt.date(2026, 1, 1)

REGRAS_AGENDA: dict[str, list[tuple[int, tuple[dt.time, dt.time]]]] = {
    # Ana Lima — manhãs na semana inteira, tardes de terça e quinta.
    "12345": [(0, MANHA), (1, MANHA), (1, TARDE), (2, MANHA), (3, MANHA), (3, TARDE), (4, MANHA)],
    # Bruno Carvalho — dias alternados, período integral.
    "23456": [(0, MANHA), (0, TARDE), (2, MANHA), (2, TARDE), (4, MANHA), (4, TARDE)],
    # Carla Menezes — meio período, com sábado de manhã.
    "34567": [(1, MANHA), (3, MANHA), (4, MANHA), (5, MANHA_SABADO)],
    # Diego Rocha — pediatria à tarde (fora do horário escolar) e sábado.
    "45678": [(0, TARDE), (1, TARDE), (2, TARDE), (3, TARDE), (5, MANHA_SABADO)],
    # Elisa Prado — segunda metade da semana, período integral.
    "56789": [(2, MANHA), (2, TARDE), (3, MANHA), (3, TARDE), (4, MANHA), (4, TARDE)],
}

# ---------------------------------------------------------------------------
# Pacientes
# ---------------------------------------------------------------------------
TOTAL_PACIENTES = 50

PRENOMES = [
    "Ana", "Beatriz", "Carlos", "Daniela", "Eduardo", "Fernanda", "Gustavo",
    "Helena", "Igor", "Juliana", "Kleber", "Larissa", "Marcelo", "Natália",
    "Otávio", "Patrícia", "Rafael", "Sabrina", "Thiago", "Vanessa", "William",
    "Yara", "Bruno", "Camila", "Diego", "Elaine", "Felipe", "Gabriela",
    "Henrique", "Isabela",
]  # fmt: skip

SOBRENOMES = [
    "Silva", "Santos", "Oliveira", "Souza", "Lima", "Pereira", "Costa",
    "Rodrigues", "Almeida", "Nascimento", "Carvalho", "Araújo", "Ribeiro",
    "Fernandes", "Gomes", "Martins", "Barbosa", "Rocha", "Dias", "Moraes",
    "Cardoso", "Teixeira", "Azevedo", "Machado", "Vieira",
]  # fmt: skip

# ---------------------------------------------------------------------------
# Consultas
# ---------------------------------------------------------------------------
# ``(paciente, médico, offset em dias de atendimento, hora, status, origem)``.
#
# Offset negativo é passado (consulta já resolvida: realizada, faltou ou
# cancelada), positivo é futuro (agendada/confirmada) — o contrário seria dado
# incoerente já na primeira tela da demo. Todos os horários caem no período da
# manhã porque o offset pode aterrissar num sábado, e sábado só tem manhã.
CONSULTAS: list[tuple[int, int, int, dt.time, str, str]] = [
    (0, 0, -12, dt.time(8, 30), Consulta.Status.REALIZADA, Consulta.Origem.RECEPCAO),
    (1, 1, -10, dt.time(9, 0), Consulta.Status.REALIZADA, Consulta.Origem.CHAT),
    (2, 2, -8, dt.time(10, 0), Consulta.Status.REALIZADA, Consulta.Origem.SITE),
    (3, 4, -6, dt.time(11, 0), Consulta.Status.REALIZADA, Consulta.Origem.CHAT),
    (4, 3, -5, dt.time(8, 0), Consulta.Status.FALTOU, Consulta.Origem.RECEPCAO),
    (5, 0, -4, dt.time(9, 30), Consulta.Status.FALTOU, Consulta.Origem.CHAT),
    (6, 1, -3, dt.time(10, 30), Consulta.Status.CANCELADA, Consulta.Origem.SITE),
    (7, 2, -2, dt.time(11, 30), Consulta.Status.CANCELADA, Consulta.Origem.CHAT),
    (8, 3, 1, dt.time(8, 0), Consulta.Status.CONFIRMADA, Consulta.Origem.CHAT),
    (9, 4, 2, dt.time(9, 0), Consulta.Status.CONFIRMADA, Consulta.Origem.RECEPCAO),
    (10, 0, 3, dt.time(10, 0), Consulta.Status.AGENDADA, Consulta.Origem.CHAT),
    (11, 1, 4, dt.time(11, 0), Consulta.Status.AGENDADA, Consulta.Origem.SITE),
    (12, 2, 5, dt.time(8, 30), Consulta.Status.AGENDADA, Consulta.Origem.CHAT),
]

# ---------------------------------------------------------------------------
# Leads
# ---------------------------------------------------------------------------
# Topo do funil: contato que ainda não virou consulta. ``(nome, telefone,
# especialidade, etapa)`` — o e-mail é derivado do nome.
LEADS_ABERTOS: list[tuple[str, str, str, str]] = [
    ("Marina Fontes", "(51) 99812-4471", "Oftalmologia Geral", Lead.Etapa.NOVO),
    ("Rogério Bastos", "(51) 99534-1180", "Glaucoma", Lead.Etapa.NOVO),
    ("Tereza Aguiar", "(51) 98871-6204", "Retina", Lead.Etapa.NOVO),
    ("Luciano Amaral", "(51) 99126-7788", "Córnea", Lead.Etapa.QUALIFICADO),
    ("Priscila Werner", "(51) 98410-3392", "Oftalmologia Pediátrica", Lead.Etapa.QUALIFICADO),
    ("Anderson Klein", "(51) 99657-2051", "Oftalmologia Geral", Lead.Etapa.QUALIFICADO),
]

# Fundo do funil: lead que converteu. ``(índice em CONSULTAS, especialidade,
# etapa)`` — nome, e-mail e telefone saem do paciente da própria consulta, que é
# como a conversão de fato acontece no `[S5-24]`.
LEADS_CONVERTIDOS: list[tuple[int, str, str]] = [
    (8, "Oftalmologia Pediátrica", Lead.Etapa.AGENDADO),
    (10, "Oftalmologia Geral", Lead.Etapa.AGENDADO),
    (12, "Córnea", Lead.Etapa.AGENDADO),
    (0, "Oftalmologia Geral", Lead.Etapa.COMPARECEU),
    (1, "Glaucoma", Lead.Etapa.COMPARECEU),
    (2, "Córnea", Lead.Etapa.RETORNO),
    (3, "Retina", Lead.Etapa.RETORNO),
]

# ---------------------------------------------------------------------------
# Evoluções
# ---------------------------------------------------------------------------
# Texto genérico de propósito: isto é dado de demonstração, não registro
# clínico. Inventar diagnóstico detalhado daria a uma linha de ``EVOLUCAO`` —
# tabela imutável, retida por 20 anos — a aparência de um atendimento real.
TEXTOS_EVOLUCAO = [
    "Consulta de rotina realizada. Acuidade visual aferida e exame externo sem alterações. "
    "Orientações de acompanhamento fornecidas ao paciente. Retorno conforme rotina.",
    "Avaliação realizada sem intercorrências. Paciente orientado quanto ao acompanhamento "
    "periódico e ao uso das medicações prescritas. Retorno agendado.",
    "Atendimento realizado. Exame de rotina concluído, sem queixas no momento. "
    "Paciente orientado a retornar em caso de novos sintomas.",
]


# ---------------------------------------------------------------------------
# Helpers de geração
# ---------------------------------------------------------------------------


def _cpf_com_digitos_verificadores(base: str) -> str:
    """Completa os 9 primeiros dígitos com os dois verificadores da Receita.

    Roda o mesmo laço duas vezes porque o algoritmo é o mesmo nas duas passadas,
    mudando só o peso inicial (10 para o primeiro DV sobre 9 dígitos, 11 para o
    segundo sobre 10). Gerar CPF com DV válido importa aqui porque o cadastro
    real valida — semear números inválidos daria um banco de demonstração em que
    nenhum paciente pode ser reeditado pela tela.

    Args:
        base: Exatamente 9 dígitos.

    Returns:
        Os 11 dígitos do CPF, sem máscara.
    """
    numero = base
    for peso_inicial in (10, 11):
        soma = sum(int(digito) * (peso_inicial - i) for i, digito in enumerate(numero))
        resto = (soma * 10) % 11
        numero += "0" if resto == 10 else str(resto)
    return numero


def _email_de(nome: str, indice: int) -> str:
    """Monta um e-mail a partir do nome, sem acentos e sempre único.

    O domínio é ``example.com`` (reservado pela RFC 2606) e não um provedor de
    verdade: o Mailhog do ambiente de dev entrega o que o sistema mandar, e um
    seed apontando para ``gmail.com`` é um disparo acidental esperando acontecer.
    """
    ascii_puro = unicodedata.normalize("NFKD", nome).encode("ascii", "ignore").decode()
    partes = ascii_puro.lower().split()
    return f"{partes[0]}.{partes[-1]}{indice:02d}@example.com"


def _hora_fim(inicio: dt.time) -> dt.time:
    """Fim do slot de :data:`DURACAO_CONSULTA_MIN` minutos que começa em ``inicio``."""
    referencia = dt.datetime.combine(dt.date(2000, 1, 1), inicio)
    return (referencia + dt.timedelta(minutes=DURACAO_CONSULTA_MIN)).time()


def _dia_de_atendimento(hoje: dt.date, offset: int) -> dt.date:
    """N-ésimo dia de atendimento (seg-sáb) antes ou depois de ``hoje``.

    Um ``timedelta`` cru cairia em domingo uma vez a cada sete, e consulta em dia
    de clínica fechada é o tipo de incoerência que aparece na primeira demo.
    """
    passo = 1 if offset > 0 else -1
    data = hoje
    restantes = abs(offset)
    while restantes:
        data += dt.timedelta(days=passo)
        if data.weekday() != 6:  # domingo: fechado
            restantes -= 1
    return data


def _conversa_id(chave: str) -> uuid.UUID:
    """UUID determinístico para o ``conversa_id`` do lead.

    ``Lead`` não tem constraint de unicidade — e não deve ter, porque a mesma
    pessoa pode voltar meses depois e isso é um lead novo. Sem chave natural, o
    seed precisa fabricar uma: o UUID v5 derivado de uma string estável dá o
    mesmo valor em toda execução, e é por ele que o ``get_or_create`` reconhece
    o lead já semeado.
    """
    return uuid.uuid5(NAMESPACE_SEED, chave)


def _carimbo_de(slot: AgendaSlot) -> dt.datetime:
    """Momento em que a evolução foi registrada: o fim da consulta.

    Precisa ser determinístico porque entra no ``conteudo_hash`` da evolução, e
    a tabela é append-only — hash gravado é hash para sempre.
    """
    momento = dt.datetime.combine(slot.data, slot.hora_fim)
    return timezone.make_aware(momento) if settings.USE_TZ else momento


class Command(BaseCommand):
    help = (
        "Cria especialidades, médicos, regras de agenda, slots, pacientes, "
        "consultas, leads, prontuários e FAQs da clínica piloto."
    )

    @transaction.atomic
    def handle(self, *args: Any, **options: Any) -> None:
        rng = random.Random(SEMENTE)  # noqa: S311 — dado de demonstração, não cripto

        superusuario = self._criar_superusuario()
        especialidades = self._criar_especialidades()
        medicos = self._criar_medicos(especialidades)
        regras_por_medico, regras = self._criar_regras(medicos)
        slots = self._criar_slots(medicos)
        pacientes, novos_pacientes = self._criar_pacientes(rng)
        consultas, novas_consultas = self._criar_consultas(pacientes, medicos)
        vinculados = self._vincular_slots_as_regras(regras_por_medico)
        leads = self._criar_leads(especialidades, consultas)
        prontuarios, evolucoes = self._criar_prontuarios(consultas)
        faqs = self._criar_faqs()

        self.stdout.write(
            self.style.SUCCESS(
                f"{len(especialidades)} especialidades, {len(medicos)} médicos, "
                f"{len(pacientes)} pacientes e {faqs} FAQs."
            )
        )
        self.stdout.write(
            f"Novos nesta execução: {regras} regras de agenda, {slots} slots, "
            f"{novos_pacientes} pacientes, {novas_consultas} consultas, {leads} leads, "
            f"{prontuarios} prontuários e {evolucoes} evoluções. "
            f"{vinculados} slots vinculados a uma regra."
        )
        if superusuario:
            self.stdout.write(f"Acesse /admin/ com o usuário `{superusuario}`.")
        self.stdout.write(
            "Próximo passo: `python manage.py reindexar_faq` para gerar os embeddings."
        )

    def _criar_superusuario(self) -> str | None:
        """Cria o superusuário de desenvolvimento, se for seguro criá-lo.

        Sem isto não há como abrir o ``/admin/``, e o Admin é a UI do CRM no
        MVP1 (ADR-0005): os 50 pacientes semeados existiriam sem que ninguém
        conseguisse vê-los.

        A senha sai de ``DJANGO_SUPERUSER_PASSWORD``. Sem ela, só há criação com
        ``DEBUG=True`` — um superusuário de senha publicada em documentação não
        pode nascer em produção porque alguém rodou ``make seed`` no servidor
        errado.

        Idempotente como o resto do comando: se o usuário já existe, nada é
        tocado. Em especial a **senha não é redefinida** — quem trocou a dele
        não a perde na próxima execução.

        Returns:
            O ``username`` criado ou já existente, ou ``None`` se a criação foi
            pulada por falta de senha fora de ``DEBUG``.
        """
        Usuario = get_user_model()
        username = os.environ.get("DJANGO_SUPERUSER_USERNAME", SUPERUSUARIO_PADRAO)
        email = os.environ.get("DJANGO_SUPERUSER_EMAIL", "admin@clinicos.local")
        senha = os.environ.get("DJANGO_SUPERUSER_PASSWORD")

        if not senha:
            if not settings.DEBUG:
                self.stdout.write(
                    self.style.WARNING(
                        "Superusuário não criado: defina DJANGO_SUPERUSER_PASSWORD. "
                        "A senha padrão só vale com DEBUG=True."
                    )
                )
                return None
            senha = SENHA_DEV_PADRAO

        usuario, criado = Usuario.objects.get_or_create(
            username=username,
            defaults={
                "email": email,
                "perfil": Usuario.Perfil.ADMIN,
                "is_staff": True,
                "is_superuser": True,
            },
        )
        if criado:
            # `set_password` fora do `defaults` porque ele precisa do hash, e
            # `get_or_create` gravaria a senha em claro na coluna.
            usuario.set_password(senha)
            usuario.save(update_fields=["password"])
        return username

    def _criar_especialidades(self) -> dict[str, Especialidade]:
        criadas: dict[str, Especialidade] = {}
        for nome, slug, descricao in ESPECIALIDADES:
            obj, _ = Especialidade.objects.get_or_create(
                nome=nome, defaults={"slug": slug, "descricao": descricao}
            )
            criadas[nome] = obj
        return criadas

    def _criar_medicos(self, especialidades: dict[str, Especialidade]) -> list[Medico]:
        medicos: list[Medico] = []
        for nome, crm, uf, nomes_esp in MEDICOS:
            medico, _ = Medico.objects.get_or_create(
                crm_numero=crm, crm_uf=uf, defaults={"nome": nome}
            )
            for indice, nome_esp in enumerate(nomes_esp):
                MedicoEspecialidade.objects.get_or_create(
                    medico=medico,
                    especialidade=especialidades[nome_esp],
                    defaults={"principal": indice == 0},
                )
            medicos.append(medico)
        return medicos

    def _criar_regras(self, medicos: list[Medico]) -> tuple[dict[int, list[AgendaRegra]], int]:
        """Cria as janelas semanais de :data:`REGRAS_AGENDA`.

        Não gera slot nenhum a partir delas — expandir regra em agenda é o
        ``gerar_slots`` da `[S3-3]`. Aqui as regras existem para (a) dar o que
        demonstrar na tela de agenda e (b) preencher ``AgendaSlot.regra``, que
        sem isso ficaria integralmente nulo e cegaria o tratamento de bordas da
        `[S3-5]`.

        Returns:
            O par ``(regras por ``medico_id``, quantidade criada nesta execução)``.
        """
        por_medico: dict[int, list[AgendaRegra]] = {}
        criadas = 0
        for medico in medicos:
            regras: list[AgendaRegra] = []
            for dia_semana, (inicio, fim) in REGRAS_AGENDA.get(medico.crm_numero, []):
                regra, nova = AgendaRegra.objects.get_or_create(
                    medico=medico,
                    dia_semana=dia_semana,
                    hora_inicio=inicio,
                    vigencia_inicio=VIGENCIA_INICIO,
                    defaults={
                        "hora_fim": fim,
                        "duracao_consulta_min": DURACAO_CONSULTA_MIN,
                        "intervalo_min": 0,
                    },
                )
                regras.append(regra)
                criadas += int(nova)
            por_medico[medico.pk] = regras
        return por_medico, criadas

    def _criar_slots(self, medicos: list[Medico]) -> int:
        """Gera slots livres nos próximos dias úteis, sem duplicar.

        Cada médico atende em dias alternados para a agenda não ficar
        artificialmente cheia — e para a tool ``buscar_slots`` ter casos em que
        um período realmente não tem vaga.
        """
        hoje = timezone.localdate()
        criados = 0
        for offset in range(1, DIAS_A_GERAR + 1):
            data = hoje + dt.timedelta(days=offset)
            if data.weekday() == 6:  # domingo: fechado
                continue
            horarios = HORARIOS_SABADO if data.weekday() == 5 else HORARIOS_SEMANA
            for indice, medico in enumerate(medicos):
                if (offset + indice) % 2:
                    continue
                for hora in horarios:
                    _, novo = AgendaSlot.objects.get_or_create(
                        medico=medico,
                        data=data,
                        hora_inicio=hora,
                        defaults={
                            "hora_fim": (
                                dt.datetime.combine(data, hora) + dt.timedelta(minutes=30)
                            ).time(),
                            "status": AgendaSlot.Status.LIVRE,
                        },
                    )
                    criados += int(novo)
        return criados

    def _vincular_slots_as_regras(self, por_medico: dict[int, list[AgendaRegra]]) -> int:
        """Aponta cada slot sem regra para a janela semanal que o cobre.

        Os slots são semeados por :meth:`_criar_slots` direto, sem passar por
        ``AgendaRegra`` (a geração a partir da regra é a `[S3-5]`), então a coluna
        ``REGRA_ID`` nasceria toda nula. Aqui ela é preenchida por casamento de
        dia da semana + horário.

        **Nem todo slot encontra regra**, e isso é esperado: os horários de
        12h-12h30 caem no almoço, que as janelas de :data:`REGRAS_AGENDA` não
        cobrem. ``AgendaSlot.regra`` é anulável exatamente para casos assim.

        Idempotente porque o filtro é ``regra__isnull=True``: na segunda execução
        os slots já vinculados nem entram no ``UPDATE``.
        """
        pendentes: list[AgendaSlot] = []
        for slot in AgendaSlot.objects.filter(regra__isnull=True).iterator():
            for regra in por_medico.get(slot.medico_id, ()):
                if (
                    regra.dia_semana == slot.data.weekday()
                    and regra.vigencia_inicio <= slot.data
                    and regra.hora_inicio <= slot.hora_inicio < regra.hora_fim
                ):
                    slot.regra = regra
                    pendentes.append(slot)
                    break
        AgendaSlot.objects.bulk_update(pendentes, ["regra"], batch_size=200)
        return len(pendentes)

    def _criar_pacientes(self, rng: random.Random) -> tuple[list[Paciente], int]:
        """Cria os 50 pacientes do DoD, com CPF válido e cifrado.

        A identidade do paciente é o CPF, não o nome: dois homônimos são duas
        pessoas, e o mesmo CPF é sempre a mesma. Por isso a checagem de
        existência é ``buscar_por_cpf`` (que compara o ``cpf_hash`` HMAC, sem
        descriptografar linha nenhuma) e o número entra por ``definir_cpf``, o
        único caminho que preenche as duas colunas derivadas de uma vez.

        Os atributos aleatórios são sorteados **antes** da checagem de
        existência, sempre. Sortear só no ramo de criação faria o ``rng``
        avançar de forma diferente na segunda execução e desalinharia todo o
        resto da sequência.

        Returns:
            O par ``(pacientes na ordem de índice, quantidade criada agora)``.
        """
        pacientes: list[Paciente] = []
        criados = 0
        nomes_usados: set[str] = set()
        for indice in range(TOTAL_PACIENTES):
            nome = f"{rng.choice(PRENOMES)} {rng.choice(SOBRENOMES)} {rng.choice(SOBRENOMES)}"
            while nome in nomes_usados:
                nome = f"{rng.choice(PRENOMES)} {rng.choice(SOBRENOMES)} {rng.choice(SOBRENOMES)}"
            nomes_usados.add(nome)
            nascimento = dt.date(rng.randint(1942, 2019), rng.randint(1, 12), rng.randint(1, 28))
            telefone = f"(51) 9{rng.randint(1000, 9999)}-{rng.randint(1000, 9999)}"
            # Base espaçada o bastante para nunca cair num CPF de dígito
            # repetido (11111111111 e afins), que todo validador recusa.
            cpf = _cpf_com_digitos_verificadores(f"{100_000_000 + indice * 1_234_567:09d}")

            existente = Paciente.objects.buscar_por_cpf(cpf).first()
            if existente is not None:
                pacientes.append(existente)
                continue

            paciente = Paciente(
                nome=nome,
                data_nascimento=nascimento,
                email=_email_de(nome, indice),
                telefone=telefone,
            )
            paciente.definir_cpf(cpf)
            paciente.save()
            pacientes.append(paciente)
            criados += 1
        return pacientes, criados

    def _criar_consultas(
        self, pacientes: list[Paciente], medicos: list[Medico]
    ) -> tuple[list[Consulta], int]:
        """Ocupa slots reais com as consultas de :data:`CONSULTAS`.

        O slot entra por ``get_or_create``: os de data futura já existem (vieram
        de :meth:`_criar_slots`) e são reaproveitados; os de data passada são
        criados aqui, porque a grade só olha para frente e uma consulta
        ``REALIZADA`` num horário de amanhã não é dado, é bug de demonstração.

        Todo slot com consulta em cima vira ``RESERVADO``. Deixá-lo ``LIVRE``
        faria a tool ``buscar_slots`` oferecer ao paciente um horário que a
        recepção já vendeu.
        """
        hoje = timezone.localdate()
        consultas: list[Consulta] = []
        criadas = 0
        for indice_paciente, indice_medico, offset, hora, status, origem in CONSULTAS:
            medico = medicos[indice_medico]
            data = _dia_de_atendimento(hoje, offset)
            slot, _ = AgendaSlot.objects.get_or_create(
                medico=medico,
                data=data,
                hora_inicio=hora,
                defaults={
                    "hora_fim": _hora_fim(hora),
                    "status": AgendaSlot.Status.RESERVADO,
                },
            )
            consulta, nova = Consulta.objects.get_or_create(
                slot=slot,
                defaults={
                    "paciente": pacientes[indice_paciente],
                    "medico": medico,
                    "status": status,
                    "origem": origem,
                },
            )
            if slot.status != AgendaSlot.Status.RESERVADO:
                slot.status = AgendaSlot.Status.RESERVADO
                slot.save(update_fields=["status"])
            consultas.append(consulta)
            criadas += int(nova)
        return consultas, criadas

    def _criar_leads(
        self, especialidades: dict[str, Especialidade], consultas: list[Consulta]
    ) -> int:
        """Monta um funil com as cinco etapas, metade dele já convertido.

        A `[S5-23]` precisa de leads espalhados pelas etapas para o funil do
        Admin ter alguma forma, e a métrica de conversão do chatbot `[S5-28]`
        precisa de leads com ``consulta`` preenchida para ter numerador.
        """
        criados = 0
        for indice, (nome, telefone, especialidade, etapa) in enumerate(LEADS_ABERTOS):
            _, novo = Lead.objects.get_or_create(
                conversa_id=_conversa_id(f"lead-aberto-{indice}"),
                defaults={
                    "nome": nome,
                    "email": _email_de(nome, indice),
                    "telefone": telefone,
                    "especialidade_interesse": especialidades[especialidade],
                    "etapa": etapa,
                },
            )
            criados += int(novo)

        for indice, (indice_consulta, especialidade, etapa) in enumerate(LEADS_CONVERTIDOS):
            consulta = consultas[indice_consulta]
            paciente = consulta.paciente
            _, novo = Lead.objects.get_or_create(
                conversa_id=_conversa_id(f"lead-convertido-{indice}"),
                defaults={
                    "nome": paciente.nome,
                    "email": paciente.email,
                    "telefone": paciente.telefone,
                    "especialidade_interesse": especialidades[especialidade],
                    "etapa": etapa,
                    "consulta": consulta,
                },
            )
            criados += int(novo)
        return criados

    def _criar_prontuarios(self, consultas: list[Consulta]) -> tuple[int, int]:
        """Abre prontuário e registra uma evolução por consulta já realizada.

        **Sem ``get_or_create`` na evolução, e por um motivo de banco.** A tabela
        ``EVOLUCAO`` tem o trigger ``TRG_EVOLUCAO_IMUTAVEL`` (S1-10), que recusa
        ``UPDATE`` e ``DELETE`` com ``ORA-20001``. Qualquer ``update_or_create``
        estouraria na segunda execução do seed, e um ``get_or_create`` cujo
        ``lookup`` incluísse ``texto`` seria pior ainda: no Oracle a coluna é
        ``CLOB`` e não pode aparecer num ``WHERE``. A checagem é por ``consulta``
        — coluna curta, indexada por ``IDX_EVOLUCAO_CONSULTA``, e um-para-um com
        a evolução do seed — e o caminho de escrita é só ``create``.

        Returns:
            O par ``(prontuários criados agora, evoluções criadas agora)``.
        """
        prontuarios = 0
        evolucoes = 0
        for indice, consulta in enumerate(consultas):
            if consulta.status != Consulta.Status.REALIZADA:
                continue
            prontuario, novo = Prontuario.objects.get_or_create(paciente=consulta.paciente)
            prontuarios += int(novo)
            if Evolucao.objects.filter(consulta=consulta).exists():
                continue
            Evolucao.objects.create(
                prontuario=prontuario,
                medico=consulta.medico,
                consulta=consulta,
                texto=TEXTOS_EVOLUCAO[indice % len(TEXTOS_EVOLUCAO)],
                criado_em=_carimbo_de(consulta.slot),
            )
            evolucoes += 1
        return prontuarios, evolucoes

    def _criar_faqs(self) -> int:
        if not ARQUIVO_FAQ.exists():
            self.stdout.write(self.style.WARNING(f"FAQ não encontrada em {ARQUIVO_FAQ}"))
            return 0
        registros = json.loads(ARQUIVO_FAQ.read_text(encoding="utf-8"))
        for item in registros:
            FaqVector.objects.get_or_create(
                pergunta=item["pergunta"],
                defaults={
                    "resposta": item["resposta"],
                    "categoria": item.get("categoria", ""),
                },
            )
        return len(registros)
