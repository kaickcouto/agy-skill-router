import os
import sys
import ast
import json
import shutil
import re
from pathlib import Path

# Suporte a UTF-8 no terminal Windows
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

ROOT = Path(__file__).resolve().parent.parent
VAULT_DIR = ROOT / "skills_vault"
QUARANTINE_DIR = ROOT / "skills_quarantine"
MANIFEST_PATH = ROOT / "skills_manifest.json"

DANGEROUS_PATTERNS = {
    "eval(", "exec(", "pty.spawn", "socket.connect", "shutil.rmtree('/"
}

STOP_WORDS = {
    "and", "the", "for", "with", "this", "that", "from", "you", "use",
    "can", "are", "when", "all", "user", "any", "not", "should", "will",
    "para", "com", "uma", "que", "por", "como", "mais", "dos", "das"
}

def analyze_code_security(code: str, filename: str) -> tuple[bool, str, list[str]]:
    if filename.endswith("__init__.py") or not code.strip():
        return True, "Aprovada", []

    for pattern in DANGEROUS_PATTERNS:
        if pattern in code:
            return False, f"Padrão inseguro detectado: {pattern}", []

    try:
        ast.parse(code)
    except SyntaxError:
        return False, "Erro de sintaxe Python", []

    env_matches = re.findall(r'os\.(?:environ\["([^"]+)"\]|getenv\(["\']([^"\']+)["\'])', code)
    detected_envs = list({k for tup in env_matches for k in tup if k})

    return True, "Aprovada", detected_envs

def parse_yaml_description(frontmatter: str) -> str:
    lines = frontmatter.splitlines()
    collecting = False
    desc_parts = []

    for line in lines:
        if not collecting:
            m = re.match(r'^description:\s*(.*)', line)
            if m:
                val = m.group(1).strip()
                if val in (">", "|", ">-", "|-"):
                    collecting = True
                else:
                    if (val.startswith('"') and val.endswith('"')) or (val.startswith("'") and val.endswith("'")):
                        val = val[1:-1]
                    return val
        else:
            if line.startswith(" ") or line.startswith("\t"):
                desc_parts.append(line.strip())
            elif line.strip():
                break

    if desc_parts:
        return " ".join(desc_parts)
    return ""

def extract_metadata(target: Path) -> tuple[str, list[str]]:
    desc = ""
    for doc_name in ["SKILL.md", "README.md"]:
        doc_file = target / doc_name if target.is_dir() else None
        if doc_file and doc_file.exists():
            text = doc_file.read_text(encoding="utf-8", errors="ignore")
            fm_match = re.search(r'^---\s*\n(.*?)\n---', text, re.DOTALL)
            if fm_match:
                desc = parse_yaml_description(fm_match.group(1))
                if desc:
                    break
            
            for line in text.splitlines():
                clean = line.strip()
                if clean and not clean.startswith("#") and clean != "---":
                    desc = clean
                    break
            if desc:
                break

    if not desc:
        py_files = list(target.rglob("*.py")) if target.is_dir() else [target] if target.suffix == ".py" else []
        for py in py_files:
            try:
                tree = ast.parse(py.read_text(encoding="utf-8", errors="ignore"))
                doc = ast.get_docstring(tree)
                if doc:
                    desc = doc.strip().splitlines()[0]
                    break
            except Exception:
                continue

    if not desc:
        desc = f"Skill operacional: {target.name}"

    words = re.findall(r'\b[a-zA-Z0-9_\-]{3,}\b', f"{target.name} {desc}".lower())
    tags = sorted(list({w for w in words if w not in STOP_WORDS}))[:20]

    return desc, tags

def run():
    QUARANTINE_DIR.mkdir(parents=True, exist_ok=True)
    manifest = []
    aprovadas, descartadas = 0, 0

    print("[*] Iniciando auditoria e filtro de segurança no vault...")

    for item in sorted(VAULT_DIR.iterdir()):
        if item.name.startswith((".", "_")):
            continue

        valid = True
        required_envs = []
        py_files = list(item.rglob("*.py")) if item.is_dir() else [item] if item.suffix == ".py" else []

        if py_files:
            for pf in py_files:
                ok, reason, envs = analyze_code_security(pf.read_text(encoding="utf-8", errors="ignore"), pf.name)
                if not ok:
                    print(f"[!] Rejeitada {item.name}: {reason} em {pf.name}")
                    valid = False
                    break
                required_envs.extend(envs)
        else:
            if item.is_dir() and not any(item.glob("*")):
                valid = False

        if not valid:
            shutil.move(str(item), str(QUARANTINE_DIR / item.name))
            descartadas += 1
            continue

        desc, tags = extract_metadata(item)
        manifest.append({
            "id": item.name.replace(".py", ""),
            "target": item.name,
            "description": desc,
            "tags": tags,
            "required_env": sorted(list(set(required_envs)))
        })
        aprovadas += 1

    with open(MANIFEST_PATH, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)

    print("\n[OK] Triagem Concluída com Sucesso!")
    print(f"    - Skills Aprovadas no Vault: {aprovadas}")
    print(f"    - Bloqueadas/Quarentena: {descartadas}")
    print(f"    - Manifesto gerado em: {MANIFEST_PATH.name}")

if __name__ == "__main__":
    run()
