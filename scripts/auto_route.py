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

RULES_PATH = ROOT / "rules.json"

UNRELATED_FRAMEWORKS = set()
GENERIC_TERMS = set()
SYNONYMS = {}
SKILL_BUNDLES = {}
PRESETS = {}
MODULE_HINTS = {}
PATH_TRIGGERS = {}
BLOCK_KEYWORDS = {}
SKILL_AFFINITY = {}

def load_rules():
    global UNRELATED_FRAMEWORKS, GENERIC_TERMS, SYNONYMS, SKILL_BUNDLES, PRESETS, MODULE_HINTS, PATH_TRIGGERS, BLOCK_KEYWORDS, SKILL_AFFINITY
    if RULES_PATH.exists():
        try:
            with open(RULES_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
                UNRELATED_FRAMEWORKS = set(data.get("unrelated_frameworks", []))
                GENERIC_TERMS = set(data.get("generic_terms", []))
                SYNONYMS = data.get("synonyms", {})
                SKILL_BUNDLES = data.get("skill_bundles", {})
                PRESETS = data.get("presets", {})
                MODULE_HINTS = data.get("module_hints", {})
                PATH_TRIGGERS = data.get("path_triggers", {})
                BLOCK_KEYWORDS = data.get("block_keywords", {})
                SKILL_AFFINITY = data.get("skill_affinity", {})
                return
        except Exception:
            pass

load_rules()

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
            intent_tokens = tokenize(meta.get("call_intent", ""))
            trigger_tokens = [t for trig in meta.get("triggers", []) for t in tokenize(trig)]
            tech_tokens = [normalize(tech) for tech in meta.get("tech_stack", [])]
            desc_tokens = tokenize(meta.get("description", ""))
            tag_tokens = [normalize(t) for t in meta.get("tags", [])]
            cat_tokens = tokenize(meta.get("category", ""))
            block_tokens = tokenize(meta.get("thematic_block", ""))
            syn_tokens = [normalize(s) for s in SYNONYMS.get(sid, [])]

            tf = Counter()
            for t in id_tokens:
                tf[t] += 4.0
            for t in intent_tokens:
                tf[t] += 4.0
            for t in trigger_tokens:
                tf[t] += 3.5
            for t in tech_tokens:
                tf[t] += 3.0
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
            domain = meta.get("category") or meta.get("thematic_block")
            if category_filter and domain != category_filter:
                continue
            if block_filter and domain != block_filter:
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

    m_mtime = MANIFEST_PATH.stat().st_mtime if MANIFEST_PATH.exists() else 0
    r_mtime = RULES_PATH.stat().st_mtime if RULES_PATH.exists() else 0
    combined_mtime = (m_mtime, r_mtime)

    if CACHE_FILE.exists():
        try:
            with open(CACHE_FILE, "rb") as f:
                cached_mtime, cached_index = pickle.load(f)
            if cached_mtime == combined_mtime:
                _GLOBAL_INDEX = cached_index
                return _GLOBAL_INDEX
        except Exception:
            pass

    load_rules()
    manifest = get_manifest()
    _GLOBAL_INDEX = BM25Index(manifest)
    try:
        CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(CACHE_FILE, "wb") as f:
            pickle.dump((combined_mtime, _GLOBAL_INDEX), f)
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

def check_module_hints(query: str) -> tuple[str, list[str]]:
    """Identifica se a consulta menciona algum módulo específico do CMS/projeto."""
    tokens = set(tokenize(query))
    for mod_name, mod_data in MODULE_HINTS.items():
        if mod_name in tokens:
            return mod_data.get("service", mod_name), mod_data.get("skills", [])
    return None, []

def apply_preset(name: str) -> bool:
    load_rules()
    preset = PRESETS.get(name.lower())
    if not preset:
        print(f"[!] Preset '{name}' não encontrado. Disponíveis: {', '.join(PRESETS.keys())}")
        return False
    title = preset.get("title", name)
    skills_to_pin = preset.get("pinned", [])
    print(f"[*] Aplicando Preset: '{title}' ({preset.get('description', '')})")
    pin(skills_to_pin)
    return True

def detect_git_context() -> list[str]:
    """Inspeciona git status do workspace ativo para inferir tecnologias dos arquivos modificados (estilo Aider)."""
    try:
        from manage_skills import _resolve_workspace_base
        ws = _resolve_workspace_base()
        if not ws or not (ws / ".git").exists():
            return []
        import subprocess
        import fnmatch
        res = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=str(ws),
            capture_output=True,
            text=True,
            timeout=2
        )
        if res.returncode != 0 or not res.stdout.strip():
            return []
        
        detected_skills = []
        for line in res.stdout.splitlines()[:25]:
            parts = line.strip().split(maxsplit=1)
            if len(parts) == 2:
                file_path = parts[1].replace("\\", "/")
                file_name = Path(file_path).name
                for pattern, sids in PATH_TRIGGERS.items():
                    if fnmatch.fnmatch(file_name, pattern) or fnmatch.fnmatch(file_path, pattern):
                        detected_skills.extend(sids)
        seen = set()
        return [s for s in detected_skills if not (s in seen or seen.add(s))]
    except Exception:
        return []

