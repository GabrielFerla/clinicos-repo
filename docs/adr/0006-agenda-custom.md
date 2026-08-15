# ADR-0006: Tela custom para a grade da agenda, fora do Django Admin

- **Status:** 🟡 Proposed
- **Data:** 2026-08-15
- **Decisor(es):** a decidir — aberto durante a S4-4, aguardando o dev lead

## Contexto

O ADR-0005 elegeu o Django Admin (`django-unfold`) como UI do CRM no MVP1, e fechou com uma ressalva explícita:

> Limitação aceita: fluxos multi-etapa (ex.: agendamento com seleção de horário + paciente + tipo de exame em um único formulário) talvez precisem de telas próprias. Quando aparecer, abrir ADR específico — **não generalizar pra todo o CRM**.

Apareceu. O design da Sprint 4 traz uma tela **Consultas do dia** para a recepção que o `ModelAdmin` não expressa. O problema não é estético — é de forma:

1. **A grade mostra o que não existe.** Um changelist lista registros. Nesta tela, o que a recepção procura ao telefone é o *buraco*: o slot livre entre duas consultas. Um `Consulta.objects` não tem linha para "10h30, livre" — essa informação está em `AgendaSlot` sem `Consulta` associada. São dois modelos numa leitura só.
2. **Duas leituras do mesmo dia, lado a lado.** Grade por horário e listagem tabular. O Admin dá uma tela por model; a recepção alternava entre elas e foi essa a reclamação de origem.
3. **Filtros com contagem por opção.** O `list_filter` do Admin não conta. E as contagens aqui precisam falar do dia inteiro mesmo com filtro aplicado, para dizer para onde ir em seguida.

Vale registrar uma segunda divergência que o ADR-0005 assume e a realidade não confirma: **`django-unfold` não está instalado no projeto**. Não é dependência em `infra/django/requirements/base.txt` nem entrada em `INSTALLED_APPS`. O Admin em uso hoje é o do Django puro. Isso não muda a decisão abaixo, mas o ADR-0005 descreve um estado que não existe, e alguém vai se apoiar nele.

## Alternativas consideradas

### Opção A: forçar no Admin, com `ModelAdmin.changelist_view` sobrescrito
- Prós: não abre precedente; mantém uma UI só.
- Contras: a grade sai de `AgendaSlot` e a listagem de `Consulta` — um dos dois vira enxerto no changelist do outro. Sobrescrever `changelist_view` para injetar contexto de outro model é justamente o tipo de Admin que ninguém consegue manter depois. E o `list_filter` seguiria sem contagem.

### Opção B: tela custom de leitura, edição continua no Admin
- Prós: a grade fica direta (dois querysets, um template); a edição não é duplicada — todo link leva ao `ConsultaAdmin`, que já tem as regras de `save_model`, o recorte por perfil e o `AgendamentoService`. A superfície nova é uma view de leitura.
- Contras: abre uma segunda UI interna. Duplica a regra de visibilidade por perfil fora do `RestritoAoMedicoMixin` — que é real, e por isso está coberta por teste dos dois lados (`apps/core/test_permissoes.py` e `apps/agenda/test_views.py`).

### Opção C: adiar a tela para o MVP2
- Prós: custo zero agora.
- Contras: a grade do dia é o que a Sprint 3 entregou como valor para a recepção; sem ela o `AgendaSlot` só se enxerga pelo changelist, que é lista de linhas e não agenda.

## Decisão

**Opção B.** Uma view custom de **leitura** em `apps/agenda/views.py`, sob `/agenda/`, com o layout interno próprio (`components/_layout_admin.html`). Toda escrita continua no Django Admin.

Limites que esta decisão **não** ultrapassa:

- Não é permissão para migrar o CRM para telas próprias. O default segue sendo registrar em `admin.py`.
- Nada de estado em sessão: os filtros vivem na querystring, então um recorte é um link.
- Nenhum JavaScript. Filtro é `<a href>`, busca é `<form method="get">`.

## Consequências

### Positivas
- A recepção vê grade e listagem na mesma tela, com os buracos visíveis.
- Como o estado está na URL, o dia filtrado se manda pelo WhatsApp e o botão voltar funciona.

### Negativas
- A regra de visibilidade por perfil passa a existir em dois lugares. Mitigado por teste explícito em cada um — inclusive o caso perigoso do `MEDICO` sem `Medico` vinculado, em que o default tem de ser o fechado.
- Mais uma superfície a manter em pé no cross-browser da S4-20.

### Neutras / mitigações
- O N+1 da grade é contido por `select_related` e travado por um teste que compara o custo com 1 e com 5 consultas.

## Notas adicionais

- Implementação: `apps/agenda/views.py`, `apps/agenda/templates/agenda/consultas.html`, testes em `apps/agenda/test_views.py`.
- Se a decisão for recusada, o caminho de volta é curto: apagar a view, a url e o template, e manter a Sprint 4 só com o site público.
