# AGY Skill Router 🚀

Roteador dinâmico de habilidades técnicas sob demanda desenvolvido sob medida para o **Google Antigravity (AGY)**.

Projetado para eliminar o consumo excessivo de tokens: mantém **1.314+ skills especializadas** repousando no Vault e Custom (custo zero de contexto) e injeta cirurgicamente apenas as 1–2 skills necessárias via **Windows Directory Junctions / Symlinks (0ms)**, com auto-limpeza após cada tarefa.

---

```text
                       ┌──────────────────────────────┐
                       │        USER PROMPT           │
                       └──────────────┬───────────────┘
                                      │
                        [BM25 + Presets + Bundles]
                                      │ (< 3ms)
                                      ▼
                       ┌──────────────────────────────┐
                       │   SKILLS VAULT & CUSTOM      │
                       │ (1.314+ skills em repouso)   │
                       └──────────────┬───────────────┘
                                      │
                         [NTFS Junction / Symlink]
                                      │ (0ms, 0 bytes)
                                      ▼
    ┌─────────────────────────────────────────────────────────────────┐
    │                    SEU PROJETO / CMS (.agent/)                  │
    │                                                                 │
    │  .agent/skills/                                                 │
    │  ├── [NATIVA]   minhas-skills-locais/  (NUNCA DELETADAS)        │
    │  ├── [ROUTER]   supabase-postgres/ ────► (Junction temporária)  │
    │  ├── [PINNED]   tailwind-patterns/ ────► (Junction fixada)      │
    │  └── [CUSTOM]   taste-skill, tdd/  ────► (Junction prioritária) │
    │                                                                 │
    │  .agent/.router_session.json ──► (Rastreio de Posse da Sessão) │
    └─────────────────────────────────┬───────────────────────────────┘
                                      │
                         [AGY Execution & Tools]
                                      │
                         [Hook Stop / Git Post-Commit]
                                      ▼
                                Auto-Reset
                   (Apenas as junções temporárias saem;
                    skills nativas permanecem intocadas)
```

---

## ⚡ Principais Recursos & Blindagem de Engenharia

- **Economia Máxima de Contexto (99.85%)**: As 1.314+ skills ficam em repouso. O contexto do agente recebe apenas as instruções exatas da demanda em execução.
- **Skills de Engenharia Ouro (Matt Pocock & Anti-Slop)**:
  - `taste-skill`: Design frontend moderno anti-slop, micro-interações refinadas e leitura de contexto de UI.
  - `ponytail`: Mindset sênior pragmático e YAGNI (menor diff funcional possível).
  - `codebase-design`: Arquitetura de módulos profundos (*deep modules*), costuras limpas (*seams*) e desacoplamento.
  - `tdd`: Ciclo rigoroso *Red-Green-Refactor* sem testes tautológicos ou mocks excessivos.
  - `diagnosing-bugs`: Isolamento de bugs com reprodução mínima (MRE) e redação estrita de segredos (`<REDACTED>`).
- **Ciclo de Vida Completo de Skills (`init`, `lint`, `import`)**:
  - Scaffolding de novas skills (`init`), auditoria estática rigorosa de tokens/YAML (`lint`) e importação direta do GitHub (`import`).
