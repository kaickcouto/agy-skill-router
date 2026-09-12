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

class SecurityASTVisitor(ast.NodeVisitor):
    def __init__(self):
        self.issues = []

    def visit_Call(self, node):
        if isinstance(node.func, ast.Name) and node.func.id in {"eval", "exec", "compile"}:
            self.issues.append(f"Chamada direta a '{node.func.id}()'")
        elif isinstance(node.func, ast.Attribute):
            if node.func.attr == "spawn" and isinstance(node.func.value, ast.Name) and node.func.value.id == "pty":
                self.issues.append("Chamada a 'pty.spawn()'")
            elif node.func.attr == "rmtree" and isinstance(node.func.value, ast.Name) and node.func.value.id == "shutil":
                if node.args and isinstance(node.args[0], ast.Constant) and node.args[0].value in {"/", "\\"}:
                    self.issues.append("Chamada destrutiva a 'shutil.rmtree('/')'")
        self.generic_visit(node)

    def visit_Import(self, node):
        for alias in node.names:
            if alias.name in {"pty"}:
                self.issues.append(f"Importação de módulo inseguro '{alias.name}'")
        self.generic_visit(node)

    def visit_ImportFrom(self, node):
        if node.module in {"pty"}:
            self.issues.append(f"Importação de módulo inseguro '{node.module}'")
        self.generic_visit(node)

STOP_WORDS = {
    "and", "the", "for", "with", "this", "that", "from", "you", "use",
    "can", "are", "when", "all", "user", "any", "not", "should", "will",
    "para", "com", "uma", "que", "por", "como", "mais", "dos", "das"
}

def analyze_code_security(code: str, filename: str) -> tuple[bool, str, list[str]]:
    if filename.endswith("__init__.py") or not code.strip():
        return True, "Aprovada", []

    try:
        tree = ast.parse(code)
    except SyntaxError:
        return False, "Erro de sintaxe Python", []

    visitor = SecurityASTVisitor()
    visitor.visit(tree)
    if visitor.issues:
        return False, f"Padrão inseguro detectado: {', '.join(visitor.issues)}", []

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

CATEGORIES = {
    "frontend": ["react", "vue", "svelte", "tailwind", "css", "html", "ui", "ux", "frontend", "nextjs", "vite", "component", "web", "dom", "zustand", "redux"],
    "backend": ["fastapi", "express", "node", "api", "rest", "graphql", "server", "endpoint", "auth", "jwt", "backend", "oauth", "pydantic"],
    "database": ["sql", "postgres", "postgresql", "supabase", "database", "banco", "redis", "mongo", "prisma", "drizzle", "migration", "orm", "queries"],
    "devops": ["docker", "kubernetes", "k8s", "terraform", "aws", "cloud", "vercel", "deploy", "git", "ci/cd", "pipeline", "bash", "linux", "nginx"],
    "testing": ["test", "testing", "vitest", "jest", "playwright", "cypress", "e2e", "unit", "mock", "tdd", "qa", "debug"],
    "data-ai": ["pandas", "excel", "xlsx", "csv", "data", "ai", "llm", "rag", "embeddings", "openai", "claude", "mcp", "analytics", "scraping", "scraper"],
    "design-media": ["design", "svg", "canvas", "threejs", "art", "gif", "video", "figma", "theme", "color", "animation"],
    "productivity": ["docx", "pptx", "pdf", "document", "report", "presentation", "markdown", "writing", "slack", "trello", "jira", "notion"]
}

def detect_category(name: str, desc: str, tags: list[str]) -> str:
    text = f"{name} {desc} {' '.join(tags)}".lower()
    scores = {}
    for cat, kws in CATEGORIES.items():
        s = sum(3 if kw in name.lower() else 1 for kw in kws if kw in text)
        if s > 0:
            scores[cat] = s
    if scores:
        return max(scores, key=scores.get)
    return "tools"

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
            q_target = QUARANTINE_DIR / item.name
            if q_target.exists():
                if q_target.is_dir():
                    shutil.rmtree(q_target, ignore_errors=True)
                else:
                    q_target.unlink(missing_ok=True)
            try:
                shutil.move(str(item), str(q_target))
            except Exception:
                pass
            descartadas += 1
            continue

        desc, tags = extract_metadata(item)
        cat = detect_category(item.name, desc, tags)
        manifest.append({
            "id": item.name.replace(".py", ""),
            "target": item.name,
            "category": cat,
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
