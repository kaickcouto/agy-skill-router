import os
import sys
import re
import json
import shutil
import stat
import urllib.request
import urllib.error
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
ROUTER_ENV_PATH = ROOT / ".env"

CURRENT_WORKSPACE = None

def _resolve_workspace_base() -> Path:
    if CURRENT_WORKSPACE:
        return CURRENT_WORKSPACE
    cwd = Path.cwd()
    if (cwd / ".git").exists() and cwd.resolve() != ROOT.resolve():
        return cwd
    load_env()
    ws_env = os.environ.get("AGY_WORKSPACE") or os.environ.get("DEFAULT_WORKSPACE")
    if ws_env:
        p = Path(ws_env).resolve()
        if p.exists():
            return p
    return ROOT

def _get_agent_folder_name(base: Path) -> str:
    """Retorna '.agents' se já existir no workspace (padrão Antigravity), senão '.agent'."""
    if (base / ".agents").exists():
        return ".agents"
    return ".agent"

def set_workspace(path: str | Path = None):
    global CURRENT_WORKSPACE
    if path:
        CURRENT_WORKSPACE = Path(path).resolve()
        ensure_target_gitignore(CURRENT_WORKSPACE)
    else:
        CURRENT_WORKSPACE = None

def get_active_dir() -> Path:
    base = _resolve_workspace_base()
    folder = _get_agent_folder_name(base)
    d = base / folder / "skills"
    d.mkdir(parents=True, exist_ok=True)
    return d

def get_pinned_file() -> Path:
    base = _resolve_workspace_base()
    folder = _get_agent_folder_name(base)
    return base / folder / ".pinned.json"

def get_session_file() -> Path:
    base = _resolve_workspace_base()
    folder = _get_agent_folder_name(base)
    return base / folder / ".router_session.json"

def load_session_state() -> dict:
    sf = get_session_file()
    if sf.exists():
        try:
            with open(sf, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

def save_session_state(state: dict):
    sf = get_session_file()
    sf.parent.mkdir(parents=True, exist_ok=True)
    with open(sf, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)

def ensure_target_gitignore(workspace: Path):
    if not workspace or not workspace.exists():
        return
    gi = workspace / ".gitignore"
    folder = _get_agent_folder_name(workspace)
    rule = f"\n# AGY Skill Router\n{folder}/skills/*\n!{folder}/skills/.gitkeep\n{folder}/.pinned.json\n{folder}/.router_session.json\n"
    try:
        if gi.exists():
            content = gi.read_text(encoding="utf-8", errors="ignore")
            if f"{folder}/skills" not in content and ".agent/skills" not in content:
                gi.write_text(content.rstrip() + rule, encoding="utf-8")
        else:
            gi.write_text(rule.lstrip(), encoding="utf-8")
    except Exception:
        pass

def _parse_env_file(path: Path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))
    except Exception:
        pass

def load_env():
    if CURRENT_WORKSPACE:
        ws_env = CURRENT_WORKSPACE / ".env"
        if ws_env.exists():
            _parse_env_file(ws_env)
    if ROUTER_ENV_PATH.exists():
        _parse_env_file(ROUTER_ENV_PATH)

CACHE_FILE = ROOT / ".agent" / "index_cache.pkl"

def invalidate_cache():
    """Invalida o cache do índice BM25 quando novas skills forem adicionadas ou modificadas."""
    if CACHE_FILE.exists():
        CACHE_FILE.unlink(missing_ok=True)
    legacy_cache = ROOT / ".cache"
    if legacy_cache.exists():
        shutil.rmtree(legacy_cache, ignore_errors=True)

