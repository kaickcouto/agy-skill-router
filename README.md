# AGY Skill Router 🚀

Roteador dinâmico de habilidades técnicas sob demanda desenvolvido sob medida para o **Google Antigravity (AGY)**.

Projetado para eliminar o consumo excessivo de tokens: mantém **1.312 skills especializadas** repousando no Vault (custo zero de contexto) e injeta cirurgicamente apenas as 1–2 skills necessárias via **Windows Directory Junctions / Symlinks (0ms)**, com auto-limpeza após cada tarefa.

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
                       │       SKILLS VAULT           │
                       │    (1.312 skills em repouso) │
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
    │  └── [PINNED]   tailwind-patterns/ ────► (Junction fixada)      │
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

- **Economia Máxima de Contexto (99.85%)**: As 1.312 skills ficam no vault. O contexto do agente recebe apenas as instruções exatas da demanda em execução.
- **Pré-Agente Multimodal Gratuito (OpenRouter)**: Decompõe demandas brutas, informais ou prints de interface em escopo, contrato e checklist cirúrgicos usando modelos gratuitos em cascata (`inclusionai/ling-3.0-flash-vl:free`, `nex-agi/nex-n2.5-mini:free`) antes de acionar o modelo principal.
- **Expansão Semântica Automática de Query**: Se o BM25 receber uma solicitação com score abaixo do limiar (`< 4.0`), consulta silenciosamente a IA gratuita para deduzir termos técnicos ocultos, elevando a precisão de busca sem custo de tokens pagos.
- **Motor BM25 Puro + Bundles**: Busca lexical de precisão com expansão de sinônimos, suporte a combos multi-skill e latência inferior a 3ms. Sem dependências externas (`pip install` desnecessário).
- **Montagem Instantânea (0ms)**: Usa Windows Directory Junctions (NTFS) e symlinks. Não duplica arquivos físicos e não requer privilégios de Administrador.
- **Dupla Trava de Coexistência com Projetos Existentes**:
  - **Rastreamento de Sessão (`.router_session.json`)**: O router registra formalmente cada injeção que realiza. Ele só gerencia pastas que ele mesmo montou.
  - **Inspeção de Atributos NTFS (`FILE_ATTRIBUTE_REPARSE_POINT`)**: Pastas físicas pré-existentes são detectadas como `[NATIVA/LOCAL]` e **nunca são deletadas ou sobrescritas**.
  - **Remoção Segura via `os.rmdir`**: Junções no Windows são desfeitas usando `os.rmdir` (API Win32 `RemoveDirectory`), garantindo que o diretório de destino original nunca seja afetado.
- **Isolamento de Workspace no Servidor MCP (`scoped_workspace`)**:
  - As requisições direcionadas a projetos externos utilizam context manager `try...finally`. O estado global do workspace é revertido após cada chamada, impedindo conflitos em sessões concorrentes.
- **Hook de Ciclo de Vida do AGY (`PreInvocation` + `Stop`)**:
  - Intercepta automaticamente o *Submit* do usuário para injetar o plano técnico e as Junctions antes do agente começar a responder, com limpeza automática no término.
- **Proteção Estrita Contra Path Traversal**:
  - O endpoint de MCP Resources (`skills://active/` e `skills://vault/`) sanitiza identificadores e valida se o caminho final está contido no diretório permitido (`.is_relative_to()`).
- **Análise de Segurança via AST (`SecurityASTVisitor`)**:
  - A triagem de código das skills inspeciona nós sintáticos do Python (`ast.NodeVisitor`), eliminando falsos positivos em comentários ou strings de markdown.
- **Regras Centralizadas (`rules.json`)**:
  - Dicionário único para listas de permissão (*whitelist*), expressões regulares de bloqueio, sinônimos, combos e presets.
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
| `route_skills(task, workspace_dir?)` | Roteia e monta via junction as 1–2 skills ideais para a demanda. |
| `apply_preset(preset_name, workspace_dir?)` | Ativa e fixa um perfil completo (`cms`, `fullstack`, `qa`). |
| `list_skills(workspace_dir?)` | Lista skills ativas marcando `[PINNED]`, `[ROUTER-JUNCTION]` e `[NATIVA/LOCAL]`. |
| `reset_skills(force?, workspace_dir?)` | Remove junções temporárias mantendo skills fixadas e nativas. |
| `pin_skill(skill_id)` | Fixa uma skill permanentemente no workspace. |
| `unpin_skill(skill_id)` | Desafixa e remove a skill. |
| `skill_info(skill_id)` | Retorna metadados, gatilhos e documentação da skill. |
| `search_skills(query)` | Busca semântica e pontuação BM25 sem ativar arquivos. |
| `pre_agent_plan(task, image_path?, auto_route_skills?)` | Decompõe demanda técnica e prints via IA gratuita do OpenRouter e auto-injeta as skills. |

---

## 💻 Uso via Linha de Comando (CLI)

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

## 📊 Benchmark de Eficiência

| Métrica | Com Router | Sem Router (Todas Carregadas) | Ganho |
| :--- | :--- | :--- | :--- |
| **Tokens Consumidos em Repouso** | **0 tokens** | ~1.836.800 tokens | **99.85% de economia** |
| **Tempo de Montagem** | **< 1ms** (NTFS Junction) | N/A (Cópia lenta) | **Instantâneo** |
| **Latência de Decisão (BM25)** | **~2.5ms** | N/A | **Tempo real** |
| **Uso de Memória / Disco** | **0 bytes duplicados** | ~150 MB por projeto | **100% deduplicado** |
