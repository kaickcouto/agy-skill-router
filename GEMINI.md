# Google Antigravity (AGY) - Skill Router Protocol

Este projeto opera como o roteador dinâmico de habilidades técnicas do Antigravity (AGY).

## Diretrizes de Execução para o Agente AGY:

1. **Roteamento de Demanda**:
   - Antes de iniciar qualquer tarefa técnica especializada (Supabase, Postgres, Tailwind, Testes E2E, Docker, Planilhas Excel/PDF), chame a tool MCP `route_skills(task='...')` ou execute `python scripts/auto_route.py '<tarefa>'`.
   - **Tarefas Complexas**: Para demandas multi-stack (ex: Banco + Frontend + Testes), passe `top_k=3` a `6` em `route_skills(task='...', top_k=4)` ou no CLI com `--top-k 4`.
   - Isso injetará instantaneamente as skills especializadas em `.agent/skills/` via Windows Directory Junctions (0ms).

2. **Pré-Agente & Decomposição Gratuita (OpenRouter)**:
   - Para pedidos informais, complexos ou com imagens/prints, execute `python scripts/pre_agent.py '<tarefa>' --route` (ou chame a tool MCP `pre_agent_plan(task='...', auto_route_skills=True)`).
   - Isso usa modelos gratuitos em cascata para extrair escopo, contrato e checklist, injetando as skills automaticamente sem gastar tokens do modelo principal.

3. **Inspeção de Documentação da Skill**:
   - Para entender os gatilhos e regras de uma skill antes de aplicá-la, consulte a tool MCP `skill_info(skill_id)` ou leia o recurso `skills://active/<skill_id>`.

4. **Economia de Contexto & Reset**:
   - Ao finalizar a implementação de uma demanda ou antes de trocar de contexto, execute `reset_skills()` ou `python scripts/auto_route.py reset`.
   - O hook nativo `Stop` do AGY em `.agent/hooks.json` e o hook git `post-commit` executam a limpeza automática como salvaguarda.

5. **Diretriz Comportamental Permanente: Ponytail (Mindset Sênior Pragmático / YAGNI)**:
   - *O melhor código é o código nunca escrito.* Em toda tarefa de implementação, siga estritamente a Escada de Decisão do Ponytail:
     1. **Precisa mesmo existir?** (Se for especulativo/desnecessário, elimine).
     2. **Já existe no codebase?** (Reutilize helpers, types ou padrões já presentes antes de criar novos).
     3. **A Stdlib resolve?** (Priorize bibliotecas padrão da linguagem).
     4. **Recurso nativo da plataforma resolve?** (HTML nativo, CSS nativo ou constraints de banco antes de JS/código).
     5. **Dependência já instalada resolve?** (Nunca adicione pacotes externos novos para o que poucas linhas resolvem).
     6. **Pode ser em uma linha?** (Faça em uma linha).
     7. **Apenas então**: escreva o menor diff funcional possível.
   - Proibido abstrações prematuras (interfaces de 1 implementação, factories para 1 produto, configs de valores imutáveis).