def get_manifest() -> dict:
    if not MANIFEST_PATH.exists():
        raise FileNotFoundError(f"skills_manifest.json ausente em: {MANIFEST_PATH}")
    with open(MANIFEST_PATH, "r", encoding="utf-8") as f:
        manifest = {item["id"]: item for item in json.load(f)}

    # Auto-descoberta dinâmica de skills personalizadas em skills_custom/
    custom_dirs = [ROOT / "skills_custom"]
    active_dir = get_active_dir()
    ws_custom = active_dir.parent.parent / "skills_custom"
    if ws_custom.exists() and ws_custom.resolve() != (ROOT / "skills_custom").resolve():
        custom_dirs.append(ws_custom)

    for cdir in custom_dirs:
        if cdir.exists():
            for sdir in cdir.iterdir():
                if sdir.is_dir() and (sdir / "SKILL.md").exists() and sdir.name not in manifest:
                    # Extrai descrição real do frontmatter YAML se presente
                    custom_desc = f"Skill personalizada: {sdir.name}"
                    custom_triggers = [sdir.name]
                    try:
                        content = (sdir / "SKILL.md").read_text(encoding="utf-8", errors="ignore")
                        fm_match = re.search(r'^---\r?\n(.*?)\r?\n---', content, re.DOTALL)
                        if fm_match:
                            fm_text = fm_match.group(1)
                            desc_match = re.search(r'^description:\s*(?:[>|]-?\s*)?(.*?)(?=(?:\r?\n[a-z0-9_\-]+:|\Z))', fm_text, re.DOTALL | re.MULTILINE)
                            if desc_match and desc_match.group(1).strip():
                                custom_desc = re.sub(r'\s+', ' ', desc_match.group(1)).strip().strip('"\'')
                    except Exception:
                        pass

                    manifest[sdir.name] = {
                        "id": sdir.name,
                        "title": sdir.name.replace("-", " ").title(),
                        "category": "custom",
                        "thematic_block": "custom",
                        "description": custom_desc,
                        "triggers": custom_triggers,
                        "tech_stack": [sdir.name],
                        "origin": "custom"
                    }
    return manifest

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

def is_junction_or_link(path: Path) -> bool:
    try:
        if path.is_symlink():
            return True
        if sys.platform == "win32":
            st = os.lstat(str(path))
            return bool(st.st_file_attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT)
    except Exception:
        return False
    return False

def remove_item(path: Path):
    remove_items_batch([path])

def remove_items_batch(paths: list[Path]):
    if not paths:
        return
    session = load_session_state()
    active_dir_abs = get_active_dir().absolute()
    targets_to_clean = []

    for path in paths:
        if path.name == ".gitkeep":
            continue
        try:
            path.absolute().relative_to(active_dir_abs)
        except ValueError:
            print(f"[ALERTA] Bloqueada exclusão fora do diretório ativo: {path}")
            continue
        is_managed = path.name in session
        if path.is_dir() and not is_junction_or_link(path) and not is_managed:
            continue
        targets_to_clean.append(path)

    remaining_junctions = []
    for path in targets_to_clean:
        path_str = str(path.absolute())
        # 1. Tentativa Win32 nativa ultra-rápida (0ms)
        if sys.platform == "win32" and is_junction_or_link(path):
            try:
                os.rmdir(path_str)
                if not os.path.lexists(path_str):
                    continue
            except OSError:
                pass

        try:
            os.unlink(path_str)
            if not os.path.lexists(path_str):
                continue
        except OSError:
            pass

        if sys.platform == "win32" and is_junction_or_link(path):
            remaining_junctions.append(path_str)
        else:
            try:
                if path.is_dir():
                    shutil.rmtree(path_str, ignore_errors=True)
                elif path.is_file():
                    path.unlink(missing_ok=True)
            except Exception:
                pass

    # 2. Se alguma junção falhar (comum no OneDrive por ACL lock), limpa todas em um ÚNICO subprocesso batch (<200ms)
    if remaining_junctions and sys.platform == "win32":
        try:
            import subprocess
            commands = []
            for r in remaining_junctions:
                commands.append(f"fsutil reparsepoint delete '{r}'")
                commands.append(f"Remove-Item -LiteralPath '{r}' -Force -Recurse -ErrorAction SilentlyContinue")
            batch_cmd = " ; ".join(commands)
            subprocess.run(["powershell", "-NoProfile", "-Command", f"& {{ {batch_cmd} }}"], capture_output=True, timeout=10)
        except Exception:
            pass

def link_directory(src: Path, dst: Path) -> str:
    try:
        os.symlink(src, dst, target_is_directory=src.is_dir())
        return "symlink"
    except OSError:
        pass

    if sys.platform == "win32" and src.is_dir():
        try:
            import _winapi
            _winapi.CreateJunction(str(src.resolve()), str(dst.absolute()))
            return "junction"
        except Exception:
            pass

    if src.is_dir():
        shutil.copytree(src, dst)
    else:
        shutil.copy2(src, dst)
    return "copy"

