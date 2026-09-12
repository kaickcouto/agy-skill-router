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

def setup():
    print("=" * 65)
    print("  🤖 INSTALADOR DE INTEGRAÇÃO NATIVA GOOGLE ANTIGRAVITY (AGY)")
    print("=" * 65)

    # 1. Configurar MCP Global
    if MCP_CONFIG_PATH.exists():
        try:
            with open(MCP_CONFIG_PATH, "r", encoding="utf-8") as f:
                config = json.load(f)
            
            servers = config.setdefault("mcpServers", {})
            servers["agy-skill-router"] = {
                "command": "python",
                "args": [str(SERVER_SCRIPT.resolve())]
            }

            with open(MCP_CONFIG_PATH, "w", encoding="utf-8") as f:
                json.dump(config, f, indent=2)
            print("[OK] MCP Server 'agy-skill-router' registrado globalmente no AGY.")
        except Exception as e:
            print(f"[!] Erro ao atualizar mcp_config.json: {e}")
    else:
        print(f"[!] mcp_config.json não encontrado em {MCP_CONFIG_PATH}")

    # 2. Configurar Git Hooks
    sys.path.insert(0, str(ROOT / "scripts"))
    import install_hooks
    install_hooks.install()

    # 3. Pré-aquecer Cache BM25
    import auto_route
    idx = auto_route.get_index()
    print(f"[OK] Cache de busca BM25 compilado ({len(idx.manifest)} skills indexadas).")

    print("\n" + "=" * 65)
    print("  ✅ ANTIGRAVITY (AGY) 100% CONFIGURADO E PRONTO PARA USO!")
    print("=" * 65 + "\n")

if __name__ == "__main__":
    setup()
