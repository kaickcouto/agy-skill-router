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
from manage_skills import add, reset, list_skills, pin, unpin, get_pinned, get_manifest, init_skill, lint_skill, import_skill

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
QUALITY_TIERS = {}
INTENT_VERBS = {}

def load_rules():
    global UNRELATED_FRAMEWORKS, GENERIC_TERMS, SYNONYMS, SKILL_BUNDLES, PRESETS, MODULE_HINTS, PATH_TRIGGERS, BLOCK_KEYWORDS, SKILL_AFFINITY, QUALITY_TIERS, INTENT_VERBS
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
                QUALITY_TIERS = data.get("quality_tiers", {})
                INTENT_VERBS = data.get("intent_verbs", {})
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

        # Pré-computação de bônus de intenção e tiers fora do loop (0ms overhead)
        intent_bonuses = {}
        for intent_key, intent_data in INTENT_VERBS.items():
            v_tokens = [normalize(v) for v in intent_data.get("verbs", [])]
            if any(v in query_tokens for v in v_tokens):
                for psid in intent_data.get("preferred_skills", []):
                    b_score, b_intents = intent_bonuses.get(psid, (0.0, []))
                    intent_bonuses[psid] = (b_score + 3.5, b_intents + [f"intent:{intent_key}"])

        gold_skills = set(QUALITY_TIERS.get("gold", {}).get("skills", []))
        silver_skills = set(QUALITY_TIERS.get("silver", {}).get("skills", []))
        gold_mult = QUALITY_TIERS.get("gold", {}).get("multiplier", 1.35)
        silver_mult = QUALITY_TIERS.get("silver", {}).get("multiplier", 1.15)

        scores = []
        for sid, meta in self.manifest.items():
            domain = meta.get("thematic_block") or meta.get("category")
            if category_filter and domain != category_filter:
                continue
            norm_id = normalize(sid)
            if block_filter:
                allowed_blocks = block_filter if isinstance(block_filter, (list, tuple, set)) else [block_filter]
                if domain not in allowed_blocks and sid not in intent_bonuses and norm_id not in query_tokens:
                    continue

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

            # Bonus por Alinhamento de Verbo de Intenção
            if sid in intent_bonuses:
                b_score, b_intents = intent_bonuses[sid]
                score += b_score
                matched_terms.extend(b_intents)

            if matched_terms and all(m in GENERIC_TERMS for m in matched_terms) and not non_generic_query:
                score = 0.0

            if score > 0:
                # Multiplicador por Nível Qualitativo (Quality Tier Boost)
                if sid in gold_skills:
                    score *= gold_mult
                elif sid in silver_skills:
                    score *= silver_mult

                scores.append((round(score, 2), sid, matched_terms))

        scores.sort(key=lambda x: x[0], reverse=True)
        return scores

_GLOBAL_INDEX = None
_CACHED_MTIME = None

def _get_custom_mtime() -> float:
    c_path = ROOT / "skills_custom"
    if not c_path.exists():
        return 0.0
    mtimes = [c_path.stat().st_mtime]
    for skill_file in c_path.glob("*/SKILL.md"):
        try:
            mtimes.append(skill_file.stat().st_mtime)
        except OSError:
            pass
    return max(mtimes)

def get_index() -> BM25Index:
    global _GLOBAL_INDEX, _CACHED_MTIME

    m_mtime = MANIFEST_PATH.stat().st_mtime if MANIFEST_PATH.exists() else 0
    r_mtime = RULES_PATH.stat().st_mtime if RULES_PATH.exists() else 0
    c_mtime = _get_custom_mtime()
    combined_mtime = (m_mtime, r_mtime, c_mtime)

    if _GLOBAL_INDEX is not None and _CACHED_MTIME == combined_mtime:
        return _GLOBAL_INDEX

    if CACHE_FILE.exists():
        try:
            with open(CACHE_FILE, "rb") as f:
                cached_mtime, cached_index = pickle.load(f)
            if cached_mtime == combined_mtime:
                _GLOBAL_INDEX = cached_index
                _CACHED_MTIME = combined_mtime
                return _GLOBAL_INDEX
        except Exception:
            pass

    load_rules()
    manifest = get_manifest()
    _GLOBAL_INDEX = BM25Index(manifest)
    _CACHED_MTIME = combined_mtime
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
                raw_path = parts[1]
                if " -> " in raw_path:
                    raw_path = raw_path.split(" -> ", 1)[1]
                file_path = raw_path.strip().strip('"').replace("\\", "/")
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