def detect_path_in_prompt(prompt: str) -> list[str]:
    """Extrai extensões ou caminhos de arquivos mencionados diretamente no prompt (estilo Cursor)."""
    import fnmatch
    detected = []
    words = re.findall(r'[\w\.\-/\\_]+', prompt)
    for word in words:
        name = Path(word).name
        for pattern, sids in PATH_TRIGGERS.items():
            if fnmatch.fnmatch(name, pattern) or fnmatch.fnmatch(word, pattern):
                detected.extend(sids)
    seen = set()
    return [s for s in detected if not (s in seen or seen.add(s))]

def detect_primary_block(prompt: str) -> str | None:
    """Classifica o domínio temático principal (Two-Tier Routing) para eliminar ruído inter-stack."""
    tokens = set(tokenize(prompt))
    best_block = None
    best_matches = 0
    for block_name, keywords in BLOCK_KEYWORDS.items():
        matches = sum(1 for kw in keywords if kw in tokens)
        if matches > best_matches and matches >= 2:
            best_matches = matches
            best_block = block_name
    return best_block

def route(prompt: str, top_k: int = 2, threshold: float = 4.0, explain: bool = False, category: str = None, block: str = None):
    load_rules()
    pinned = get_pinned()
    already_pinned = set(pinned)

    # 1. Path-Triggered Context: Menção direta a arquivos no prompt (Cursor style)
    path_skills = detect_path_in_prompt(prompt)
    if path_skills:
        fresh_path = [s for s in path_skills if s not in already_pinned]
        if fresh_path:
            reset()
            selected = fresh_path[:top_k]
            print(f"[PATH-TRIGGER] Extensão/Arquivo detectado no prompt -> {', '.join(selected)}")
            activated = add(selected)
            return {"status": "path_trigger_match", "confidence": 10.0, "threshold": threshold, "skills": selected, "activated": activated, "pinned": list(pinned)}

    # 2. Verifica Módulo do Projeto (CMS Module Hints)
    mod_service, mod_skills = check_module_hints(prompt)
    if mod_service:
        reset()
        print(f"[MÓDULO CMS] Serviço Detectado: '{mod_service}' -> {', '.join(mod_skills)}")
        activated = add(mod_skills)
        return {"status": "module_match", "confidence": 10.0, "threshold": threshold, "module": mod_service, "activated": activated, "pinned": list(pinned)}

    # 3. Bundles Coordenados de Skills
    bundle_id, bundle_skills = check_bundles(prompt)
    if bundle_id:
        reset()
        b_title = SKILL_BUNDLES[bundle_id]["title"]
        print(f"[BUNDLE] Combo Ativado: '{b_title}' -> {', '.join(bundle_skills)}")
        activated = add(bundle_skills)
        return {"status": "bundle_match", "confidence": 10.0, "threshold": threshold, "bundle": bundle_id, "activated": activated, "pinned": list(pinned)}

    # 4. Two-Tier Routing: Dedução de Bloco Temático para eliminar ruído cruzado
    if not block and not category:
        inferred_block = detect_primary_block(prompt)
        if inferred_block:
            block = inferred_block
            print(f"[TWO-TIER] Domínio Classificado: '{block}'")

    print(f"[*] Tarefa: '{prompt}'")
    if block:
        print(f"[*] Bloco Temático: '{block}'")
    elif category:
        print(f"[*] Filtro de Categoria: '{category}'")

    # 5. Git-Aware Context: Detecta tecnologias ativas se o prompt for curto/vago (Aider style)
    git_skills = detect_git_context() if len(tokenize(prompt)) <= 4 else []
    if git_skills:
        fresh_git = [s for s in git_skills if s not in already_pinned]
        if fresh_git:
            print(f"[GIT-AWARE] Contexto deduzido dos arquivos modificados -> {', '.join(fresh_git[:2])}")

    reset()
    activated = []

    # 2. Roteamento BM25 por Relevância com Desempate de Colisão
    index = get_index()
    results = index.score(prompt, category_filter=category, block_filter=block)

    # Desempate determinístico para skills semanticamente parecidas:
    # Prioriza termos não-genéricos específicos e gatilhos explícitos
    def disambiguation_key(item):
        score, sid, matches = item
        specific_matches = len([m for m in matches if m not in GENERIC_TERMS])
        meta = index.manifest.get(sid, {})
        trig_matches = sum(1 for t in meta.get("triggers", []) if any(normalize(m) in normalize(t) for m in matches))
        return (score, specific_matches, trig_matches)

    def is_valid_selection(r):
        score, sid, matches = r
        if score < threshold:
            return False
        # Impede falsos positivos: rejeita se todos os matches forem termos genéricos/stopwords
        return any(m not in GENERIC_TERMS for m in matches)

    already_pinned = set(pinned)
    # Prioriza skills novas que ainda não estão fixadas/ativas, garantindo vagas do top_k para novas habilidades
    fresh_results = [r for r in results if is_valid_selection(r) and r[1] not in already_pinned]
    if fresh_results:
        # Aplica Matriz de Afinidade (Co-occurrence) para elevar a melhor companheira técnica
        primary_sid = fresh_results[0][1]
        companions = set(SKILL_AFFINITY.get(primary_sid, []))
        if len(fresh_results) > 1 and companions and top_k > 1:
            head = [fresh_results[0]]
            tail = sorted(fresh_results[1:], key=lambda x: (x[1] in companions, x[0]), reverse=True)
            selected_results = (head + tail)[:top_k]
        else:
            selected_results = fresh_results[:top_k]
    else:
        selected_results = [r for r in results if is_valid_selection(r)][:top_k]
    selected_ids = [r[1] for r in selected_results]

    if selected_ids:
        confidence = selected_results[0][0]
        status = "routed"
        print(f"[*] Roteando automaticamente para: {', '.join(selected_ids)} (Confiança: {confidence:.2f} >= {threshold})")
        activated = add(selected_ids)
    else:
        confidence = results[0][0] if results else 0.0
        # 3. Resgate por Expansão Semântica com Pré-Agente Gratuito
        try:
            import pre_agent
            print(f"[*] Limiar não atingido ({confidence:.2f} < {threshold}). Consultando expansão semântica gratuita...")
            exp_terms = pre_agent.expand_query(prompt)
            if exp_terms:
                exp_query = f"{prompt} {' '.join(exp_terms)}"
                exp_results = index.score(exp_query, category_filter=category, block_filter=block)
                fresh_exp = [r for r in exp_results if is_valid_selection(r) and r[1] not in already_pinned]
                selected_results = (fresh_exp if fresh_exp else [r for r in exp_results if is_valid_selection(r)])[:top_k]
                selected_ids = [r[1] for r in selected_results]
                if selected_ids:
                    confidence = selected_results[0][0]
                    status = "semantic_routed"
                    print(f"[*] Roteamento semântico resgatado para: {', '.join(selected_ids)} (Confiança: {confidence:.2f})")
                    activated = add(selected_ids)
        except Exception:
            pass

        if not selected_ids and git_skills:
            fresh_git = [s for s in git_skills if s not in already_pinned]
            if fresh_git:
                selected_ids = fresh_git[:top_k]
                status = "git_aware_match"
                confidence = 8.0
                print(f"[*] [GIT-AWARE] Roteando para skills dos arquivos modificados: {', '.join(selected_ids)}")
                activated = add(selected_ids)

        if not selected_ids:
            confidence = results[0][0] if results else 0.0
            status = "fallback_base_mode"
            if pinned:
                print(f"[*] Nenhuma skill atingiu o limiar de confiança ({confidence:.2f} < {threshold}). Fallback: modo base (mantidas {len(pinned)} fixadas).")
            else:
                print(f"[*] Nenhuma skill atingiu o limiar de confiança ({confidence:.2f} < {threshold}). Fallback: modo base sem custo extra.")

    if explain:
        print("\n--- [EXPLAIN / BM25 RANKING] ---")
        if not selected_results:
            print(f"Nenhuma skill atingiu o limiar de ativação ({threshold}). Encaminhado para fallback.")
        for score, sid, matches in results[:5]:
            meta = index.manifest.get(sid, {})
            cat = meta.get("thematic_block", meta.get("category", "tools"))
            if sid in selected_ids:
                status_str = "[SELECIONADA]"
            elif sid in already_pinned:
                status_str = "[JÁ FIXADA]  "
            else:
                status_str = "[DESCARTADA] "
            print(f"  {status_str} Score: {score:5.2f} | ID: {sid:30} | Bloco: {cat:15} | Matches: {', '.join(matches)}")

    return {
        "status": status,
        "confidence": round(confidence, 2),
        "threshold": threshold,
        "bundle": None,
        "activated": activated,
        "pinned": list(pinned),
        "results": results[:5]
    }

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

