import sys
import os
import re
import json
import math
import pickle
import unicodedata
from collections import Counter
from pathlib import Path

# Suporte a UTF-8 no Windows
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parent
CACHE_FILE = ROOT / ".agent" / "index_cache.pkl"
MANIFEST_PATH = ROOT / "skills_manifest.json"

sys.path.insert(0, str(SCRIPT_DIR))
from manage_skills import add, reset, list_skills, pin, unpin, get_pinned, get_manifest

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
    "loops", "logica", "explicar", "duvida", "ajuda", "array", "lista",
    "while", "when", "with", "then", "also", "into", "from", "over",
    "just", "more", "como", "funciona", "qual", "para"
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

# Combos Coordenados de Skills (Dependency Bundles)
SKILL_BUNDLES = {
    "fullstack-supabase": {
        "title": "Fullstack Supabase & React",
        "triggers": ["crud", "supabase", "fullstack", "autenticacao", "dashboard", "bpu", "banco"],
        "min_matches": 2,
        "skills": ["supabase-postgres-best-practices", "frontend-design", "zod-validation-expert"]
    },
    "frontend-tailwind-ui": {
        "title": "Frontend Tailwind & Design System",
        "triggers": ["tailwind", "interface", "componentes", "layout", "responsivo", "estilo"],
        "min_matches": 2,
        "skills": ["tailwind-patterns", "frontend-design"]
    },
    "excel-data-reports": {
        "title": "Ingestão Excel/PPA & Relatórios PDF",
        "triggers": ["planilha", "excel", "devis", "ppa", "relatorio", "tabela", "openpyxl"],
        "min_matches": 2,
        "skills": ["xlsx", "pdf"]
    },
    "web-testing-suite": {
        "title": "Suíte Completa de Testes E2E & Unitários",
        "triggers": ["testes", "playwright", "vitest", "cypress", "e2e", "qa", "unitario", "testar"],
        "min_matches": 2,
        "skills": ["webapp-testing", "vitest-skill"]
    }
}

def normalize(text: str) -> str:
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("utf-8")
    return text.lower()

def tokenize(text: str) -> list[str]:
    norm = normalize(text)
    return re.findall(r'\b[a-z0-9_\-]{3,}\b', norm)

class BM25Index:
    def __init__(self, manifest: dict, k1: float = 1.5, b: float = 0.75):
        self.k1 = k1
        self.b = b
        self.manifest = manifest
        self.doc_ids = list(manifest.keys())
        self.N = len(self.doc_ids)
        self.doc_len = {}
        self.doc_term_freqs = {}
        self.df = Counter()

        total_length = 0
        for sid, meta in manifest.items():
            norm_id = normalize(sid)
            id_tokens = tokenize(norm_id)
            desc_tokens = tokenize(meta.get("description", ""))
            tag_tokens = [normalize(t) for t in meta.get("tags", [])]
            cat_tokens = tokenize(meta.get("category", ""))
            block_tokens = tokenize(meta.get("thematic_block", ""))
            syn_tokens = [normalize(s) for s in SYNONYMS.get(sid, [])]

            tf = Counter()
            for t in id_tokens:
                tf[t] += 4.0
            for t in block_tokens:
                tf[t] += 3.0
            for t in syn_tokens:
                tf[t] += 3.0
            for t in cat_tokens:
                tf[t] += 2.0
            for t in tag_tokens:
                tf[t] += 2.0
            for t in desc_tokens:
                tf[t] += 1.0

            dlen = sum(tf.values())
            self.doc_len[sid] = dlen
            self.doc_term_freqs[sid] = tf
            total_length += dlen

            for term in tf.keys():
                self.df[term] += 1

        self.avgdl = total_length / self.N if self.N > 0 else 1.0

    def score(self, query: str, category_filter: str = None, block_filter: str = None) -> list[tuple[float, str, list[str]]]:
        query_tokens = tokenize(query)
        if not query_tokens:
            return []

        non_generic_query = [t for t in query_tokens if t not in GENERIC_TERMS]

        scores = []
        for sid, meta in self.manifest.items():
            if category_filter and meta.get("category") != category_filter:
                continue
            if block_filter and meta.get("thematic_block") != block_filter:
                continue

            norm_id = normalize(sid)
            id_parts = set(norm_id.split("-"))

            has_unrelated = False
            for fw in UNRELATED_FRAMEWORKS:
                if fw in id_parts and fw not in query_tokens:
                    has_unrelated = True
                    break
            if has_unrelated:
                continue

            tf = self.doc_term_freqs[sid]
            doc_l = self.doc_len[sid]
            score = 0.0
            matched_terms = []

            for token in query_tokens:
                if token not in tf:
                    continue

                f = tf[token]
                n_t = self.df.get(token, 0)
                idf = math.log(1.0 + (self.N - n_t + 0.5) / (n_t + 0.5))
                denom = f + self.k1 * (1.0 - self.b + self.b * (doc_l / self.avgdl))
                term_score = idf * (f * (self.k1 + 1.0)) / denom

                if token in GENERIC_TERMS:
                    term_score *= 0.15

                score += term_score
                matched_terms.append(token)

            if norm_id in query_tokens:
                score += 10.0
            elif any(s in query_tokens for s in SYNONYMS.get(sid, [])):
                score += 5.0

            if matched_terms and all(m in GENERIC_TERMS for m in matched_terms) and not non_generic_query:
                score = 0.0

            if score > 0:
                scores.append((round(score, 2), sid, matched_terms))

        scores.sort(key=lambda x: x[0], reverse=True)
        return scores

