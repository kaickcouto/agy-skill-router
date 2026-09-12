import os
import sys
import json
import shutil
from pathlib import Path

# Suporte a UTF-8 no Windows
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

ROOT = Path(__file__).resolve().parent.parent
VAULT_DIR = ROOT / "skills_vault"
ACTIVE_DIR = ROOT / ".agent" / "skills"
MANIFEST_PATH = ROOT / "skills_manifest.json"
ENV_PATH = ROOT / ".env"

def load_env():
    if ENV_PATH.exists():
        with open(ENV_PATH, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

def get_manifest() -> dict:
    if not MANIFEST_PATH.exists():
        print("[!] Erro: skills_manifest.json ausente. Execute python scripts/setup_skills.py.")
        sys.exit(1)
    with open(MANIFEST_PATH, "r", encoding="utf-8") as f:
        return {item["id"]: item for item in json.load(f)}

def remove_item(path: Path):
    if path.name == ".gitkeep":
        return
    if path.is_symlink() or path.is_file():
        path.unlink()
    elif path.is_dir():
        shutil.rmtree(path, ignore_errors=True)

def add(ids: list[str]) -> list[str]:
    load_env()
    manifest = get_manifest()
    ACTIVE_DIR.mkdir(parents=True, exist_ok=True)
    activated = []

    for sid in ids:
        if sid not in manifest:
            print(f"[!] ID desconhecido no catálogo: '{sid}'")
            continue

        meta = manifest[sid]
        target_name = meta.get("target", sid)
        src = (VAULT_DIR / target_name).resolve()
        dst = ACTIVE_DIR / target_name

        if dst.exists() or dst.is_symlink():
            print(f"[-] Já ativa: {sid}")
            activated.append(sid)
            continue

        if not src.exists():
            print(f"[!] Origem não encontrada no vault: {src}")
            continue

        missing = [v for v in meta.get("required_env", []) if not os.getenv(v)]
        if missing:
            print(f"[X] Bloqueada '{sid}': Faltam variáveis no .env -> {', '.join(missing)}")
            continue

        try:
            os.symlink(src, dst, target_is_directory=src.is_dir())
        except OSError:
            if src.is_dir():
                shutil.copytree(src, dst)
            else:
                shutil.copy2(src, dst)
        print(f"[+] Ativada: {sid}")
        activated.append(sid)
    return activated

def remove(ids: list[str]):
    manifest = get_manifest()
    for sid in ids:
        target_name = manifest.get(sid, {}).get("target", sid)
        dst = ACTIVE_DIR / target_name
        if dst.exists() or dst.is_symlink():
            remove_item(dst)
            print(f"[-] Desativada: {sid}")
        else:
            print(f"[!] Skill inativa: {sid}")

def reset():
    if ACTIVE_DIR.exists():
        for item in ACTIVE_DIR.iterdir():
            if item.name != ".gitkeep":
                remove_item(item)
    print("[OK] Todas as skills ativas foram removidas.")

def list_skills() -> list[str]:
    active = []
    if ACTIVE_DIR.exists():
        active = [item.name for item in ACTIVE_DIR.iterdir() if item.name != ".gitkeep"]

    if not active:
        print("[*] Nenhuma skill ativa no momento.")
        return []
    print("[*] Skills ativas em .agent/skills/:")
    for name in active:
        print(f"  * {name}")
    return active

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Uso: python scripts/manage_skills.py [add|remove|reset|list] [args...]")
        sys.exit(0)

    cmd = sys.argv[1].lower()
    args = sys.argv[2:]

    if cmd == "add":
        add(args)
    elif cmd == "remove":
        remove(args)
    elif cmd == "reset":
        reset()
    elif cmd == "list":
        list_skills()
    else:
        print(f"[!] Comando inválido: {cmd}. Use: add, remove, reset ou list.")
