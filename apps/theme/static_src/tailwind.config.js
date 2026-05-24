/**
 * Tailwind CSS config do ClinicOS.
 *
 * `content` cobre todos os templates HTML dos 6 apps de domínio + raiz
 * + os forms.py (para futuro uso de classes Tailwind em widgets Django).
 *
 * Importante: os globs são relativos a `apps/theme/static_src/`, que é
 * o cwd em que o Tailwind CLI executa (npm scripts em package.json).
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
    extend: {},
  },
  plugins: [],
};
