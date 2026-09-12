import sys
import os
import time
import json
from pathlib import Path

# Suporte UTF-8 no Windows
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

ROOT = Path(__file__).resolve().parent.parent
HOME = Path.home()
MCP_CONFIG = HOME / ".gemini" / "config" / "mcp_config.json"
MANIFEST = ROOT / "skills_manifest.json"
RULES = ROOT / "rules.json"
HOOK = ROOT / ".git" / "hooks" / "post-commit"

def check(title: str, condition: bool, detail: str = "") -> bool:
    icon = "✅ [OK]" if condition else "❌ [ERRO]"
    print(f" {icon} {title:<45} {detail}")
    return condition

def run_doctor():
    print("=" * 70)
    print("  🩺 DIAGNÓSTICO DE SAÚDE & PRONTIDÃO (AGY-SKILL-ROUTER)")
    print("=" * 70)

    results = []

    # 1. Python Version
    py_ok = sys.version_info >= (3, 10)
    v_str = f"v{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    results.append(check("Interpretador Python (>= 3.10)", py_ok, f"({v_str})"))

    # 2. Windows Directory Junction Support
    junction_ok = False
    temp_src = ROOT / "_temp_doc_src"
    temp_dst = ROOT / "_temp_doc_dst"
    try:
        temp_src.mkdir(parents=True, exist_ok=True)
        if sys.platform == "win32":
            import _winapi
            _winapi.CreateJunction(str(temp_src.resolve()), str(temp_dst.absolute()))
            junction_ok = temp_dst.exists()
            os.unlink(str(temp_dst.absolute()))
        else:
            os.symlink(temp_src, temp_dst, target_is_directory=True)
            junction_ok = temp_dst.exists()
            os.unlink(str(temp_dst.absolute()))
    except Exception as e:
        junction_ok = False
    finally:
        if temp_src.exists():
            temp_src.rmdir()
    results.append(check("Windows Directory Junctions (0ms Link)", junction_ok, "(Suporte Nativo NTFS)"))

    # 3. Global AGY MCP Registration
    mcp_ok = False
    mcp_detail = "Não registrado"
    if MCP_CONFIG.exists():
        try:
            with open(MCP_CONFIG, "r", encoding="utf-8") as f:
                data = json.load(f)
            servers = data.get("mcpServers", {})
            if "agy-skill-router" in servers:
                mcp_ok = True
                mcp_detail = "Registrado em mcp_config.json"
        except Exception:
            pass
    results.append(check("Servidor MCP Global no AGY", mcp_ok, f"({mcp_detail})"))

    # 4. Skills Vault Integrity
    vault_ok = False
    skill_count = 0
    if MANIFEST.exists():
        try:
            with open(MANIFEST, "r", encoding="utf-8") as f:
                m_data = json.load(f)
            skill_count = len(m_data)
            vault_ok = skill_count >= 1300
        except Exception:
            pass
    results.append(check("Skills Vault & Manifesto", vault_ok, f"({skill_count} skills indexadas)"))

    # 5. Rules, Presets & Module Hints
    rules_ok = False
    presets_count = 0
    modules_count = 0
    if RULES.exists():
        try:
            with open(RULES, "r", encoding="utf-8") as f:
                r_data = json.load(f)
            presets_count = len(r_data.get("presets", {}))
            modules_count = len(r_data.get("module_hints", {}))
            rules_ok = presets_count > 0 and modules_count > 0
        except Exception:
            pass
    results.append(check("Regras, Presets CMS & Módulos", rules_ok, f"({presets_count} presets, {modules_count} módulos)"))

    # 6. BM25 Cache & Latency
    sys.path.insert(0, str(ROOT / "scripts"))
    import auto_route
    idx = auto_route.get_index()
    t0 = time.perf_counter()
    scores = idx.score("teste de performance postgres")
    elapsed_ms = (time.perf_counter() - t0) * 1000
    cache_ok = len(scores) > 0 and elapsed_ms < 15
    results.append(check("Motor BM25 & Latência de Busca", cache_ok, f"({elapsed_ms:.2f}ms/query)"))

    # 7. Git Lifecycle Auto-Reset Hook
    hook_ok = HOOK.exists()
    results.append(check("Git Hook de Auto-Reset (post-commit)", hook_ok, "(Ativo em .git/hooks/)"))

    # Summary
    all_ok = all(results)
    print("=" * 70)
    if all_ok:
        print("  🎉 STATUS: 100% OPERACIONAL! TUDO PRONTO PARA O SEU CMS.")
    else:
        print("  ⚠️ STATUS: ATENÇÃO! Alguns componentes necessitam de ajuste.")
    print("=" * 70 + "\n")
    return all_ok

if __name__ == "__main__":
    success = run_doctor()
    sys.exit(0 if success else 1)
