/**
 * Tailwind CSS config do ClinicOS.
 *
 * `content` cobre todos os templates HTML dos 6 apps de domínio + raiz
 * + os forms.py (para futuro uso de classes Tailwind em widgets Django).
 *
 * Importante: os globs são relativos a `apps/theme/static_src/`, que é
 * o cwd em que o Tailwind CLI executa (npm scripts em package.json).
 *
 * O `theme.extend` abaixo espelha os tokens do design system Broadsheet
 * declarados em `src/styles.css` [S1-18]. Ele NÃO os redefine: aponta para as
 * mesmas `var(--*)`, de modo que existe um único lugar para retunar o visual
 * (o `:root` do styles.css) e as duas formas de escrever — classe de
 * componente (`.btn-primary`) e utilitário (`bg-accent text-paper`) — nunca
 * divergem. Sem isto, quem escrevesse Tailwind puro reintroduziria o cinza
 * padrão do framework e desmontaria a paleta de tinta.
 */
module.exports = {
  content: [
    // Templates de qualquer app de domínio (apps/<app>/templates/...).
    '../../**/templates/**/*.html',
    // Templates do app theme propriamente dito.
    '../templates/**/*.html',
    // Templates globais na raiz do projeto.
    '../../../templates/**/*.html',
    // Classes Tailwind eventualmente declaradas em widgets/forms Django.
    '../../**/forms.py',
  ],
  theme: {
    extend: {
      colors: {
        // Papéis principais.
        paper: 'var(--color-bg)',
        surface: 'var(--color-surface)',
        ink: 'var(--color-text)',
        divisor: 'var(--color-divider)',
        // Amarelo de processo — só para tratamento de impressão, nunca cromo.
        processo: 'var(--color-process-yellow)',
        neutral: {
          100: 'var(--color-neutral-100)',
          200: 'var(--color-neutral-200)',
          300: 'var(--color-neutral-300)',
          400: 'var(--color-neutral-400)',
          500: 'var(--color-neutral-500)',
          600: 'var(--color-neutral-600)',
          700: 'var(--color-neutral-700)',
          800: 'var(--color-neutral-800)',
          900: 'var(--color-neutral-900)',
        },
        accent: {
          DEFAULT: 'var(--color-accent)',
          100: 'var(--color-accent-100)',
          200: 'var(--color-accent-200)',
          300: 'var(--color-accent-300)',
          400: 'var(--color-accent-400)',
          500: 'var(--color-accent-500)',
          600: 'var(--color-accent-600)',
          700: 'var(--color-accent-700)',
          800: 'var(--color-accent-800)',
          900: 'var(--color-accent-900)',
        },
        accent2: {
          DEFAULT: 'var(--color-accent-2)',
          100: 'var(--color-accent-2-100)',
          200: 'var(--color-accent-2-200)',
          300: 'var(--color-accent-2-300)',
          400: 'var(--color-accent-2-400)',
          500: 'var(--color-accent-2-500)',
          600: 'var(--color-accent-2-600)',
          700: 'var(--color-accent-2-700)',
          800: 'var(--color-accent-2-800)',
          900: 'var(--color-accent-2-900)',
        },
      },
      fontFamily: {
        // O serif é o cromo: não existe sans neste sistema.
        heading: 'var(--font-heading)',
        body: 'var(--font-body)',
        sans: 'var(--font-body)',
        serif: 'var(--font-body)',
      },
      spacing: {
        1: 'var(--space-1)',
        2: 'var(--space-2)',
        3: 'var(--space-3)',
        4: 'var(--space-4)',
        6: 'var(--space-6)',
        8: 'var(--space-8)',
      },
      borderRadius: {
        sm: 'var(--radius-sm)',
        DEFAULT: 'var(--radius-md)',
        md: 'var(--radius-md)',
        lg: 'var(--radius-lg)',
      },
      boxShadow: {
        sm: 'var(--shadow-sm)',
        DEFAULT: 'var(--shadow-md)',
        md: 'var(--shadow-md)',
        lg: 'var(--shadow-lg)',
      },
    },
  },
  plugins: [],
};