def detect_primary_block(prompt: str) -> str | list[str] | None:
    """Classifica o domínio temático principal (Two-Tier Routing) com TypeSafe AI (Jev) e fallback heurístico."""
    try:
        import typesafe_client
        res = typesafe_client.classify_task(prompt)
        if res and res.get("should_act"):
            block_map = {
                "core-database": ["database"],
                "core-backend": ["backend"],
                "core-frontend": ["frontend", "design-media"],
                "quality-testing": ["testing"],
                "cloud-devops": ["devops", "cloud-devops"],
                "data-ai-engine": ["data-ai", "productivity"]
            }
            if res.get("is_multistack") and res.get("active_blocks"):
                flattened = []
                for b in res["active_blocks"]:
                    targets = block_map.get(b, [])
                    if isinstance(targets, list):
                        flattened.extend(targets)
                    elif targets:
                        flattened.append(targets)
                if len(flattened) >= 2:
                    return list(dict.fromkeys(flattened))
            if res.get("block_confidence", 0.0) >= 0.70:
                block = res.get("block")
                mapped = block_map.get(block)
                if mapped:
                    return mapped
    except Exception:
        pass

    tokens = set(tokenize(prompt))
    best_block = None
    best_matches = 0
    for block_name, keywords in BLOCK_KEYWORDS.items():
        matches = sum(1 for kw in keywords if kw in tokens)
        if matches > best_matches and matches >= 2:
            best_matches = matches
            best_block = block_name

    if best_block == "data-ai":
        return ["data-ai", "productivity"]
    if best_block == "devops":
        return ["devops", "cloud-devops"]
    if best_block == "frontend":
        return ["frontend", "design-media"]
    return best_block

