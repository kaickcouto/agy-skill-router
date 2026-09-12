# Google Antigravity (AGY) - Skill Router Protocol

Este projeto opera como o roteador dinâmico de habilidades técnicas do Antigravity (AGY).

## Diretrizes de Execução para o Agente AGY:

1. **Roteamento de Demanda**:
   - Antes de iniciar qualquer tarefa técnica especializada (Supabase, Postgres, Tailwind, Testes E2E, Docker, Planilhas Excel/PDF), chame a tool MCP `route_skills(task='...')` ou execute `python scripts/auto_route.py '<tarefa>'`.
   - Isso injetará instantaneamente as 1–2 skills especializadas em `.agent/skills/` via Windows Directory Junctions (0ms).

2. **Inspeção de Documentação da Skill**:
   - Para entender os gatilhos e regras de uma skill antes de aplicá-la, consulte a tool MCP `skill_info(skill_id)` ou leia o recurso `skills://active/<skill_id>`.

3. **Economia de Contexto & Reset**:
   - Ao finalizar a implementação de uma demanda ou antes de trocar de contexto, execute `reset_skills()` ou `python scripts/auto_route.py reset`.
   - O hook nativo `Stop` do AGY em `.agent/hooks.json` e o hook git `post-commit` executam a limpeza automática como salvaguarda.