def find_skill_source(sid: str) -> tuple[Path | None, str]:
    active_dir = get_active_dir()
    ws_custom = active_dir.parent.parent / "skills_custom" / sid
    if ws_custom.exists():
        return ws_custom.resolve(), "custom-workspace"

    router_custom = ROOT / "skills_custom" / sid
    if router_custom.exists():
        return router_custom.resolve(), "custom-router"

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
    session = load_session_state()
    activated = []

    for sid in ids:
        src, origin = find_skill_source(sid)
        if not src:
            print(f"[!] ID não encontrado: '{sid}'")
            continue

        target_name = sid
        dst = active_dir / target_name

        if is_junction_or_link(dst) and not dst.exists():
            remove_item(dst)

        if dst.exists() or dst.is_symlink() or is_junction_or_link(dst):
            print(f"[-] Já ativa ou nativa: {sid}")
            activated.append(sid)
            continue

        meta = manifest.get(sid, {})
        missing = [v for v in meta.get("required_env", []) if not os.getenv(v)]
        if missing:
            print(f"[X] Bloqueada '{sid}': Faltam variáveis no .env -> {', '.join(missing)}")
            continue

        method = link_directory(src, dst)
        session[target_name] = {"origin": origin, "method": method}
        print(f"[+] Ativada ({origin}, {method}): {sid}")
        activated.append(sid)

    save_session_state(session)
    return activated

def remove(ids: list[str]):
    manifest = get_manifest()
    pinned = get_pinned()
    active_dir = get_active_dir()
    session = load_session_state()

    for sid in ids:
        if sid in pinned:
            print(f"[!] Skill '{sid}' está fixada (PIN). Use 'unpin {sid}'.")
            continue
        target_name = manifest.get(sid, {}).get("target", sid)
        dst = active_dir / target_name
        if dst.exists() or dst.is_symlink() or is_junction_or_link(dst):
            remove_item(dst)
            session.pop(target_name, None)
            print(f"[-] Desativada: {sid}")
        else:
            print(f"[!] Skill inativa: {sid}")
    save_session_state(session)

def reset(force: bool = False):
    pinned = set() if force else get_pinned()
    manifest = get_manifest()
    pinned_targets = {manifest.get(sid, {}).get("target", sid) for sid in pinned}

    active_dir = get_active_dir()
    session = load_session_state()
    removed_count = 0
    preserved_native = []

    if active_dir.exists():
        items_to_delete = []
        for item in list(active_dir.iterdir()):
            if item.name == ".gitkeep" or item.name in pinned_targets:
                continue
            is_managed = item.name in session
            if item.is_dir() and not is_junction_or_link(item) and not is_managed:
                preserved_native.append(item.name)
                continue
            items_to_delete.append(item)
            session.pop(item.name, None)
            removed_count += 1
        remove_items_batch(items_to_delete)

    save_session_state(session)
    msg_parts = [f"[OK] Reset concluído ({removed_count} links/itens removidos)"]
    if pinned:
        msg_parts.append(f"Fixadas: {', '.join(pinned)}")
    if preserved_native:
        msg_parts.append(f"Nativas preservadas: {', '.join(preserved_native)}")
    print(". ".join(msg_parts) + ".")

def pin(ids: list[str]):
    manifest = get_manifest()
    pinned = get_pinned()
    valid_ids = [sid for sid in ids if sid in manifest]
    invalid_ids = [sid for sid in ids if sid not in manifest]
    if invalid_ids:
        print(f"[!] Skill(s) não encontrada(s) no catálogo: {', '.join(invalid_ids)}")
    if valid_ids:
        for sid in valid_ids:
            pinned.add(sid)
        save_pinned(pinned)
        add(valid_ids)
        print(f"[PIN] Skills fixadas: {', '.join(valid_ids)}")