def route(prompt: str, top_k: int = 2, threshold: float = 4.0, explain: bool = False, category: str = None, block: str = None):
    load_rules()
    pinned = get_pinned()
    already_pinned = set(pinned)

    # 0. Early Exit: Prompt vazio ou só espaços
    if not prompt or not str(prompt).strip():
        return {
            "status": "empty_prompt",
            "confidence": 0.0,
            "threshold": threshold,
            "skills": [],
            "activated": [],
            "pinned": list(pinned)
        }

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
        else:
            # Todas as skills do caminho já estão fixadas/ativas
            return {"status": "already_satisfied_by_pinned", "confidence": 10.0, "threshold": threshold, "skills": path_skills, "activated": [], "pinned": list(pinned)}

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
    # Prioriza tiers qualitativos, alinhamento de intenção, termos não-genéricos específicos e gatilhos explícitos
    gold_set = set(QUALITY_TIERS.get("gold", {}).get("skills", []))
    silver_set = set(QUALITY_TIERS.get("silver", {}).get("skills", []))

    def disambiguation_key(item):
        score, sid, matches = item
        specific_matches = len([m for m in matches if m not in GENERIC_TERMS])
        meta = index.manifest.get(sid, {})
        trig_matches = sum(1 for t in meta.get("triggers", []) if any(normalize(m) in normalize(t) for m in matches))
        tier_weight = 2 if sid in gold_set else (1 if sid in silver_set else 0)
        has_intent = 1 if any(m.startswith("intent:") for m in matches) else 0
        return (round(score, 1), tier_weight, has_intent, trig_matches, specific_matches)

    results.sort(key=disambiguation_key, reverse=True)

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

    shortlist_rejected = False
    if selected_ids:
        # Padrão Oficial TypeSafe: Verificação de Shortlist com Jev para descarte de falsos positivos
        try:
            import typesafe_client
            winner, fits_map, approved = typesafe_client.verify_shortlist_fit(prompt, selected_ids, index.manifest)
            if not approved:
                print(f"[*] [TYPESAFE-VERIFY] Shortlist descartado por falta de aderência ({fits_map}).")
                selected_ids = []
                shortlist_rejected = True
            else:
                selected_ids = [sid for sid in selected_ids if sid in approved]
                if winner and winner in selected_ids and selected_ids[0] != winner:
                    selected_ids.remove(winner)
                    selected_ids.insert(0, winner)
        except Exception:
            pass

    if selected_ids:
        score_lookup = {sid: sc for sc, sid, _ in (results or [])}
        confidence = score_lookup.get(selected_ids[0], selected_results[0][0])
        status = "routed"
        print(f"[*] Roteando automaticamente para: {', '.join(selected_ids)} (Confiança: {confidence:.2f} >= {threshold})")
        activated = add(selected_ids)
    else:
        confidence = results[0][0] if results else 0.0
        # 3. Resgate por Expansão Semântica com Pré-Agente Gratuito
        if not shortlist_rejected:
            try:
                import typesafe_client
                ts_check = typesafe_client.classify_task(prompt)
                if ts_check and (not ts_check.get("should_act") or ts_check.get("block") == "general-tools"):
                    raise ValueError("Ação não requerida ou código genérico.")
                import pre_agent
                if results and results[0][0] >= threshold:
                    print(f"[*] Termos específicos não detectados nos resultados principais. Consultando expansão semântica gratuita...")
                else:
                    print(f"[*] Limiar não atingido ({confidence:.2f} < {threshold}). Consultando expansão semântica gratuita...")
                exp_terms = pre_agent.expand_query(prompt)
                if exp_terms:
                    exp_query = f"{prompt} {' '.join(exp_terms)}"
                    exp_results = index.score(exp_query, category_filter=category, block_filter=block)
                    fresh_exp = [r for r in exp_results if is_valid_selection(r) and r[1] not in already_pinned]
                    selected_results = (fresh_exp if fresh_exp else [r for r in exp_results if is_valid_selection(r)])[:top_k]
                    selected_ids = [r[1] for r in selected_results]
                    if selected_ids:
                        # Verificação rigorosa com TypeSafe no resgate semântico
                        try:
                            winner, fits_map, approved = typesafe_client.verify_shortlist_fit(prompt, selected_ids, index.manifest)
                            if not approved:
                                selected_ids = []
                            else:
                                selected_ids = [sid for sid in selected_ids if sid in approved]
                                if winner and winner in selected_ids and selected_ids[0] != winner:
                                    selected_ids.remove(winner)
                                    selected_ids.insert(0, winner)
                        except Exception:
                            pass
                    if selected_ids:
                        score_lookup = {sid: sc for sc, sid, _ in (exp_results or [])}
                        confidence = score_lookup.get(selected_ids[0], selected_results[0][0])
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
        "skills": selected_ids,
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
        print("  python scripts/auto_route.py init <nome> [descrição]")
        print("  python scripts/auto_route.py lint <nome|caminho>")
        print("  python scripts/auto_route.py import <owner/repo[@subpasta]> [--skill pasta] [--name nome]")
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
    elif cmd == "init":
        if len(args) > 1:
            init_skill(args[1], " ".join(args[2:]) if len(args) > 2 else None)
        else:
            print("Uso: python scripts/auto_route.py init <nome-da-skill> [descrição]")
    elif cmd == "lint":
        if len(args) > 1:
            lint_skill(args[1])
        else:
            print("Uso: python scripts/auto_route.py lint <nome-da-skill>")
    elif cmd == "import":
        if len(args) > 1:
            spec = args[1]
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
            print("Uso: python scripts/auto_route.py import <owner/repo[@subpasta]> [--skill subpasta] [--name nome]")
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

        skip_next = False
        clean_args = []
        for i, a in enumerate(args):
            if skip_next:
                skip_next = False
                continue
            if a in ("--category", "--block", "--top-k"):
                skip_next = True
                continue
            if a in ("--explain", "--plan", "--pre"):
                continue
            clean_args.append(a)
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
