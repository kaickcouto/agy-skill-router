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
HOOKS_JSON = ROOT / ".agent" / "hooks.json"

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

    # 2. Configurar Hook Nativo 'Stop' do AGY com caminhos absolutos
    HOOKS_JSON.parent.mkdir(parents=True, exist_ok=True)
    hook_command = f'"{sys.executable}" "{AUTO_ROUTE_SCRIPT.resolve()}" reset'
    hooks_data = {
        "agy-skill-cleanup": {
            "Stop": [
                {
                    "type": "command",
                    "command": hook_command
                }
            ]
        }
    }
    with open(HOOKS_JSON, "w", encoding="utf-8") as f:
        json.dump(hooks_data, f, indent=2)
    print(f"[OK] Hook nativo do AGY configurado com caminho absoluto em: {HOOKS_JSON}")

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