def unpin(ids: list[str]):
    pinned = get_pinned()
    manifest = get_manifest()
    session = load_session_state()
    for sid in ids:
        if sid in pinned:
            pinned.remove(sid)
            target_name = manifest.get(sid, {}).get("target", sid)
            remove_item(get_active_dir() / target_name)
            session.pop(target_name, None)
            print(f"[UNPIN] Desafixada e removida: {sid}")
    save_pinned(pinned)
    save_session_state(session)

def list_skills() -> list[str]:
    active = []
    pinned = get_pinned()
    active_dir = get_active_dir()
    session = load_session_state()

    if active_dir.exists():
        active = [item.name for item in active_dir.iterdir() if item.name != ".gitkeep"]

    if not active:
        print("[*] Nenhuma skill ativa no momento.")
        return []
    print(f"[*] Skills ativas:")
    for name in active:
        p = active_dir / name
        tags = []
        if name in pinned:
            tags.append("PINNED")
        if name in session:
            tags.append(f"ROUTER-{session[name]['method'].upper()}")
        elif p.is_dir() and not is_junction_or_link(p):
            tags.append("NATIVA/LOCAL")
        tag_str = f" [{' | '.join(tags)}]" if tags else ""
        print(f"  * {name}{tag_str}")
    return active

def init_skill(name: str, description: str = None) -> Path | None:
    """Scaffolds a new specialized skill in skills_custom/<name>/SKILL.md."""
    clean_name = re.sub(r'[^a-zA-Z0-9_\-]+', '-', name.strip().lower()).strip('-')
    if not clean_name:
        print(f"[!] Nome de skill inválido: '{name}'. Use apenas letras minúsculas, números, hífens e underscores.")
        return None

    target_dir = ROOT / "skills_custom" / clean_name
    target_file = target_dir / "SKILL.md"
    if target_file.exists():
        print(f"[!] A skill '{clean_name}' já existe em: {target_dir}")
        return target_file

    target_dir.mkdir(parents=True, exist_ok=True)
    desc = description.strip() if description else f"Diretrizes técnicas e padrões especializados para {clean_name}."

    template = f"""---
name: {clean_name}
description: {desc}
---

# {clean_name.replace('-', ' ').title()}

## Quando Ativar Esta Skill
- Use quando a tarefa envolver {clean_name}.
- Acione para implementação, refatoração ou auditoria deste domínio.

## Diretrizes de Engenharia & Boas Práticas
1. Siga a Escada de Decisão do Ponytail (YAGNI, menor diff funcional).
2. Priorize recursos nativos da plataforma e bibliotecas já instaladas.
3. Garanta validação estrita nas fronteiras e testes automatizados.

## Exemplos Canônicos
```typescript
// Implementação padrão de referência
```

## Anti-Padrões Proibidos
- Não crie abstrações prematuras de uso único.
- Não introduza dependências externas desnecessárias.
"""
    target_file.write_text(template, encoding="utf-8")
    invalidate_cache()

    print(f"[+] Skill '{clean_name}' inicializada com sucesso!")
    print(f"    Local: {target_file}")
    return target_file

