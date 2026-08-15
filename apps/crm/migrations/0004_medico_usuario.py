"""Vincula ``Medico`` a um ``Usuario`` — pré-requisito da S2-10.

Sem esta coluna não existe a pergunta "quais consultas são *deste* médico?" em
termos que o banco entenda: sobrariam o nome (frágil no primeiro homônimo ou na
primeira correção de grafia) e o ``Group`` do Django, que expressa *o que* um
perfil pode fazer e nunca *sobre quais linhas*.

Por que não há ``AddIndex`` aqui
--------------------------------
O plano original previa um ``IDX_MEDICO_USUARIO`` explícito, pela convenção do
módulo ("todo índice tem nome"). Ele foi verificado contra o Oracle 23ai real e
**não pode existir**::

    ALTER TABLE "MEDICO" ADD "USUARIO_ID" NUMBER(19) NULL UNIQUE ...
    CREATE INDEX "IDX_MEDICO_USUARIO" ON "MEDICO" ("USUARIO_ID")
    -- ORA-01408: such column list already indexed

O ``UNIQUE`` do ``OneToOneField`` já é respaldado por um índice único (aparece
como ``SYS_C0088xx`` em ``USER_INDEXES``), e o Oracle recusa um segundo índice
sobre a mesma lista de colunas. É o mesmo gotcha documentado em
``Especialidade.slug`` e ``Paciente.cpf_hash`` — com a diferença de que lá o
índice extra vinha do default do próprio campo, e aqui viria da mão.

A busca que a S2-10 faz (``Medico.objects.get(usuario=...)``, via
``request.user.medico``) é servida por esse índice implícito. O preço é o nome
autogerado dessa constraint, a mesma exceção já aceita em ``Consulta.slot`` e
``Prontuario.paciente``.

Rollback: ``python manage.py migrate crm 0003_lead`` (testado no Oracle real —
o ``AddField`` reverte com ``ALTER TABLE ... DROP COLUMN``, e como a constraint
nasceu junto da coluna ela cai com ela).
"""

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("crm", "0003_lead"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="medico",
            name="usuario",
            field=models.OneToOneField(
                blank=True,
                db_index=False,
                help_text="Login deste médico no painel. Preenchido, ele passa a ver apenas os próprios pacientes, consultas e prontuários.",
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="medico",
                to=settings.AUTH_USER_MODEL,
                verbose_name="usuário",
            ),
        ),
    ]