_GLOBAL_INDEX = None

def get_index() -> BM25Index:
    global _GLOBAL_INDEX
    if _GLOBAL_INDEX is not None:
        return _GLOBAL_INDEX

    manifest_mtime = MANIFEST_PATH.stat().st_mtime if MANIFEST_PATH.exists() else 0
    if CACHE_FILE.exists():
        try:
            with open(CACHE_FILE, "rb") as f:
                cached_mtime, cached_index = pickle.load(f)
            if cached_mtime == manifest_mtime:
                _GLOBAL_INDEX = cached_index
                return _GLOBAL_INDEX
        except Exception:
            pass

    manifest = get_manifest()
    _GLOBAL_INDEX = BM25Index(manifest)
    try:
        CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(CACHE_FILE, "wb") as f:
            pickle.dump((manifest_mtime, _GLOBAL_INDEX), f)
    except Exception:
        pass
    return _GLOBAL_INDEX

def check_bundles(query: str) -> tuple[str, list[str]]:
    """Verifica se a tarefa se qualifica para um Bundle Coordenado de Skills."""
    tokens = set(tokenize(query))
    for b_id, b_meta in SKILL_BUNDLES.items():
        matches = sum(1 for trig in b_meta["triggers"] if trig in tokens)
        if matches >= b_meta["min_matches"]:
            return b_id, b_meta["skills"]
    return None, []

def route(prompt: str, top_k: int = 2, threshold: float = 4.0, explain: bool = False, category: str = None, block: str = None):
    # 1. Verifica se dispara um Bundle Coordenado
    bundle_id, bundle_skills = check_bundles(prompt)
    pinned = get_pinned()

    print(f"[*] Tarefa: '{prompt}'")
    if block:
        print(f"[*] Bloco Temático: '{block}'")
    elif category:
        print(f"[*] Filtro de Categoria: '{category}'")

    reset()

    activated = []
    if bundle_id:
        b_title = SKILL_BUNDLES[bundle_id]["title"]
        print(f"[BUNDLE] Combo Ativado: '{b_title}' -> {', '.join(bundle_skills)}")
        activated = add(bundle_skills)
        return {"bundle": bundle_id, "activated": activated, "pinned": list(pinned)}

    # 2. Roteamento BM25 por Relevância
    index = get_index()
    results = index.score(prompt, category_filter=category, block_filter=block)

    selected_results = [r for r in results if r[0] >= threshold][:top_k]
    selected_ids = [r[1] for r in selected_results]

    if selected_ids:
        print(f"[*] Roteando automaticamente para: {', '.join(selected_ids)}")
        activated = add(selected_ids)
    else:
        if pinned:
            print(f"[*] Nenhuma nova skill especializada requerida (mantidas {len(pinned)} fixadas).")
        else:
            print("[*] Nenhuma skill especializada requerida (modo base sem custo extra).")

    if explain:
        print("\n--- [EXPLAIN / BM25 RANKING] ---")
        if not selected_results:
            print("Nenhuma skill atingiu o threshold de ativação.")
        for score, sid, matches in results[:5]:
            meta = index.manifest.get(sid, {})
            cat = meta.get("thematic_block", meta.get("category", "tools"))
            status_str = "[SELECIONADA]" if sid in selected_ids else "[DESCARTADA]"
            print(f"  {status_str} Score: {score:5.2f} | ID: {sid:30} | Bloco: {cat:15} | Matches: {', '.join(matches)}")

    return {"bundle": None, "activated": activated, "pinned": list(pinned), "results": results[:5]}