def lint_skill(target: str) -> bool:
    """Valida frontmatter YAML, integridade técnica e tamanho de uma skill."""
    clean_target = target.strip()
    src, origin = find_skill_source(clean_target)

    p = Path(clean_target)
    if p.is_file():
        skill_file = p
        skill_name = p.parent.name
    elif p.is_dir() and (p / "SKILL.md").exists():
        skill_file = p / "SKILL.md"
        skill_name = p.name
    elif src and (src / "SKILL.md").exists():
        skill_file = src / "SKILL.md"
        skill_name = clean_target
    else:
        print(f"[X] Skill ou arquivo SKILL.md não encontrado para: '{clean_target}'")
        return False

    content = skill_file.read_text(encoding="utf-8", errors="ignore")
    size_bytes = len(content.encode("utf-8"))
    size_kb = size_bytes / 1024.0

    print(f"\n📋 LINT REPORT: {skill_name} ({skill_file})")
    print("-" * 65)

    issues = 0
    warnings = 0

    # 1. Frontmatter YAML (com suporte a multilinhas >- ou |)
    fm_match = re.search(r'^---\r?\n(.*?)\r?\n---', content, re.DOTALL)
    if not fm_match:
        print(" ❌ [ERRO] Frontmatter YAML ausente no início do arquivo (delimitadores ---).")
        issues += 1
    else:
        fm_text = fm_match.group(1)
        has_name = bool(re.search(r'^name:\s*.+', fm_text, re.MULTILINE))
        desc_match = re.search(r'^description:\s*(?:[>|]-?\s*)?(.*?)(?=(?:\r?\n[a-z0-9_\-]+:|\Z))', fm_text, re.DOTALL | re.MULTILINE)

        if has_name:
            print(" ✅ [OK] Campo 'name' presente no frontmatter.")
        else:
            print(" ❌ [ERRO] Campo 'name' ausente no frontmatter.")
            issues += 1

        if desc_match and desc_match.group(1).strip():
            desc_val = re.sub(r'\s+', ' ', desc_match.group(1)).strip().strip('"\'')
            if len(desc_val) >= 20:
                print(f" ✅ [OK] Campo 'description' descritivo ({len(desc_val)} caracteres).")
            else:
                print(f" ⚠️ [AVISO] 'description' muito curta ({len(desc_val)} chars). Recomendado >= 20 para BM25.")
                warnings += 1
        else:
            print(" ❌ [ERRO] Campo 'description' ausente no frontmatter.")
            issues += 1

    # 2. Orçamento de Contexto & Tamanho
    if size_kb <= 50:
        print(f" ✅ [OK] Tamanho ideal para contexto ({size_kb:.1f} KB <= 50 KB).")
    elif size_kb <= 90:
        print(f" ⚠️ [AVISO] Tamanho moderado ({size_kb:.1f} KB). Mantenha conciso para economizar tokens.")
        warnings += 1
    else:
        print(f" ❌ [ERRO] Tamanho excessivo ({size_kb:.1f} KB > 90 KB). Risco de saturar a janela de contexto.")
        issues += 1

    # 3. Em-dashes proibidos (Anti-tell)
    em_dashes = len(re.findall(r'[—–]', content))
    if em_dashes == 0:
        print(" ✅ [OK] Zero travessões longos (em-dash / en-dash).")
    else:
        print(f" ⚠️ [AVISO] Detectados {em_dashes} travessões em-dash/en-dash ('—'/'–'). Use hífens normais ('-').")
        warnings += 1

    # 4. Blocos de Código Markdown
    fences = len(re.findall(r'^```', content, re.MULTILINE))
    if fences % 2 == 0:
        print(" ✅ [OK] Blocos de código markdown devidamente balanceados.")
    else:
        print(f" ❌ [ERRO] Blocos de código não balanceados ({fences} marcadores ``` encontrados).")
        issues += 1

    print("-" * 65)
    if issues == 0:
        print(f" 🎉 RESULTADO: APROVADO! ({warnings} avisos)")
        return True
    else:
        print(f" 🚫 RESULTADO: REPROVADO ({issues} erros, {warnings} avisos).")
        return False

def _parse_github_spec(spec: str, skill_folder: str = None) -> tuple[str, str, str, str]:
    """Extrai (owner, repo, subpath, skill_name) a partir de spec ou URL."""
    spec = spec.strip().rstrip("/")
    if "github.com/" in spec:
        match = re.search(r'github\.com/([^/]+)/([^/]+)(?:/(?:tree|blob)/[^/]+/(.+))?', spec)
        if match:
            owner, repo, raw_subpath = match.group(1), match.group(2), match.group(3) or ""
            repo = repo.replace(".git", "")
            subpath = skill_folder or raw_subpath
            if subpath.endswith("/SKILL.md"):
                subpath = subpath[:-9]
            elif subpath.lower() == "skill.md":
                subpath = ""
            skill_name = Path(subpath).name if subpath else repo
            return owner, repo, subpath, skill_name

    if "@" in spec:
        base, subpath = spec.split("@", 1)
        owner, repo = base.strip().split("/", 1)
        if subpath.endswith("/SKILL.md"):
            subpath = subpath[:-9]
        elif subpath.lower() == "skill.md":
            subpath = ""
        skill_name = Path(subpath).name if subpath else repo
        return owner, repo, subpath, skill_name

    if "/" in spec:
        parts = spec.split("/", 1)
        owner, repo = parts[0], parts[1]
        subpath = skill_folder or ""
        if subpath.endswith("/SKILL.md"):
            subpath = subpath[:-9]
        elif subpath.lower() == "skill.md":
            subpath = ""
        skill_name = Path(subpath).name if subpath else repo
        return owner, repo, subpath, skill_name

    raise ValueError(f"Formato inválido: '{spec}'. Use 'owner/repo' ou 'owner/repo@subpasta'.")

