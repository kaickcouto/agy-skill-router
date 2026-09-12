import sys
import os
import re
import json
import unicodedata
from pathlib import Path

# Suporte a UTF-8 no Windows
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

# Adiciona pasta de scripts ao path para importar manage_skills
SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from manage_skills import add, reset, list_skills, get_manifest

# Frameworks irrelevantes para penalizar caso apareçam no ID sem terem sido pedidos
UNRELATED_FRAMEWORKS = {
    "angular", "vue", "svelte", "django", "laravel", "flutter",
    "swift", "godot", "odoo", "wordpress", "drupal", "magento",
    "spring", "ruby", "rails", "php", "csharp", "dotnet", "rust"
}

GENERIC_TERMS = {
    "python", "javascript", "typescript", "node", "code", "codigo",
    "script", "funcao", "function", "arquivo", "file", "criar",
    "fazer", "gerar", "escreva", "build", "create", "make", "task",
    "ajustar", "modificar", "corrigir", "adicionar", "novo", "loop",
    "loops", "logica", "explicar", "duvida", "ajuda", "array", "lista"
}

SYNONYMS = {
    "supabase-postgres-best-practices": ["supabase", "postgres", "postgresql", "rls", "migration", "migrations", "tabela", "tabelas", "sql", "politicas"],
    "supabase": ["supabase", "postgres", "postgresql", "rls", "migration", "migrations", "tabela", "tabelas", "sql"],
    "supabase-automation": ["supabase", "migration", "banco", "database"],
    "tailwind-design-system": ["tailwind", "tailwindcss", "css", "layout", "responsivo", "estilo", "tema"],
    "tailwind-patterns": ["tailwind", "tailwindcss", "css", "layout", "estilo", "componentes"],
    "tanstack-query-expert": ["tanstack", "react-query", "query", "cache", "fetch", "mutacao"],
    "zod-validation-expert": ["zod", "validacao", "schema", "schemas", "dto"],
    "vitest-skill": ["vitest", "teste", "testes", "testar", "unitario", "unitarios", "mock", "mocking"],
    "webapp-testing": ["teste", "testes", "testar", "cypress", "playwright", "e2e", "qa", "automatizar", "verificar"],
    "pdf": ["pdf", "pdfs", "adobe", "ocr", "formulario", "formularios", "folha", "pagina", "devis", "relatorio"],
    "xlsx": ["planilha", "planilhas", "excel", "tabela", "tabelas", "spreadsheet", "spreadsheets", "csv", "tsv", "colunas", "linhas", "formulas", "ppa", "bpu", "openpyxl", "pandas"],
    "docx": ["word", "doc", "docx", "documento", "documentos", "texto", "redacao", "relatorio", "contrato", "oficio"],
    "pptx": ["powerpoint", "apresentacao", "apresentacoes", "slides", "slide", "deck", "pitch"],
    "frontend-design": ["frontend", "interface", "ui", "ux", "react", "componente", "componentes", "layout", "visual", "tela"],
    "web-artifacts-builder": ["site", "aplicacao", "pagina", "webapp", "dashboard", "componente", "spa"],
    "mcp-builder": ["mcp", "protocolo", "servidor", "conector", "integration", "tools"],
    "canvas-design": ["poster", "banner", "cartaz", "arte", "ilustracao", "design", "grafico"],
    "slack-gif-creator": ["gif", "animacao", "slack", "sticker", "frame"],
    "brand-guidelines": ["marca", "identidade", "branding", "paleta", "cores", "padrao"],
    "doc-coauthoring": ["coautoria", "revisao", "editorial", "redigir", "co-autor"],
    "internal-comms": ["comunicacao", "comunicado", "anuncio", "newsletter", "memorando"]
}

def normalize(text: str) -> str:
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("utf-8")
    return text.lower()

def score_skill(query: str, skill_id: str, skill_data: dict) -> float:
    normalized_query = normalize(query)
    tokens = set(re.findall(r'\b[a-z0-9_\-]{3,}\b', normalized_query))
    if not tokens:
        return 0.0

    score = 0.0
    norm_id = normalize(skill_id)
    id_parts = set(norm_id.split("-"))
    norm_desc = normalize(skill_data.get("description", ""))
    norm_tags = [normalize(t) for t in skill_data.get("tags", [])]

    # Penalidade para frameworks estranhos que não estão no prompt
    for fw in UNRELATED_FRAMEWORKS:
        if fw in id_parts and fw not in tokens:
            return -100.0

    # 1. Correspondência no ID
    for token in tokens:
        if token == norm_id:
            score += 15.0
        elif token in id_parts and token not in GENERIC_TERMS:
            score += 8.0
        elif token in norm_id and token not in GENERIC_TERMS:
            score += 2.0

    # 2. Sinônimos e mapeamento de domínio
    syns = SYNONYMS.get(skill_id, [])
    for token in tokens:
        if token in syns:
            score += 7.0

    # 3. Correspondência em tags
    for token in tokens:
        if token in norm_tags:
            score += 0.5 if token in GENERIC_TERMS else 3.5

    # 4. Correspondência no texto da descrição
    for token in tokens:
        if token in norm_desc:
            score += 0.2 if token in GENERIC_TERMS else 1.0

    return score

def route(prompt: str, top_k: int = 2, threshold: float = 5.0):
    manifest = get_manifest()
    scored = []

    for sid, data in manifest.items():
        s = score_skill(prompt, sid, data)
        if s >= threshold:
            scored.append((s, sid))

    scored.sort(reverse=True, key=lambda x: x[0])
    selected = [sid for _, sid in scored[:top_k]]

    print(f"[*] Tarefa: '{prompt}'")
    reset()

    if selected:
        print(f"[*] Roteando automaticamente para: {', '.join(selected)}")
        add(selected)
    else:
        print("[*] Nenhuma skill especializada requerida (modo base sem custo extra).")

def status():
    manifest = get_manifest()
    print(f"[*] Total de skills cadastradas no Vault: {len(manifest)}")
    list_skills()

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Uso:")
        print("  python scripts/auto_route.py '<tarefa a ser executada>'")
        print("  python scripts/auto_route.py status")
        print("  python scripts/auto_route.py reset")
        sys.exit(0)

    arg = sys.argv[1].strip()
    if arg == "status":
        status()
    elif arg == "reset":
        reset()
    elif arg == "list":
        list_skills()
    else:
        full_query = " ".join(sys.argv[1:])
        route(full_query)