def search(query: str, top_k: int = 10, category: str = None, block: str = None):
    index = get_index()
    results = index.score(query, category_filter=category, block_filter=block)
    label = f"no bloco '{block}'" if block else (f"na categoria '{category}'" if category else "")
    print(f"[*] Busca por: '{query}' {label}".strip())
    print(f"[*] Encontradas: {len(results)} skills compatíveis")
    output = []
    for score, sid, matches in results[:top_k]:
        meta = index.manifest.get(sid, {})
        blk = meta.get("thematic_block", "tools")
        desc = meta.get("description", "")[:90] + "..."
        print(f"  [{score:4.1f}] {sid:30} ({blk}) -> {desc}")
        output.append({"score": round(score, 2), "id": sid, "block": blk, "description": meta.get("description", ""), "matches": matches})
    return output

def status():
    manifest = get_manifest()
    pinned = get_pinned()
    print(f"[*] Total de skills no Vault: {len(manifest)}")
    if pinned:
        print(f"[*] Skills fixadas [PIN]: {', '.join(pinned)}")
    list_skills()

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Uso do Roteador de Skills BM25:")
        print("  python scripts/auto_route.py '<tarefa a executar>' [--explain] [--top-k N] [--block BLOCO] [--category CAT]")
        print("  python scripts/auto_route.py search '<termo>' [--block BLOCO] [--category CAT]")
        print("  python scripts/auto_route.py pin <id1> [id2...]")
        print("  python scripts/auto_route.py unpin <id1> [id2...]")
        print("  python scripts/auto_route.py status")
        print("  python scripts/auto_route.py reset")
        sys.exit(0)

    args = sys.argv[1:]
    cmd = args[0]

    if cmd == "status":
        status()
    elif cmd == "reset":
        reset()
    elif cmd == "pin":
        pin(args[1:])
    elif cmd == "unpin":
        unpin(args[1:])
    elif cmd == "search":
        q = args[1] if len(args) > 1 and not args[1].startswith("--") else ""
        cat = None
        block = None
        if "--category" in args:
            idx = args.index("--category")
            if idx + 1 < len(args):
                cat = args[idx + 1]
        if "--block" in args:
            idx = args.index("--block")
            if idx + 1 < len(args):
                block = args[idx + 1]
        search(q, category=cat, block=block)
    else:
        # Modo Roteamento
        explain = "--explain" in args
        category = None
        block = None
        top_k = 2

        if "--category" in args:
            idx = args.index("--category")
            if idx + 1 < len(args):
                category = args[idx + 1]
        if "--block" in args:
            idx = args.index("--block")
            if idx + 1 < len(args):
                block = args[idx + 1]
        if "--top-k" in args:
            idx = args.index("--top-k")
            if idx + 1 < len(args):
                top_k = int(args[idx + 1])

        clean_args = [a for a in args if not a.startswith("--") and a not in (category, block, str(top_k))]
        prompt = " ".join(clean_args)
        route(prompt, top_k=top_k, explain=explain, category=category, block=block)
