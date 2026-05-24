# ADR-0005: Django Admin (django-unfold) como UI do CRM no MVP1

- **Status:** 🟢 Decided
- **Data:** 2026-05-23
- **Decisor(es):** Dev lead, após validação visual no Checkpoint 5 da Sprint 0

## Contexto

O CRM interno do ClinicOS no MVP1 cobre CRUD de pacientes, médicos, especialidades, horários e configurações administrativas — telas usadas pelos operadores da clínica, nunca pelo paciente final. Há duas trilhas viáveis para essa UI:

1. **Django Admin com `django-unfold`** — admin nativo, customizado por um tema moderno (sidebar fixa, dark mode, cards). Tudo "grátis" ao registrar o modelo em `admin.py`.
2. **UI custom em HTMX + Tailwind** — telas próprias por entidade, mais flexíveis, mas com custo proporcional ao número de modelos.

A escolha foi validada empiricamente no Checkpoint 5 da Sprint 0 (S0-19, S0-20, S0-21): `django-unfold==0.94.0` foi instalado sobre o projeto Django+Oracle do Checkpoint 2, e o usuário inspecionou visualmente o admin rodando em `http://localhost:8005/admin/` antes de decidir.

## Decisão

**Django Admin com `django-unfold` é suficiente para o CRM interno do MVP1.**

UIs custom em HTMX + Tailwind ficam reservadas para contextos onde a experiência de uso justifica o custo:

- Site público da clínica (Sprint 4) — UX pública precisa ser controlada
- Chatbot / chat streaming (Sprint 5) — comportamento real-time e formato de conversa
- Eventualmente prontuário (Sprint 6) — se a complexidade do fluxo clínico exigir

Para qualquer outro CRUD interno, o default é registrar em `admin.py` e seguir.

## Consequências

- **Sprint 2 fica focada em modelagem + permissões + filtros customizados no Admin**, não em construir formulários do zero.
- Cadastros internos ganham look-and-feel uniforme do Unfold.
- Cada novo modelo recebe CRUD funcional automático ao registrar em `unfold.admin.ModelAdmin`.
- Limitação aceita: fluxos multi-etapa (ex.: agendamento com seleção de horário + paciente + tipo de exame em um único formulário) talvez precisem de telas próprias. Quando aparecer, abrir ADR específico — **não generalizar pra todo o CRM**.
- Se em MVP2 alguma área pedir customização visual que Unfold não cobrir, o custo de migrar para HTMX/Tailwind por módulo é **localizado**, não-global.

## Critérios que sustentaram a decisão (Checkpoint 5)

- ✅ Unfold instala limpo sobre Django 5.1.3 + Oracle 23ai (thin mode), sem ajustes na engine.
- ✅ Visual confirmado pelo decisor como **moderno o suficiente** para uso interno.
- ✅ Login, CSRF, CRUD básico de Paciente, listagem e add funcionam sem ajustes.
- ✅ Static files do Unfold servem corretamente via `runserver` (com `collectstatic`).
- ✅ Tema renderiza título customizado ("ClinicOS Spike Admin") via dict `UNFOLD` no settings.

## Notas

- Esta decisão é **escopada para UI interna**. Pacientes nunca enxergam o admin.
- O spike usou o usuário `system` no Oracle por conveniência descartável. A Sprint 1 vai migrar tudo para o usuário `CLINICOS` (USERS tablespace) — independente desta ADR.
- Sprint 2 aplicará a decisão modelando o CRM completo herdando de `unfold.admin.ModelAdmin`.
