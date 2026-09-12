import sys
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HOOKS_DIR = ROOT / ".git" / "hooks"

def install():
    if not HOOKS_DIR.exists():
        print("[!] Diretório .git/hooks não encontrado. Este repositório é um clone Git?")
        sys.exit(1)

    py_exe = sys.executable
    auto_route_script = (ROOT / "scripts" / "auto_route.py").resolve()

    py_cmd_sh = py_exe.replace("\\", "/")
    auto_route_sh = str(auto_route_script).replace("\\", "/")
    auto_route_bat = str(auto_route_script)

    post_commit_sh = f"""#!/bin/sh
# AGY Skill Router - Auto-Reset Hook
if [ -x "{py_cmd_sh}" ]; then
    "{py_cmd_sh}" "{auto_route_sh}" reset > /dev/null 2>&1 || true
else
    python3 "{auto_route_sh}" reset > /dev/null 2>&1 || python "{auto_route_sh}" reset > /dev/null 2>&1 || true
fi
"""

    post_commit_bat = f"""@echo off
REM AGY Skill Router - Auto-Reset Hook
if exist "{py_exe}" (
    "{py_exe}" "{auto_route_bat}" reset >nul 2>&1
) else (
    python "{auto_route_bat}" reset >nul 2>&1
)
"""

    # 1. Hook bash/sh padrão (Git Bash / Linux / macOS)
    sh_path = HOOKS_DIR / "post-commit"
    sh_path.write_text(post_commit_sh, encoding="utf-8")
    try:
        sh_path.chmod(0o755)
    except Exception:
        pass

    # 2. Hook Windows CMD
    bat_path = HOOKS_DIR / "post-commit.cmd"
    bat_path.write_text(post_commit_bat, encoding="utf-8")

    print("[OK] Git hooks instalados com sucesso em .git/hooks/post-commit!")
    print("[*] Toda vez que um commit for concluído, as skills ativas serão automaticamente limpas (reset).")

if __name__ == "__main__":
    install()
