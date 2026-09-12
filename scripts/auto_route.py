import sys
import os
import re
import json
import math
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
            syn_tokens = [normalize(s) for s in SYNONYMS.get(sid, [])]

            # Frequência ponderada de termos
            tf = Counter()
            for t in id_tokens:
                tf[t] += 4.0
            for t in cat_tokens:
                tf[t] += 2.5
            for t in syn_tokens:
                tf[t] += 3.0
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

    def score(self, query: str, category_filter: str = None) -> list[tuple[float, str, list[str]]]:
        query_tokens = tokenize(query)
        if not query_tokens:
            return []

        # Identifica se a query é 100% genérica
        non_generic_query = [t for t in query_tokens if t not in GENERIC_TERMS]

        scores = []
        for sid, meta in self.manifest.items():
            if category_filter and meta.get("category") != category_filter:
                continue

            norm_id = normalize(sid)
            id_parts = set(norm_id.split("-"))

            # Penalidade para framework não relacionado que não está na query
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
                # IDF com suavização
                idf = math.log(1.0 + (self.N - n_t + 0.5) / (n_t + 0.5))
                # BM25 tf normalization
                denom = f + self.k1 * (1.0 - self.b + self.b * (doc_l / self.avgdl))
                term_score = idf * (f * (self.k1 + 1.0)) / denom

                # Se for termo genérico, amortece peso
                if token in GENERIC_TERMS:
                    term_score *= 0.15

                score += term_score
                matched_terms.append(token)

            # Bônus se houver match exato do nome ou de sinônimo forte
            if norm_id in query_tokens:
                score += 10.0
            elif any(s in query_tokens for s in SYNONYMS.get(sid, [])):
                score += 5.0

            # Se todos os matches forem termos genéricos e sem termos técnicos no prompt, anula
            if matched_terms and all(m in GENERIC_TERMS for m in matched_terms) and not non_generic_query:
                score = 0.0

            if score > 0:
                scores.append((round(score, 2), sid, matched_terms))

        scores.sort(key=lambda x: x[0], reverse=True)
        return scores

_GLOBAL_INDEX = None

def get_index() -> BM25Index:
    global _GLOBAL_INDEX
    if _GLOBAL_INDEX is None:
        manifest = get_manifest()
        _GLOBAL_INDEX = BM25Index(manifest)
    return _GLOBAL_INDEX

def route(prompt: str, top_k: int = 2, threshold: float = 4.0, explain: bool = False, category: str = None):
    index = get_index()
    results = index.score(prompt, category_filter=category)
    pinned = get_pinned()

    selected_results = [r for r in results if r[0] >= threshold][:top_k]
    selected_ids = [r[1] for r in selected_results]

    print(f"[*] Tarefa: '{prompt}'")
    if category:
        print(f"[*] Filtro de Categoria: '{category}'")

    reset()

    if selected_ids:
        print(f"[*] Roteando automaticamente para: {', '.join(selected_ids)}")
        add(selected_ids)
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
            cat = meta.get("category", "tools")
            status_str = "[SELECIONADA]" if sid in selected_ids else "[DESCARTADA]"
            print(f"  {status_str} Score: {score:5.2f} | ID: {sid:30} | Cat: {cat:12} | Matches: {', '.join(matches)}")

def search(query: str, top_k: int = 10, category: str = None):
    index = get_index()
    results = index.score(query, category_filter=category)
    print(f"[*] Busca por: '{query}'" + (f" na categoria '{category}'" if category else ""))
    print(f"[*] Encontradas: {len(results)} skills compatíveis")
    for score, sid, matches in results[:top_k]:
        meta = index.manifest.get(sid, {})
        cat = meta.get("category", "tools")
        desc = meta.get("description", "")[:90] + "..."
        print(f"  [{score:4.1f}] {sid:30} ({cat}) -> {desc}")

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
        print("  python scripts/auto_route.py '<tarefa a executar>' [--explain] [--top-k N] [--category CAT]")
        print("  python scripts/auto_route.py search '<termo>' [--category CAT]")
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
        q = args[1] if len(args) > 1 else ""
        cat = None
        if "--category" in args:
            idx = args.index("--category")
            if idx + 1 < len(args):
                cat = args[idx + 1]
        search(q, category=cat)
    else:
        # Modo Roteamento
        explain = "--explain" in args
        category = None
        top_k = 2

        if "--category" in args:
            idx = args.index("--category")
            if idx + 1 < len(args):
                category = args[idx + 1]
        if "--top-k" in args:
            idx = args.index("--top-k")
            if idx + 1 < len(args):
                top_k = int(args[idx + 1])

        clean_args = [a for a in args if not a.startswith("--") and a not in (category, str(top_k))]
        prompt = " ".join(clean_args)
        route(prompt, top_k=top_k, explain=explain, category=category)