- **Git-Aware Context Routing (estilo Aider)**: Inspeciona silenciosamente o `git status` do workspace ativo para inferir o contexto das tecnologias modificadas quando a solicitação do usuário for curta ou vaga.
- **Path-Triggered Context (estilo Cursor)**: Mapeamento de arquivos e extensões mencionadas no prompt (ex: `migrations.sql`, `routes.py`, `App.tsx`, `Dockerfile`) para acionamento instantâneo das skills especializadas correspondentes.
- **Two-Tier Domain Classification**: Classificação prévia por blocos temáticos (`database`, `backend`, `frontend`, `testing`, `data-ai`) que isola o espaço de busca, eliminando totalmente ruídos e falsos positivos cruzados.
- **Skill Co-occurrence & Affinity Matrix**: Priorização contextual inteligente de skills irmãs (ex: ao ativar `python-fastapi-development`, prioriza automaticamente `api-designer`).
- **Binary Index Cache (`.agent/index_cache.pkl`)**: Serialização binária pré-compilada do índice BM25 com invalidação instantânea profunda baseada em `mtime` dos arquivos `SKILL.md`.
- **Protocolo MCP Totalmente Conforme**: Handshake com suporte formal a `listChanged` e ferramentas expostas para o Antigravity.
- **Pré-Agente Multimodal Gratuito (OpenRouter)**: Decompõe demandas brutas, informais ou prints de interface em escopo, contrato e checklist cirúrgicos usando modelos gratuitos em cascata (`inclusionai/ling-3.0-flash-vl:free`, `nex-agi/nex-n2.5-mini:free`) antes de acionar o modelo principal.
- **Suíte Completa de Testes Automatizados (28/28)**: Testes de regressão cobrindo roteamento, bundles, hooks nativos, path-triggers, cache binário, importação, scaffolding e conformidade MCP em [tests/test_router.py](tests/test_router.py).
- **Diagnóstico 1-Clique (`scripts/doctor.py`)**: Validação de 7 pilares de integridade técnica em milissegundos.

---

## 🛠️ Instalação Rápida (1-Clique)

### Requisitos:
- Python 3.10+ (apenas biblioteca padrão).
- Windows, Linux ou macOS.

### Passo a Passo:
```bash
# 1. Clone o repositório
git clone https://github.com/kaickcouto/agy-skill-router.git
cd agy-skill-router

# 2. Configuração Automática para o Google Antigravity (AGY)
python scripts/setup_agy.py

# 3. Validar Diagnóstico de Saúde
python scripts/doctor.py
```

---

## 🔌 Configuração MCP no Antigravity

O script `scripts/setup_agy.py` registra o servidor automaticamente no arquivo global do Antigravity (`~/.gemini/config/mcp_config.json`). Caso queira verificar ou configurar manualmente:

```json
{
  "mcpServers": {
    "agy-skill-router": {
      "command": "python",
      "args": [
        "C:\\Users\\SEU_USUARIO\\caminho\\para\\agy-skill-router\\scripts\\mcp_server.py"
      ]
    }
  }
}
```

### Ferramentas Expostas pelo MCP:
| Ferramenta | Descrição |
| :--- | :--- |
| `route_skills(task, top_k?, block?, workspace_dir?)` | Roteia e monta via junction as 1–2 skills ideais para a demanda. |
| `pre_agent_plan(task, image_path?, auto_route_skills?, top_k?, workspace_dir?)` | Decompõe demanda técnica e prints via IA gratuita do OpenRouter e auto-injeta as skills. |
| `lint_skill(skill_id)` | Inspeciona e audita uma skill técnica, validando frontmatter YAML, tamanho e ausência de tells de IA. |
| `apply_preset(preset_name, workspace_dir?)` | Ativa e fixa um perfil completo (`cms`, `fullstack`, `qa`). |
| `list_skills(workspace_dir?)` | Lista skills ativas marcando `[PINNED]`, `[ROUTER-JUNCTION]` e `[NATIVA/LOCAL]`. |
| `reset_skills(force?, workspace_dir?)` | Remove junções temporárias mantendo skills fixadas e nativas. |
| `pin_skill(skill_id, workspace_dir?)` | Fixa uma skill permanentemente no workspace. |
| `unpin_skill(skill_id, workspace_dir?)` | Desafixa e remove a skill. |
| `skill_info(skill_id)` | Retorna metadados, gatilhos e documentação da skill. |
| `search_skills(query, top_k?, block?)` | Busca semântica e pontuação BM25 sem ativar arquivos. |

---

## 💻 Uso via Linha de Comando (CLI)

### 0. Gerenciamento & Ciclo de Vida de Skills (Novo!)
```bash
# Inicializar uma nova skill técnica com diretrizes Ponytail/Anti-Slop:
python scripts/auto_route.py init "minha-nova-skill" "Descrição concisa dos padrões técnicos"

# Auditar e validar a qualidade/orçamento de tokens de uma skill:
python scripts/auto_route.py lint "taste-skill"

# Importar diretamente uma skill do GitHub (ex: Matt Pocock, Vercel Labs):
python scripts/auto_route.py import "mattpocock/skills@skills/engineering/codebase-design"
```

