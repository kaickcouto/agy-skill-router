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
MANIFEST_PATH = ROOT / "skills_manifest.json"
ENV_PATH = ROOT / ".env"

CURRENT_WORKSPACE = None

def set_workspace(path: str | Path = None):
    global CURRENT_WORKSPACE
    if path:
        CURRENT_WORKSPACE = Path(path).resolve()
    else:
        CURRENT_WORKSPACE = None

def get_active_dir() -> Path:
    if CURRENT_WORKSPACE:
        d = CURRENT_WORKSPACE / ".agent" / "skills"
        d.mkdir(parents=True, exist_ok=True)
        return d
    cwd = Path.cwd()
    if (cwd / ".git").exists() and cwd.resolve() != ROOT.resolve():
        d = cwd / ".agent" / "skills"
        d.mkdir(parents=True, exist_ok=True)
        return d
    d = ROOT / ".agent" / "skills"
    d.mkdir(parents=True, exist_ok=True)
    return d

def get_pinned_file() -> Path:
    if CURRENT_WORKSPACE:
        return CURRENT_WORKSPACE / ".agent" / ".pinned.json"
    cwd = Path.cwd()
    if (cwd / ".git").exists() and cwd.resolve() != ROOT.resolve():
        return cwd / ".agent" / ".pinned.json"
    return ROOT / ".agent" / ".pinned.json"

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

def get_pinned() -> set[str]:
    pinned_path = get_pinned_file()
    if pinned_path.exists():
        try:
            with open(pinned_path, "r", encoding="utf-8") as f:
                return set(json.load(f))
        except Exception:
            return set()
    return set()

def save_pinned(pinned: set[str]):
    pinned_path = get_pinned_file()
    pinned_path.parent.mkdir(parents=True, exist_ok=True)
    with open(pinned_path, "w", encoding="utf-8") as f:
        json.dump(sorted(list(pinned)), f, indent=2)

def pin(ids: list[str]):
    manifest = get_manifest()
    pinned = get_pinned()
    valid_ids = [sid for sid in ids if sid in manifest]
    for sid in valid_ids:
        pinned.add(sid)
    save_pinned(pinned)
    add(valid_ids)
    print(f"[PIN] Skills fixadas: {', '.join(valid_ids)}")

def unpin(ids: list[str]):
    pinned = get_pinned()
    manifest = get_manifest()
    for sid in ids:
        if sid in pinned:
            pinned.remove(sid)
            target_name = manifest.get(sid, {}).get("target", sid)
            remove_item(get_active_dir() / target_name)
            print(f"[UNPIN] Desafixada e removida: {sid}")
        else:
            print(f"[!] Skill não estava fixada: {sid}")
    save_pinned(pinned)

def remove_item(path: Path):
    if path.name == ".gitkeep":
        return

    # Trava de segurança: impede exclusão fora do diretório ativo
    try:
        path.absolute().relative_to(get_active_dir().absolute())
    except ValueError:
        print(f"[ALERTA DE SEGURANÇA] Bloqueada tentativa de remover fora do diretório ativo: {path}")
        return

    path_str = str(path.absolute())
    try:
        # No Windows, remove junção ou symlink instantaneamente
        os.unlink(path_str)
        return
    except OSError:
        pass

    try:
        if path.is_dir():
            shutil.rmtree(path_str, ignore_errors=True)
        elif path.is_file():
            path.unlink(missing_ok=True)
    except Exception:
        pass

def link_directory(src: Path, dst: Path):
    """Cria ponteiro instantâneo (Symlink ou Windows Directory Junction) sem cópia física."""
    # 1. Tenta symlink padrão
    try:
        os.symlink(src, dst, target_is_directory=src.is_dir())
        return "symlink"
    except OSError:
        pass

    # 2. Windows Directory Junction (0ms, sem privilégios de Administrador)
    if sys.platform == "win32" and src.is_dir():
        try:
            import _winapi
            _winapi.CreateJunction(str(src.resolve()), str(dst.absolute()))
            return "junction"
        except Exception:
            pass

    # 3. Fallback cópia física
    if src.is_dir():
        shutil.copytree(src, dst)
    else:
        shutil.copy2(src, dst)
    return "copy"

