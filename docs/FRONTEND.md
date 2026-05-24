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
- **Classes utilitárias customizadas** → bloco `@layer components` em
  `apps/theme/static_src/src/styles.css`. Usar `@apply` para combinar
  utilitários Tailwind.
- **Tema (cores, fontes, etc.)** → `theme.extend` em
  `apps/theme/static_src/tailwind.config.js`. Os design tokens reais saem
  da S1-18 (Design).

## Content globs do Tailwind

O Tailwind purga classes não usadas escaneando arquivos. `tailwind.config.js`
está configurado para varrer:

- `apps/<qualquer-app>/templates/**/*.html`
- `apps/theme/templates/**/*.html`
- `templates/**/*.html` (raiz)
- `apps/<qualquer-app>/forms.py` (para classes em widgets Django)

Se você criar templates fora desses diretórios, **adicione o glob no
`content`** ou as classes vão sumir no build de produção.

## Wireframes vs. CSS

S1-18/S1-19/S1-20 (Design) entregam paleta, tipografia e wireframes. Até lá
trabalhe com utilitários Tailwind puros — o `base.html` e o `.btn-primary`
deste sprint são placeholders que **vão ser refeitos** com a identidade
visual real.
