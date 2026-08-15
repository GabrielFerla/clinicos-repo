# Frontend do ClinicOS

Stack: **Django templates + Tailwind CSS** via `django-tailwind`. Sem Vue, sem
SPA — ADR-0003. Interatividade pontual entra via HTMX em sprints futuras.

## App `apps.theme`

Todo o frontend "infra" vive em `apps/theme/`. Layout no padrão do
`django-tailwind`:

```
apps/theme/
  apps.py                   # ThemeConfig (name="apps.theme")
  static_src/               # fonte do CSS, dependências npm
    package.json            # devDeps: tailwindcss, postcss, autoprefixer
    postcss.config.js
    tailwind.config.js      # globs de content cobrindo todos os apps
    src/styles.css          # @tailwind base/components/utilities + @layer
  templates/
    base.html               # <html> com {% tailwind_css %}
    components/             # componentes reutilizáveis (parciais Django)
      _layout.html
```

Settings relevantes (`config/settings/base.py`):

| Setting              | Valor             | Por quê                                |
|----------------------|-------------------|----------------------------------------|
| `TAILWIND_APP_NAME`  | `"apps.theme"`    | onde o django-tailwind procura assets  |
| `INTERNAL_IPS`       | `["127.0.0.1"]`   | browser-reload (`django-tailwind[reload]`) |
| `NPM_BIN_PATH`       | `"npm"`           | binário npm no container Django        |

## Comandos

Todos rodam dentro do container `django` (que tem Node 20 LTS instalado pelo
`infra/django/Dockerfile`):

| Make                 | Equivalente                                                          |
|----------------------|----------------------------------------------------------------------|
| `make tailwind-install` | `docker compose exec django python manage.py tailwind install`    |
| `make tailwind-dev`     | `docker compose exec django python manage.py tailwind start` (watch) |
| `make tailwind-build`   | `docker compose exec django python manage.py tailwind build` (prod) |

Fluxo típico:

1. **Setup inicial** (uma vez por clone): `make tailwind-install` —
   `npm install` dentro de `apps/theme/static_src/`.
2. **Dev**: `make tailwind-dev` em outro terminal enquanto roda o Django.
   O CSS é recompilado a cada salvamento de template/CSS.
3. **Antes do deploy**: `make tailwind-build` gera o CSS minificado em
   `apps/theme/static/css/dist/styles.css`, depois `collectstatic` o coloca
   onde o nginx serve.

## Onde adicionar componentes

- **Parciais Django reutilizáveis** → `apps/theme/templates/components/`.
  Padrão de nome: `_nome.html` (prefixo `_` deixa claro que é parcial).
  Importe com `{% include "components/_botao.html" %}`.
- **Classes de componente** → `apps/theme/static_src/src/styles.css`, em CSS
  puro, **fora** de `@layer components`. Não é preciosismo: o Tailwind faz
  tree-shaking do que está dentro de `@layer`, emitindo só as classes que
  encontrou nos globs de `content`. Foi por isso que o `.btn`/`.btn-primary`
  original — que morava em `@layer components` e não era usado em template
  nenhum — sumia do CSS compilado. Em CSS puro nada é descartado, e a cascata
  continua certa porque `@tailwind utilities` vem por último no arquivo.
- **Tema (cores, fontes, etc.)** → o `:root` de
  `apps/theme/static_src/src/styles.css` é a **fonte da verdade** [S1-18]. O
  `theme.extend` do `tailwind.config.js` apenas espelha esses tokens
  (`paper`, `ink`, `accent`, `accent2`, `surface`…) apontando para as mesmas
  `var(--*)`, para que utilitário e classe de componente nunca divirjam.
  Retune num lugar só: o `:root`.

## Content globs do Tailwind

O Tailwind purga classes não usadas escaneando arquivos. `tailwind.config.js`
está configurado para varrer:

- `apps/<qualquer-app>/templates/**/*.html`
- `apps/theme/templates/**/*.html`
- `templates/**/*.html` (raiz)
- `apps/<qualquer-app>/forms.py` (para classes em widgets Django)

Se você criar templates fora desses diretórios, **adicione o glob no
`content`** ou as classes vão sumir no build de produção.

## Identidade visual

A identidade chegou na S4 e **não é mais placeholder**: o projeto adota o
design system **Broadsheet** — jornal impresso na web, Source Serif 4
quase-preta sobre papel, ciano e magenta como tintas de processo usadas
pequenas. O guia está em [`DESIGN_SYSTEM.md`](DESIGN_SYSTEM.md); leia a caixa
do topo, que mapeia o guia original para o que existe neste repositório.

Duas regras do sistema que valem como critério de review:

- **A página não se estrutura com réguas, bordas ou caixas.** A separação entre
  seções é espaço em branco. O `.card` é o único componente com caixa e fica
  reservado a itens discretos (listagens), nunca para montar layout. As duas
  réguas permitidas são móveis de primeira página: `.regra-dupla` e
  `.regra-fina`.
- **Não introduza sans-serif para cromo de interface.** O serif *é* o cromo.

Layouts disponíveis em `apps/theme/templates/components/`:

| Layout | Para quê |
|---|---|
| `_layout_publico.html` | Site público. Nav sticky com menu responsivo, rodapé de 4 colunas, assistente flutuante. Espera `clinica` e `chat_sugestoes` no contexto. |
| `_layout_admin.html` | Telas internas (recepção/médico). Nav de módulos e identificação do usuário. |
| `_layout.html` | O contêiner simples de `max-w-7xl`. Usado hoje pelo `/chat/`. |

⚠️ `{% extends %}` tem de ser a **primeira tag** do arquivo — um `{% comment %}`
acima dele derruba o template inteiro com `TemplateSyntaxError`. E o comentário
de cerquilha `{# … #}` do Django é de **uma linha só**: em várias linhas ele
vaza como texto na página.

Ainda pendentes do Design: **S1-19** (logo) e **S1-20** (wireframes). Hoje a
marca é o nome da clínica em Source Serif 4, sem símbolo.
