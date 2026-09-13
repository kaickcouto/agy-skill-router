import sys
import os
import json
from pathlib import Path

# Suporte a UTF-8 no Windows
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

ROOT = Path(__file__).resolve().parent.parent
HOME = Path.home()
MCP_CONFIG_PATH = HOME / ".gemini" / "config" / "mcp_config.json"
SERVER_SCRIPT = ROOT / "scripts" / "mcp_server.py"
AUTO_ROUTE_SCRIPT = ROOT / "scripts" / "auto_route.py"
GLOBAL_HOOKS_JSON = HOME / ".gemini" / "config" / "hooks.json"
GLOBAL_GEMINI_MD = HOME / ".gemini" / "config" / "GEMINI.md"
HOOKS_JSON = ROOT / ".agent" / "hooks.json"
HOOK_STOP_SCRIPT = ROOT / "scripts" / "hook_stop.py"
HOOK_PRE_INVOCATION_SCRIPT = ROOT / "scripts" / "hook_pre_invocation.py"

def setup():
    print("=" * 65)
    print("  🤖 INSTALADOR NATIVO GOOGLE ANTIGRAVITY (AGY)")
    print("=" * 65)

    # 1. Configurar MCP Global com interpretador absoluto
    MCP_CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    config = {}
    if MCP_CONFIG_PATH.exists():
        try:
            with open(MCP_CONFIG_PATH, "r", encoding="utf-8") as f:
                config = json.load(f)
        except Exception:
            config = {}

    servers = config.setdefault("mcpServers", {})
    servers["agy-skill-router"] = {
        "command": sys.executable,
        "args": [str(SERVER_SCRIPT.resolve())]
    }

    try:
        with open(MCP_CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=2)
        print(f"[OK] MCP Server registrado em: {MCP_CONFIG_PATH}")
    except Exception as e:
        print(f"[!] Erro ao atualizar mcp_config.json: {e}")

    # 2. Configurar Hooks Nativos do AGY ('Stop' e 'PreInvocation') com caminhos absolutos
    HOOKS_JSON.parent.mkdir(parents=True, exist_ok=True)
    hook_cleanup = f'"{sys.executable}" "{HOOK_STOP_SCRIPT.resolve()}"'
    hook_pre_agent = f'"{sys.executable}" "{HOOK_PRE_INVOCATION_SCRIPT.resolve()}"'
    hooks_data = {
        "agy-skill-cleanup": {
            "Stop": [
                {
                    "type": "command",
                    "command": hook_cleanup
                }
            ]
        },
        "agy-pre-agent": {
            "PreInvocation": [
                {
                    "type": "command",
                    "command": hook_pre_agent
                }
            ]
        }
    }
    
    # Salva no workspace local
    with open(HOOKS_JSON, "w", encoding="utf-8") as f:
        json.dump(hooks_data, f, indent=2)
    print(f"[OK] Hooks nativos locais configurados em: {HOOKS_JSON}")

    # Salva nos hooks globais do Antigravity (~/.gemini/config/hooks.json)
    try:
        GLOBAL_HOOKS_JSON.parent.mkdir(parents=True, exist_ok=True)
        with open(GLOBAL_HOOKS_JSON, "w", encoding="utf-8") as f:
            json.dump(hooks_data, f, indent=2)
        print(f"[OK] Hooks nativos globais configurados em: {GLOBAL_HOOKS_JSON}")
    except Exception as e:
        print(f"[!] Erro ao atualizar hooks globais: {e}")

    # 3. Sincronizar GEMINI.md Global com diretrizes do Skill Router
    try:
        if GLOBAL_GEMINI_MD.exists():
            content = GLOBAL_GEMINI_MD.read_text(encoding="utf-8", errors="ignore")
            if "AGY Skill Router Protocol" not in content and "route_skills" not in content:
                router_rules = (
                    "\n\n## AGY Skill Router Protocol\n"
                    "- **Roteamento de Demanda Técnica Especializada**:\n"
                    "  - Antes de iniciar qualquer tarefa técnica especializada (Supabase, Postgres, Tailwind, Testes E2E, Docker, Excel/PDF, APIs, etc.), chame a tool MCP `route_skills(task='...')` ou aplique o preset via `apply_preset(preset_name=...)`.\n"
                    "  - Para demandas complexas multi-stack, passe `top_k=3` a `5`.\n"
                    "  - Ao finalizar a implementação de uma demanda técnica ou antes de trocar de contexto, chame `reset_skills()`.\n"
                )
                GLOBAL_GEMINI_MD.write_text(content.rstrip() + router_rules, encoding="utf-8")
                print(f"[OK] Regras globais do Skill Router sincronizadas em: {GLOBAL_GEMINI_MD}")
            else:
                print(f"[OK] Regras globais em {GLOBAL_GEMINI_MD} já incluem Skill Router.")
    except Exception as e:
        print(f"[!] Erro ao atualizar GEMINI.md global: {e}")

    # 3. Configurar Git Hooks
    sys.path.insert(0, str(ROOT / "scripts"))
    import install_hooks
    install_hooks.install()

    # 4. Pré-aquecer motor BM25
    import auto_route
    idx = auto_route.get_index()
    print(f"[OK] Motor BM25 aquecido ({len(idx.manifest)} skills indexadas).")

    print("\n" + "=" * 65)
    print("  ✅ ANTIGRAVITY CONFIGURADO E PRONTO PARA OPERAÇÃO!")
    print("=" * 65 + "\n")

if __name__ == "__main__":
    setup()