### 0. Pré-Agente & Decomposição Gratuita (OpenRouter)
```bash
# Decompor a demanda em plano cirúrgico e auto-injetar as skills (-r):
python scripts/pre_agent.py "criar tabela de pedidos no supabase com trigger de updated_at" -r

# Modo Multimodal (análise de prints/mockups sem custo de tokens pagos):
python scripts/pre_agent.py "recriar esta tela de checkout" -i "mockups/checkout.png" -r

# Roteamento + Planejamento unificado direto pelo auto_route:
python scripts/auto_route.py "fazer deploy no vercel com nextjs e tailwind" --plan
```

### 1. Roteamento por Demanda
```bash
# Roteamento padrão (com resgate por expansão semântica automática se score < 4.0)
python scripts/auto_route.py "criar migration e tabela com RLS no supabase"

# Explicar scores e triggers selecionados
python scripts/auto_route.py "criar formulário de orçamentos devis em pdf e excel" --explain

# Roteamento direcionado a outro projeto (ex: seu CMS)
python scripts/auto_route.py "validar schemas zod" --workspace "C:\caminho\para\CMS"
```

### 2. Presets e Fixação (Pinning)
```bash
# Aplicar perfil base do CMS (Supabase + Tailwind fixados)
python scripts/auto_route.py preset cms

# Fixar uma skill manualmente
python scripts/auto_route.py pin supabase-postgres-best-practices

# Desafixar
python scripts/auto_route.py unpin supabase-postgres-best-practices
```

### 3. Diagnóstico e Limpeza
```bash
# Ver status das skills ativas e origem de montagem
python scripts/auto_route.py status

# Limpar skills temporárias (preserva fixadas e nativas)
python scripts/auto_route.py reset

# Limpeza forçada (remove inclusive fixadas, mantendo nativas físicas)
python scripts/auto_route.py reset --force

# Executar diagnóstico do sistema
python scripts/doctor.py
```

---

## 🎯 Coexistência e Preservação em Projetos Externos

Quando utilizado em projetos que já possuem ferramentas e skills (como seu CMS):

1. **Precedência de Escopo**:
   - `skills_custom/` do projeto alvo > `skills_custom/` do router > `skills_vault/`.
2. **Proteção Física & Posse**:
   - Pastas reais em `.agent/skills/` que não constam no `.router_session.json` são classificadas como `[NATIVA/LOCAL]` e são **completamente ignoradas em qualquer operação de reset**.
