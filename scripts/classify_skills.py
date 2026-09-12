import sys
import os
import re
import json
from pathlib import Path

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

ROOT = Path(__file__).resolve().parent.parent
VAULT_DIR = ROOT / "skills_vault"
MANIFEST_PATH = ROOT / "skills_manifest.json"

TECH_CATALOG = {
    "supabase": "Supabase",
    "postgres": "PostgreSQL",
    "postgresql": "PostgreSQL",
    "sql": "SQL",
    "react": "React",
    "nextjs": "Next.js",
    "tailwind": "Tailwind CSS",
    "tailwindcss": "Tailwind CSS",
    "typescript": "TypeScript",
    "javascript": "JavaScript",
    "python": "Python",
    "vitest": "Vitest",
    "jest": "Jest",
    "playwright": "Playwright",
    "cypress": "Cypress",
    "docker": "Docker",
    "kubernetes": "Kubernetes",
    "k8s": "Kubernetes",
    "fastapi": "FastAPI",
    "express": "Express",
    "nodejs": "Node.js",
    "node": "Node.js",
    "zod": "Zod",
    "graphql": "GraphQL",
    "redis": "Redis",
    "prisma": "Prisma",
    "drizzle": "Drizzle ORM",
    "xlsx": "Excel / Openpyxl",
    "excel": "Excel",
    "pdf": "PDF",
    "docx": "Word / DOCX",
    "pptx": "PowerPoint / PPTX",
    "pandas": "Pandas",
    "three": "Three.js",
    "webgl": "WebGL",
    "zustand": "Zustand",
    "tanstack": "TanStack Query",
    "vue": "Vue.js",
    "angular": "Angular",
    "mcp": "Model Context Protocol",
    "auth": "OAuth / JWT Auth",
    "rls": "Row Level Security (RLS)"
}

BLOCK_TITLES = {
    "core-frontend": "Frontend & Interface UI",
    "core-backend": "Backend, APIs & Auth",
    "core-database": "Bancos de Dados & Migrations",
    "quality-testing": "Qualidade, Testes & Arquitetura",
    "cloud-devops": "DevOps, Infra & Deploy",
    "data-ai-engine": "Dados, IA & Automação",
    "office-docs": "Documentos & Relatórios"
}

def clean_trigger(text: str) -> str:
    text = re.sub(r'^[-*•\d\.]+\s*', '', text).strip()
    text = re.sub(r'^(?:Use\s+(?:this\s+skill\s+)?when(?:\s+the\s+user|\s+you)?|User\s+mentions(?:\s+or\s+implies)?:\s*|When\s+|Trigger\s+(?:especially\s+)?when\s+)', '', text, flags=re.IGNORECASE).strip()
    text = text.strip('"\'` .,:;')
    if text:
        text = text[0].upper() + text[1:]
    return text

def extract_triggers_and_intent(content: str, desc: str, skill_id: str) -> tuple[str, list[str], list[str]]:
    triggers = []

    # 1. Busca seções estruturadas no markdown
    sections = re.findall(r'##\s*(?:When to (?:Use|Apply)|Triggers|Use Cases)(.*?)(?=\n##|\Z)', content, re.DOTALL | re.IGNORECASE)
    for sec in sections:
        for line in sec.splitlines():
            line = line.strip()
            if line.startswith(('-', '*', '•')) and len(line) > 5:
                ct = clean_trigger(line)
                if ct and ct not in triggers and len(ct) > 4:
                    triggers.append(ct)

    # 2. Se não encontrou bullets, busca em frases descritivas dentro das seções
    if not triggers:
        for sec in sections:
            # Procura sentenças dentro da seção
            for sent in re.split(r'[;\n]', sec):
                sent = sent.strip()
                if len(sent) > 15 and not sent.startswith('#'):
                    ct = clean_trigger(sent)
                    if ct and ct not in triggers:
                        triggers.append(ct)
                        if len(triggers) >= 3:
                            break

    # 3. Fallback: extrai do campo 'description'
    if not triggers and desc:
        match = re.search(r'(?:use\s+(?:this\s+skill\s+)?when|trigger\s+(?:especially\s+)?when|use\s+for)\s+(.*?)(?:\.|$)', desc, re.IGNORECASE)
        if match:
            raw_clauses = re.split(r'[,;]|\bor\b', match.group(1))
            for clause in raw_clauses:
                ct = clean_trigger(clause)
                if len(ct) > 8 and ct not in triggers:
                    triggers.append(ct)

    # 4. Fallback contextual a partir do ID e descrição
    if not triggers:
        parts = skill_id.replace('-', ' ').title()
        triggers.append(f"Desenvolvimento ou tarefas envolvendo {parts}")

    # Síntese de call_intent (1 frase concisa de até 150 caracteres)
    intent = ""
    if desc:
        first_sentence = desc.split('.')[0].strip()
        first_sentence = re.sub(r'^(?:Use\s+this\s+skill\s+(?:any\s+time|when)|Expert\s+in|Comprehensive)\s+', '', first_sentence, flags=re.IGNORECASE)
        intent = first_sentence.strip('"\'` ')
        if intent:
            intent = intent[0].upper() + intent[1:]
    if not intent or len(intent) < 10:
        intent = f"Especialista em {skill_id.replace('-', ' ')} e padrões de engenharia."

    # Identificação da Stack Tecnológica
    combined_text = f"{skill_id} {content[:1000]} {desc}".lower()
    stack = []
    for k, name in TECH_CATALOG.items():
        if re.search(rf'\b{re.escape(k)}\b', combined_text):
            if name not in stack:
                stack.append(name)

    return intent[:180], triggers[:5], stack[:6]

def classify_all():
    if not MANIFEST_PATH.exists():
        print("[!] Erro: skills_manifest.json não encontrado.")
        sys.exit(1)

    with open(MANIFEST_PATH, "r", encoding="utf-8") as f:
        manifest = json.load(f)

    print(f"[*] Iniciando classificação detalhada de {len(manifest)} skills...")
    updated_count = 0

    for item in manifest:
        sid = item["id"]
        s_dir = VAULT_DIR / sid
        s_md = s_dir / "SKILL.md"

        content = ""
        if s_md.exists():
            try:
                content = s_md.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                pass

        intent, triggers, stack = extract_triggers_and_intent(content, item.get("description", ""), sid)

        item["call_intent"] = intent
        item["triggers"] = triggers
        item["tech_stack"] = stack
        updated_count += 1

    with open(MANIFEST_PATH, "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)

    print(f"[OK] Classificação concluída com sucesso! {updated_count} skills enriquecidas.")

if __name__ == "__main__":
    classify_all()