def import_skill(spec: str, skill_folder: str = None, as_name: str = None) -> bool:
    """Importa uma skill de um repositório GitHub diretamente para skills_custom/."""
    try:
        owner, repo, subpath, default_name = _parse_github_spec(spec, skill_folder)
    except Exception as e:
        print(f"[!] Erro ao interpretar repositório: {e}")
        return False

    target_name = as_name or default_name
    target_name = re.sub(r'[^a-zA-Z0-9_\-]', '-', target_name).lower()
    target_dir = ROOT / "skills_custom" / target_name
    target_file = target_dir / "SKILL.md"

    print(f"[*] Importando skill de GitHub: {owner}/{repo}" + (f" (pasta: {subpath})" if subpath else "") + "...")

    branches = ["main", "master"]
    candidate_paths = []
    if subpath:
        sub_clean = subpath.strip("/")
        candidate_paths.extend([
            f"{sub_clean}/SKILL.md",
            f"skills/{sub_clean}/SKILL.md"
        ])
    else:
        candidate_paths.extend([
            "SKILL.md",
            f"skills/{repo}/SKILL.md",
            f"{repo}/SKILL.md"
        ])

    downloaded_content = None
    successful_url = None

    for b in branches:
        for p in candidate_paths:
            url = f"https://raw.githubusercontent.com/{owner}/{repo}/{b}/{p}"
            try:
                req = urllib.request.Request(url, headers={"User-Agent": "agy-skill-router/1.0"})
                with urllib.request.urlopen(req, timeout=8) as resp:
                    if resp.status == 200:
                        downloaded_content = resp.read().decode("utf-8", errors="ignore")
                        successful_url = url
                        break
            except Exception:
                continue
        if downloaded_content:
            break

    if not downloaded_content:
        print(f"[X] Não foi possível localizar SKILL.md em '{owner}/{repo}'.")
        print(f"    Tentados caminhos: {', '.join(candidate_paths)} nas branches main/master.")
        return False

    target_dir.mkdir(parents=True, exist_ok=True)
    target_file.write_text(downloaded_content, encoding="utf-8")
    print(f"[+] SKILL.md baixado de: {successful_url}")
    print(f"[+] Salvo em: {target_file}")

    invalidate_cache()

    lint_skill(target_name)
    return True

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Uso: python scripts/manage_skills.py [add|remove|reset|list|pin|unpin|init|lint|import] [args...]")
        sys.exit(0)

    cmd = sys.argv[1].lower()
    args = sys.argv[2:]

    if cmd == "add":
        add(args)
    elif cmd == "remove":
        remove(args)
    elif cmd == "reset":
        force_flag = "--force" in args
        reset(force=force_flag)
    elif cmd == "list":
        list_skills()
    elif cmd == "pin":
        pin(args)
    elif cmd == "unpin":
        unpin(args)
    elif cmd == "init":
        if not args:
            print("Uso: python scripts/manage_skills.py init <nome-da-skill> [descrição]")
        else:
            name = args[0]
            desc = " ".join(args[1:]) if len(args) > 1 else None
            init_skill(name, desc)
    elif cmd == "lint":
        if not args:
            print("Uso: python scripts/manage_skills.py lint <nome-da-skill>")
        else:
            lint_skill(args[0])
    elif cmd == "import":
        if not args:
            print("Uso: python scripts/manage_skills.py import <owner/repo[@subpasta]> [--skill subpasta] [--name nome]")
        else:
            spec = args[0]
            sub = None
            as_n = None
            if "--skill" in args:
                idx = args.index("--skill")
                if idx + 1 < len(args):
                    sub = args[idx + 1]
            if "--name" in args:
                idx = args.index("--name")
                if idx + 1 < len(args):
                    as_n = args[idx + 1]
            import_skill(spec, skill_folder=sub, as_name=as_n)
    else:
        print(f"[!] Comando inválido: {cmd}")