3. **Privacidade e Isolamento Git**:
   - `.agent/hooks.json` é ignorado localmente e gerado por template neutro ([.agent/hooks.json.example](file:///c:/Users/Sadan/Documents/agy-skill-router/.agent/hooks.json.example)).
   - As junctions são ignoradas pelo Git (`.agent/skills/*`), evitando que arquivos do vault poluam o versionamento do projeto.

---

## 📂 Estrutura do Repositório

```text
agy-skill-router/
├── .agent/
│   ├── hooks.json.example     # Template neutro do Hook nativo 'Stop' do AGY
│   ├── .router_session.json   # Registro de posse da sessão ativa (ignorado no git)
│   └── skills/                # Ponto de montagem ativo (junctions locais)
├── skills_vault/              # 1.312 skills especializadas indexadas
├── skills_custom/             # Suas skills personalizadas / prioritárias
├── scripts/
│   ├── auto_route.py          # Motor BM25, Expansão Semântica e interface CLI
│   ├── pre_agent.py           # Pré-Agente Multimodal gratuito via OpenRouter
│   ├── hook_pre_invocation.py # Hook nativo AGY PreInvocation (interceptação no Submit)
│   ├── manage_skills.py       # Gestor NTFS (Junctions, Coexistência, Pins, Session)
│   ├── mcp_server.py          # Servidor MCP stdio com tool pre_agent_plan
│   ├── doctor.py              # Diagnóstico de integridade e saúde
│   ├── setup_agy.py           # Instalador 1-clique com registro de hooks e MCP
│   ├── install_hooks.py       # Instalador dinâmico de Git Hooks
│   ├── benchmark.py           # Suíte de avaliação de precisão e latência
│   ├── setup_skills.py        # Validador AST e sanitizador de código
│   ├── audit_quality.py       # Auditor de qualidade integrado com rules.json
│   └── classify_skills.py     # Classificador e extrator delimitado de gatilhos
├── rules.json                 # Regras unificadas (filtros, sinônimos, combos e presets)
├── skills_manifest.json       # Catálogo taxonômico com metadados e triggers
├── GEMINI.md                  # Protocolo de contexto e diretrizes do agente AGY
└── README.md                  # Documentação oficial
```

---

## 📊 Benchmark Crítico de Engenharia & Auditoria de Tokens

Bateria rigorosa de **30 casos de teste reais** divididos em 4 tiers de dificuldade (*Direct, Informal, Adversarial, NegativeTrap*), auditando o consumo de tokens contra o baseline real do catálogo do System Prompt.

### 1. Precisão do Roteador (30 Casos de Teste)
| Métrica | Resultado | Descrição |
| :--- | :--- | :--- |
| **Acurácia Global** | **100.0% (30/30)** | Cobertura total em tarefas diretas, gírias, multi-stack e armadilhas |
| **Precisão Técnica** | **100.0%** | Zero ativações erradas em demandas de código |
| **Taxa de Falso-Positivo** | **0.0% (0/9)** | Nenhuma skill vazada em perguntas casuais/conversacionais (Tier 4) |
| **Taxa de Falso-Negativo** | **0.0% (0/21)** | Nenhuma omissão de skill quando o contexto técnico exige |
| **F1-Score** | **100.0%** | Equilíbrio harmônico entre sensibilidade e contenção |
| **Latência BM25 (p50 / p95 / p99)** | **2.68ms / 4.22ms / 4.59ms** | Roteamento em tempo real sem sobrecarga perceptível |

### 2. Auditoria Realista: Jornada Diária de 50 Turnos de Codificação
> [!NOTE]
> O baseline realista calcula o custo do catálogo das 1.312 skills (196.344 tokens) que seriam repetidamente injetados no System Prompt a cada mensagem sem o roteador dinâmico.

| Métrica | Sem Router (Catálogo Fixo) | Com AGY Skill Router | Economia Real Líquida |
| :--- | :--- | :--- | :--- |
| **Overhead no System Prompt** | **196.344 tokens** / mensagem | **0 tokens** (skills residem em disco) | **100% livre** |
| **Injeção Ativa por Tarefa** | 196.344 tokens | **~5.943 tokens** (apenas na demanda ativa) | **97.0% menos tokens** |
| **Consumo Total (50 turnos)** | **9.817.200 tokens** | **190.178 tokens** | **9.627.022 tokens poupados (98.1%)** |
| **Custo na Sessão (Claude 3.5 Sonnet)**| **$29.45 USD** (~R$ 169.35) | **$0.57 USD** (~R$ 3.28) | **-$28.88 USD** (~R$ 166.07) |
| **Custo na Sessão (OpenAI GPT-4o)** | **$24.54 USD** (~R$ 141.10) | **$0.47 USD** (~R$ 2.70) | **-$24.07 USD** (~R$ 138.39) |
| **Viabilidade em Janela de 128k** | ❌ **ESTOURO FATAL** (196k > 128k) | ✅ **97.2% livre** para arquivos do projeto | **Permite usar modelos com janelas menores** |
| **Tempo de Montagem (Junctions)** | N/A | **< 1ms** (Windows NTFS Junction) | **0ms de overhead de I/O** |
| **Decomposição Gratuita (OpenRouter)** | 0 (modelo pago processa tudo) | **~1.200 tokens** poupados no modelo pago | **Raciocínio preliminar a custo zero** |