def find_skill_source(sid: str) -> tuple[Path | None, str]:
    """Busca o diretório da skill: prioriza skills_custom locais, depois vault."""
    active_dir = get_active_dir()
    # 1. Checa se o projeto alvo tem skills_custom/
    ws_custom = active_dir.parent.parent / "skills_custom" / sid
    if ws_custom.exists():
        return ws_custom.resolve(), "custom-workspace"

    # 2. Checa skills_custom do router
    router_custom = ROOT / "skills_custom" / sid
    if router_custom.exists():
        return router_custom.resolve(), "custom-router"

    # 3. Vault padrão
    manifest = get_manifest()
    target_name = manifest.get(sid, {}).get("target", sid)
    vault_src = ROOT / "skills_vault" / target_name
    if vault_src.exists():
        return vault_src.resolve(), "vault"

    return None, "not-found"

def add(ids: list[str]) -> list[str]:
    load_env()
    manifest = get_manifest()
    active_dir = get_active_dir()
    active_dir.mkdir(parents=True, exist_ok=True)
    activated = []

    for sid in ids:
        src, origin = find_skill_source(sid)
        if not src:
            print(f"[!] ID não encontrado no catálogo nem em skills_custom/: '{sid}'")
            continue

        target_name = sid
        dst = active_dir / target_name

        if dst.exists() or dst.is_symlink():
            print(f"[-] Já ativa: {sid}")
            activated.append(sid)
            continue

        meta = manifest.get(sid, {})
        missing = [v for v in meta.get("required_env", []) if not os.getenv(v)]
        if missing:
            print(f"[X] Bloqueada '{sid}': Faltam variáveis no .env -> {', '.join(missing)}")
            continue

        method = link_directory(src, dst)
        print(f"[+] Ativada ({origin}, {method}): {sid}")
        activated.append(sid)
    return activated

def remove(ids: list[str]):
    manifest = get_manifest()
    pinned = get_pinned()
    active_dir = get_active_dir()
    for sid in ids:
        if sid in pinned:
            print(f"[!] Skill '{sid}' está fixada (PIN). Use 'unpin {sid}' para removê-la.")
            continue
        target_name = manifest.get(sid, {}).get("target", sid)
        dst = active_dir / target_name
        if dst.exists() or dst.is_symlink():
            remove_item(dst)
            print(f"[-] Desativada: {sid}")
        else:
            print(f"[!] Skill inativa: {sid}")

def reset(force: bool = False):
    pinned = set() if force else get_pinned()
    manifest = get_manifest()
    pinned_targets = {manifest.get(sid, {}).get("target", sid) for sid in pinned}

    active_dir = get_active_dir()
    removed_count = 0
    if active_dir.exists():
        for item in active_dir.iterdir():
            if item.name != ".gitkeep" and item.name not in pinned_targets:
                remove_item(item)
                removed_count += 1

    if pinned:
        print(f"[OK] Reset concluído ({removed_count} removidas). Mantidas fixadas: {', '.join(pinned)}")
    else:
        print("[OK] Todas as skills ativas foram removidas.")

def list_skills() -> list[str]:
    active = []
    pinned = get_pinned()
    active_dir = get_active_dir()
    if active_dir.exists():
        active = [item.name for item in active_dir.iterdir() if item.name != ".gitkeep"]

    if not active:
        print("[*] Nenhuma skill ativa no momento.")
        return []
    print(f"[*] Skills ativas em {active_dir.relative_to(ROOT) if active_dir.is_relative_to(ROOT) else active_dir}:")
    for name in active:
        tag = " [PINNED]" if name in pinned else ""
        print(f"  * {name}{tag}")
    return active

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Uso: python scripts/manage_skills.py [add|remove|reset|list|pin|unpin] [args...]")
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
    elif cmd == "pin":
        pin(args)
    elif cmd == "unpin":
        unpin(args)
    else:
        print(f"[!] Comando inválido: {cmd}. Use: add, remove, reset, list, pin ou unpin.")
