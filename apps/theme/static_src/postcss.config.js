// PostCSS config consumido pelo Tailwind CLI durante o build.
// O django-tailwind chama `npx tailwindcss ...` no diretório `static_src/`,
// e o Tailwind por sua vez carrega este arquivo automaticamente.
module.exports = {
  plugins: {
    tailwindcss: {},
    autoprefixer: {},
  },
};
