# Sprint 4 — Site público da clínica

**Duração:** 2 semanas
**Período:** Semanas 8-9
**Status:** ☐ Pendente

## Meta

> Site institucional bonito, rápido, responsivo e pronto para receber o chatbot na Sprint 5. Conteúdo real da clínica oftalmológica piloto.

---

## Tarefas

### Design
- [ ] **S4-1** Design final das páginas em alta fidelidade no Figma · **DESIGN** · 12h
- [ ] **S4-2** Revisão do design com cliente piloto (1 rodada de ajustes) · **DESIGN+TODOS** · 4h
- [ ] **S4-3** Coleta de conteúdo real da clínica (textos, fotos, equipe) · **TODOS** · 4h

### Estrutura base
- [ ] **S4-4** Layout base com header, footer, menu responsivo · **FRONT** · 6h
- [ ] **S4-5** Sistema de componentes Tailwind: botões, cards, formulários, badges · **FRONT** · 5h
- [ ] **S4-6** Configuração de internacionalização (português-BR) · **BACK** · 2h

### Páginas
- [ ] **S4-7** Página inicial: hero, especialidades em destaque, depoimentos, CTA forte · **FRONT** · 8h
- [ ] **S4-8** Página de Especialidades com conteúdo oftalmológico real · **FRONT+DESIGN** · 6h
- [ ] **S4-9** Página individual de cada subespecialidade (refrativa, catarata, etc.) · **FRONT** · 6h
- [ ] **S4-10** Página de Equipe Médica (puxa do banco, fotos otimizadas) · **FRONT+BACK** · 5h
- [ ] **S4-11** Página de Contato com formulário (entra como lead no CRM) · **FRONT+BACK** · 5h
- [ ] **S4-12** Página de FAQ pública (base do conteúdo para Vector Search na Sprint 5) · **FRONT** · 4h
- [ ] **S4-13** Página de localização com mapa estático · **FRONT** · 3h
- [ ] **S4-14** Páginas legais: política de privacidade, termos, política de cookies · **FRONT+BACK** · 4h

### CTAs e conversão
- [ ] **S4-15** Botão flutuante "Agendar consulta" visível em todas as páginas · **FRONT** · 2h
- [ ] **S4-16** Banner de cookies LGPD com aceite registrado · **FRONT+BACK** · 3h

### Qualidade e performance
- [ ] **S4-17** SEO básico: meta tags, sitemap.xml, robots.txt, Open Graph · **FRONT** · 4h
- [ ] **S4-18** Performance: lazy load, otimização de imagens (WebP), Core Web Vitals · **FRONT** · 5h
- [ ] **S4-19** Acessibilidade: contraste WCAG AA, navegação por teclado, ARIA · **FRONT** · 4h
- [ ] **S4-20** Testes manuais em Chrome, Firefox, Safari + iOS/Android · **QA** · 4h
- [ ] **S4-21** Lighthouse: alvo Performance 90+, Accessibility 95+, SEO 95+ · **FRONT+QA** · 3h

### Deploy de staging
- [ ] **S4-22** Subir site em ambiente de staging · **DEVOPS** · 4h
- [ ] **S4-23** Domínio de staging com HTTPS configurado · **DEVOPS** · 2h

---

## Definition of Done

- [ ] Site público acessível em domínio de staging com HTTPS
- [ ] Lighthouse: Performance ≥ 90, Accessibility ≥ 95, SEO ≥ 95
- [ ] Formulário de contato cria um Lead no CRM corretamente
- [ ] Site funciona em iPhone, Android e desktop sem layout quebrado
- [ ] Banner de cookies LGPD funcionando com aceite registrado
- [ ] Cliente piloto revisou e aprovou o conteúdo das páginas
- [ ] Conteúdo da FAQ pronto para vetorização na Sprint 5

---

## Demos da review

1. **Tour completo do site** — desktop, depois mobile
2. **Formulário de contato** — preencher, ver lead aparecer no CRM
3. **Lighthouse ao vivo** — rodar audit na frente do cliente
4. **Acessibilidade** — navegar usando só teclado

---

## Notas

_(adicionar durante a execução)_

---

## Riscos específicos desta sprint

- **R8** (scope creep) — cliente vai pedir "queria o site com tema escuro também". Postergar
- **Risco específico:** conteúdo da clínica atrasar. Mitigação: começar coleta no início da sprint
