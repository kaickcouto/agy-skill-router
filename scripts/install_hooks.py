import sys
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HOOKS_DIR = ROOT / ".git" / "hooks"

POST_COMMIT_SH = """#!/bin/sh
# AGY Skill Router - Auto-Reset Hook
python scripts/auto_route.py reset > /dev/null 2>&1 || true
"""

POST_COMMIT_BAT = """@echo off
REM AGY Skill Router - Auto-Reset Hook
python scripts\\auto_route.py reset >nul 2>&1
"""

def install():
    if not HOOKS_DIR.exists():
        print("[!] Diretório .git/hooks não encontrado. Este repositório é um clone Git?")
        sys.exit(1)

    # 1. Hook bash/sh padrão (Git Bash / Linux / macOS)
    sh_path = HOOKS_DIR / "post-commit"
    sh_path.write_text(POST_COMMIT_SH, encoding="utf-8")
    try:
        sh_path.chmod(0o755)
    except Exception:
        pass

    # 2. Hook Windows CMD
    bat_path = HOOKS_DIR / "post-commit.cmd"
    bat_path.write_text(POST_COMMIT_BAT, encoding="utf-8")

    print("[OK] Git hooks instalados com sucesso em .git/hooks/post-commit!")
    print("[*] Toda vez que um commit for concluído, as skills ativas serão automaticamente limpas (reset).")

if __name__ == "__main__":
    install()
