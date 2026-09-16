# AGY Skill Router Protocol & Engineering Guidelines

## 1. Roteamento Técnico JIT (0ms)
- **Especializado**: Antes de tarefas de Supabase, Postgres, FastAPI, Tailwind, Testes, Excel/PDF, chame `route_skills(task='...')` (ou CLI `python scripts/auto_route.py '<tarefa>'`).
- **Multi-Stack / Complexo**: Passe `top_k=3` a `5`.
- **Reset**: Ao concluir a demanda ou trocar de contexto, chame `reset_skills()` (ou CLI `python scripts/auto_route.py reset`).

## 2. Pré-Agente (OpenRouter Custo Zero)
- Para demandas vagas, complexas ou com prints/mockups, chame `pre_agent_plan(task='...', auto_route_skills=True)` para extrair escopo, contrato e checklist cirúrgico com skills injetadas sem queimar tokens da cota principal.

## 3. Disciplina de Engenharia & Decisão Permanente
- **Ponytail (YAGNI & Pragmático)**: *O melhor código é o nunca escrito*. Menor diff funcional possível, stdlib/plataforma nativa primeiro, zero abstrações prematuras.
- **Codebase Design (Deep Modules)**: Interfaces simples e enxutas por fora; implementação profunda e autocontida por dentro. Costuras limpas (`seams`).
- **TDD Rigoroso**: Ciclo Red-Green-Refactor estrito. Não crie testes que passam sozinhos nem mocke a própria lógica.
- **Diagnóstico Sistemático de Bugs**: Isole o problema com MRE (reprodução mínima) e oculte segredos (`<REDACTED>`) antes de tentar qualquer fix especulativo.
