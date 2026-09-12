# AGY Skill Router 🚀

Roteador dinâmico de skills com economia cirúrgica de tokens para agentes de IA (Antigravity, Claude Desktop, Cursor e outros).

Mantém centenas de skills técnicas descansando no **Vault** (custo zero de contexto) e injeta via **Windows Directory Junctions / Symlinks** apenas as 1–2 skills especializadas necessárias para a tarefa atual, limpando-as automaticamente no reset.

---

## ⚡ Diferenciais de Performance

- **Zero Custo de Contexto em Repouso**: Skills em `skills_vault/` não consomem nenhum token de prompt de sistema.
- **Roteador BM25 Puro + Cache Binário**: Busca lexical de alta precisão com expansão de sinônimos e resposta em `< 5ms`.
- **Windows Junctions Nativos**: Ativação instantânea (0ms) sem duplicar arquivos físicos no disco e sem requerer privilégios de Administrador.
- **Bundles Coordenados**: Detecção automática de combos técnicos multi-skill (ex: Fullstack Supabase, Relatórios Excel/PDF, Suíte E2E).
- **Pinning de Skills**: Trava skills essenciais do projeto (como Supabase ou Design System) permanentemente ativas.
- **Servidor MCP Nativo (JSON-RPC 2.0)**: Comunicação direta por stdio para qualquer agente/IDE moderno.

---

## 🛠️ Instalação e Requisitos

- Python 3.10+ (apenas biblioteca padrão, **zero dependências externas pip**).
- Windows, Linux ou macOS.

```bash
git clone https://github.com/kaickcouto/agy-skill-router.git
cd agy-skill-router

# Gera o manifesto e audita a integridade do vault
python scripts/setup_skills.py
```

---

## 🔌 Configuração MCP (Model Context Protocol)

Adicione ao arquivo de configuração MCP do seu cliente (`antigravity.json`, `claude_desktop_config.json` ou Cursor):

```json
{
  "mcpServers": {
    "agy-skill-router": {
      "command": "python",
      "args": [
        "C:\\Users\\Sadan\\Documents\\agy-skill-router\\scripts\\mcp_server.py"
      ]
    }
  }
}
```

### Ferramentas Expostas pelo MCP:
- `route_skills(task, top_k=2, block=null)`: Analisa a tarefa, remove skills anteriores e ativa as ideais.
- `list_skills()`: Lista skills atualmente ativas e fixadas em `.agent/skills/`.
- `reset_skills(force=false)`: Remove skills ativas restaurando o workspace base.
- `search_skills(query, top_k=5, block=null)`: Pesquisa no vault sem ativar.
- `pin_skill(skill_id)`: Fixa uma skill permanente no workspace.
- `unpin_skill(skill_id)`: Desafixa e remove uma skill.

---

## 💻 Uso via Linha de Comando (CLI)

### 1. Roteamento Dinâmico por Tarefa
```bash
# Roteia e ativa as melhores skills para o prompt
python scripts/auto_route.py "criar migration e tabela com RLS no supabase"

# Exibe explicação detalhada e pontuação BM25
python scripts/auto_route.py "fazer testes e2e com playwright" --explain

# Filtrar por bloco temático
python scripts/auto_route.py "otimizar queries sql" --block core-database
```

### 2. Gerenciamento de Fixação (Pinning)
```bash
# Fixar skill para não ser desativada em resets
python scripts/auto_route.py pin supabase-postgres-best-practices

# Desafixar
python scripts/auto_route.py unpin supabase-postgres-best-practices
```

### 3. Reset Manual e Status
```bash
python scripts/auto_route.py status
python scripts/auto_route.py reset
```

---

## 📂 Estrutura do Repositório

```text
agy-skill-router/
├── .agent/
│   └── skills/                # Ponto de montagem (junctions/symlinks ativos)
├── skills_vault/              # +1.300 skills técnicas catalogadas
├── scripts/
│   ├── auto_route.py          # Motor BM25 + Bundles + CLI
│   ├── manage_skills.py       # Gestor de junctions, pinning e links
│   ├── mcp_server.py          # Servidor MCP stdio JSON-RPC 2.0
│   ├── setup_skills.py        # Sanitização e geração do manifesto
│   └── jury_classifier.py     # Classificador Tri-Mind (Advogado, Crítico, Juiz)
├── skills_manifest.json       # Índice estruturado com blocos e metadados
└── README.md
```
