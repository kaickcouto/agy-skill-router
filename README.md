# AGY Skill Router 🚀

Roteador dinâmico de habilidades técnicas sob demanda para agentes de IA (**Google Antigravity (AGY)**, Claude Desktop, Cursor e outros).

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

## ⚡ Principais Recursos

- **Economia Máxima de Contexto (99.85%)**: As 1.312 skills ficam no vault. O contexto do agente recebe apenas as instruções exatas da demanda em execução.
- **Motor BM25 Puro + Bundles**: Busca lexical de precisão com expansão de sinônimos, suporte a combos multi-skill e latência inferior a 3ms. Sem dependências externas (`pip install` desnecessário).
- **Montagem Instantânea (0ms)**: Usa Windows Directory Junctions (NTFS) e symlinks. Não duplica arquivos físicos e não requer privilégios de Administrador.
- **Coexistência Segura com Projetos Existentes**:
  - Detecta pastas físicas pré-existentes via atributos NTFS (`FILE_ATTRIBUTE_REPARSE_POINT`).
  - **Zero Risco**: O comando `reset` e os hooks **nunca** apagam ou alteram pastas nativas do seu projeto.
  - Blindagem automática de versionamento: adiciona `.agent/skills/*` ao `.gitignore` do projeto alvo.
- **Camada de Customização (`skills_custom/`)**: Suas skills proprietárias ou do projeto têm precedência total sobre as skills do catálogo público.
- **Presets de Módulos & CMS**:
  - Presets instantâneos: `cms`, `fullstack`, `qa`.
  - Mapeamento inteligente de módulos: reconhece automaticamente contextos como `devis`, `ppa`, `faturamento`, `auth`, `relatorios`, etc.
- **Servidor MCP Nativo (JSON-RPC 2.0)**: Comunicação direta por stdio compatível com o protocolo MCP (Tools + Resources `skills://`).
- **Diagnóstico 1-Clique (`scripts/doctor.py`)**: Validação de 7 pilares de prontidão técnica em milissegundos.

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

## 🔌 Configuração MCP (Model Context Protocol)

O script de setup registra o servidor automaticamente no seu `mcp_config.json` global do Antigravity. Caso utilize outro cliente (Claude Desktop, Cursor), adicione manualmente:

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
| `route_skills(task, workspace?)` | Roteia e monta via junction as 1–2 skills ideais para a demanda. |
| `apply_preset(preset_name, workspace?)` | Ativa e fixa um perfil completo (`cms`, `fullstack`, `qa`). |
| `list_skills(workspace?)` | Lista skills ativas marcando status `[PINNED]` e `[NATIVA/LOCAL]`. |
| `reset_skills(force?, workspace?)` | Remove junções temporárias mantendo skills fixadas e nativas. |
| `pin_skill(skill_id, workspace?)` | Fixa uma skill permanentemente no workspace. |
| `unpin_skill(skill_id, workspace?)` | Desafixa e remove a skill. |
| `skill_info(skill_id)` | Retorna metadados, gatilhos e documentação da skill. |
| `search_skills(query)` | Busca semântica e pontuação BM25 sem ativar arquivos. |

---

## 💻 Uso via Linha de Comando (CLI)

### 1. Roteamento por Demanda
```bash
# Roteamento padrão
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
# Ver status das skills ativas
python scripts/auto_route.py status

# Limpar skills temporárias (preserva fixadas e nativas)
python scripts/auto_route.py reset

# Limpeza forçada (remove inclusive fixadas, mantendo nativas físicas)
python scripts/auto_route.py reset --force

# Executar diagnóstico do sistema
python scripts/doctor.py
```

---

## 🎯 Coexistência e Preservação de Projetos

Quando utilizado em projetos que já possuem ferramentas e skills (como seu CMS):

1. **Prioridade de Sobrescrita**:
   - `skills_custom/` do projeto alvo > `skills_custom/` do router > `skills_vault/`.
2. **Proteção Física**:
   - Pastas reais em `.agent/skills/` não são links simbólicos nem reparse points. O motor as marca como `[NATIVA/LOCAL]` e **ignora qualquer ordem de exclusão nelas**.
3. **Isolamento Git**:
   - As junctions são ignoradas pelo Git (`.agent/skills/*`), evitando commits acidentais de arquivos do vault no repositório do seu projeto.

---

## 📂 Estrutura do Repositório

```text
agy-skill-router/
├── .agent/
│   ├── hooks.json             # Hook nativo 'Stop' do AGY para auto-reset
│   └── skills/                # Ponto de montagem ativo (junctions locais)
├── skills_vault/              # 1.312 skills especializadas indexadas
├── skills_custom/             # Suas skills personalizadas / prioritárias
├── scripts/
│   ├── auto_route.py          # Motor BM25, Bundles e interface CLI
│   ├── manage_skills.py       # Gestor NTFS (Junctions, Coexistência, Pins)
│   ├── mcp_server.py          # Servidor MCP stdio (JSON-RPC 2.0)
│   ├── doctor.py              # Diagnóstico de integridade e saúde
│   ├── setup_agy.py           # Instalador 1-clique no Antigravity
│   ├── benchmark.py           # Suíte de avaliação de precisão e latência
│   └── setup_skills.py        # Validador de manifesto e sanitizador
├── rules.json                 # Regras de parada, sinônimos, combos e presets
├── skills_manifest.json       # Catálogo taxonômico com metadados e triggers
├── GEMINI.md                  # Protocolo de contexto e diretrizes do agente AGY
└── README.md                  # Documentação oficial
```

---

## 📊 Benchmark de Eficiência

| Métrica | Com Router | Sem Router (Todas Carregadas) | Ganho |
| :--- | :--- | :--- | :--- |
| **Tokens Consumidos em Repouso** | **0 tokens** | ~650.000 tokens | **99.85% de economia** |
| **Tempo de Montagem** | **< 1ms** (NTFS Junction) | N/A (Cópia lenta) | **Instantâneo** |
| **Latência de Decisão (BM25)** | **~2.8ms** | N/A | **Tempo real** |
| **Uso de Memória / Disco** | **0 bytes duplicados** | ~150 MB por projeto | **100% deduplicado** |