def info(skill_id: str) -> dict:
    manifest = get_manifest()
    meta = manifest.get(skill_id)
    if not meta:
        print(f"[!] Skill '{skill_id}' não encontrada no vault.")
        return None

    blk = meta.get("thematic_block", "geral")
    intent = meta.get("call_intent", "Sem intenção cadastrada.")
    triggers = meta.get("triggers", [])
    stack = meta.get("tech_stack", [])

    print("\n" + "=" * 65)
    print(f"  SKILL: {skill_id}")
    print(f"  BLOCO: {blk}")
    print("=" * 65)
    print(f"\n🎯 INTENÇÃO DE CHAMADA:")
    print(f"   {intent}")
    print(f"\n⚡ QUANDO CHAMAR (TRIGGERS DE DEMANDA):")
    if triggers:
        for t in triggers:
            print(f"   • {t}")
    else:
        print("   • Uso geral conforme documentação técnica.")
    if stack:
        print(f"\n🛠️ TECH STACK:")
        print(f"   {', '.join(stack)}")
    print("=" * 65 + "\n")
    return meta

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
        print("  python scripts/auto_route.py info <skill_id>")
        print("  python scripts/auto_route.py preset <nome|list>")
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
    elif cmd == "preset":
        if len(args) > 1:
            pname = args[1].lower()
            if pname == "list":
                load_rules()
                print("[*] Presets disponíveis:")
                for k, v in PRESETS.items():
                    print(f"  • {k:12} - {v.get('title')} ({', '.join(v.get('pinned', []))})")
            else:
                apply_preset(pname)
        else:
            print("Uso: python scripts/auto_route.py preset <nome|list>")
    elif cmd == "info":
        sid = args[1] if len(args) > 1 else ""
        if sid:
            info(sid)
        else:
            print("Uso: python scripts/auto_route.py info <skill_id>")
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

        if "--plan" in args or "--pre" in args:
            import pre_agent
            res = pre_agent.pre_agent_decompose(prompt, auto_route_skills=True, top_k=top_k)
            print(f"=== PRÉ-AGENTE AGY [Modelo: {res['model_used']}] ===\n")
            print(res["spec"])
            print("\n--- SKILLS AGY ATIVADAS ---")
            print(f"[*] Injetadas em .agent/skills/: {', '.join(res['activated_skills']) if res['activated_skills'] else 'Nenhuma (modo base)'}")
            sys.exit(0)

        route(prompt, top_k=top_k, explain=explain, category=category, block=block)
