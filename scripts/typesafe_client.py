import os
import sys
import time
import json
import hashlib
import re
import unicodedata
import urllib.request
import urllib.error
from pathlib import Path
from typing import Any

# Suporte UTF-8 no Windows
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

ROOT = Path(__file__).resolve().parent.parent

# Cache de dois níveis: In-memory (0ms) + Disco compartilhado entre processos (0.5ms)
_MEM_CACHE: dict[str, tuple[float, dict]] = {}
CACHE_FILE = ROOT / ".agent" / ".typesafe_cache.json"
TELEMETRY_FILE = ROOT / ".agent" / "telemetry.jsonl"
CACHE_TTL_SECONDS = 60.0

def get_api_key() -> str | None:
    key = os.environ.get("TYPESAFE_API_KEY")
    if key:
        return key.strip()
    env_path = ROOT / ".env"
    if env_path.exists():
        try:
            for line in env_path.read_text(encoding="utf-8-sig").splitlines():
                line = line.strip().lstrip("\ufeff")
                if line.startswith("TYPESAFE_API_KEY="):
                    _, v = line.split("=", 1)
                    val = v.strip().strip("'\"")
                    if val:
                        os.environ["TYPESAFE_API_KEY"] = val
                        return val
        except Exception:
            pass
    return None

def _normalize_text(text: str) -> str:
    norm = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("utf-8").lower()
    # Preserva símbolos técnicos de linguagens/ferramentas (+, #, ., -) e remove pontuação puramente sintática
    norm = re.sub(r'[^\w\s\+#\.\-]', ' ', norm)
    return ' '.join(norm.split())

def _cache_key(state: Any, questions: dict) -> str:
    norm_state = state
    if isinstance(state, dict):
        norm_state = {k: (_normalize_text(v) if isinstance(v, str) else v) for k, v in state.items()}
    elif isinstance(state, str):
        norm_state = _normalize_text(state)
    raw = f"{json.dumps(norm_state, sort_keys=True, default=str)}::{json.dumps(questions, sort_keys=True, default=str)}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()

def log_telemetry(event: str, details: dict):
    try:
        TELEMETRY_FILE.parent.mkdir(parents=True, exist_ok=True)
        # Rotação simples: se o log exceder 1MB, mantém os 2000 eventos mais recentes
        if TELEMETRY_FILE.exists() and TELEMETRY_FILE.stat().st_size > 1_000_000:
            try:
                old_lines = TELEMETRY_FILE.read_text(encoding="utf-8").splitlines()
                TELEMETRY_FILE.write_text("\n".join(old_lines[-2000:]) + "\n", encoding="utf-8")
            except Exception:
                pass
        entry = {
            "ts": time.time(),
            "event": event,
            **details
        }
        with open(TELEMETRY_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception:
        pass


def _get_cached_answer(ckey: str) -> dict | None:
    now = time.time()
    # 1. Checa memória local
    if ckey in _MEM_CACHE:
        ts, ans = _MEM_CACHE[ckey]
        if now - ts < CACHE_TTL_SECONDS:
            return ans

    # 2. Checa cache em disco compartilhado entre subprocessos (Hook AGY <-> CLI)
    if CACHE_FILE.exists():
        try:
            data = json.loads(CACHE_FILE.read_text(encoding="utf-8"))
            entry = data.get(ckey)
            if entry and now - entry.get("ts", 0) < CACHE_TTL_SECONDS:
                ans = entry.get("ans")
                _MEM_CACHE[ckey] = (entry["ts"], ans)
                return ans
        except Exception:
            pass
    return None

def _save_cached_answer(ckey: str, answers: dict):
    now = time.time()
    _MEM_CACHE[ckey] = (now, answers)
    try:
        CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
        data = {}
        if CACHE_FILE.exists():
            try:
                data = json.loads(CACHE_FILE.read_text(encoding="utf-8"))
            except Exception:
                data = {}
        # Pruning de entradas expiradas há mais de 5 minutos
        data = {k: v for k, v in data.items() if now - v.get("ts", 0) < 300}
        data[ckey] = {"ts": now, "ans": answers}
        tmp_file = CACHE_FILE.with_suffix(f".tmp.{os.getpid()}")
        tmp_file.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        try:
            os.replace(tmp_file, CACHE_FILE)
        except Exception:
            if tmp_file.exists():
                tmp_file.unlink()
    except Exception:
        pass

def evaluate_systemone(state: str | dict | list, questions: dict, timeout: float = 1.8) -> dict | None:
    """Executa inferência com cache multi-processo e timeout rápido de 1.8s."""
    api_key = get_api_key()
    if not api_key:
        return None

    ckey = _cache_key(state, questions)
    cached = _get_cached_answer(ckey)
    if cached is not None:
        log_telemetry("systemone_eval", {"cached": True, "latency_ms": 0.0, "tokens_saved": 350})
        return cached

    payload = {
        "state": state,
        "model": "jev-latest",
        "questions": questions
    }

    req = urllib.request.Request(
        "https://api.typesafe.ai/v1/systemone",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "User-Agent": "AGY-Skill-Router/1.0"
        }
    )

    t0 = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            answers = data.get("answers", {})
            _save_cached_answer(ckey, answers)
            latency = (time.perf_counter() - t0) * 1000.0
            log_telemetry("systemone_eval", {"cached": False, "latency_ms": round(latency, 2), "tokens_used": 120})
            return answers
    except Exception as err:
        log_telemetry("systemone_error", {"error": str(err)})
        return None

def classify_task(prompt: str) -> dict | None:
    """Padrão Oficial: Combina 3-Noul Gate, Bloco Temático Bimodal, Intenção e Guardrails (Fan-Out)."""
    clean_prompt = prompt.strip()
    if len(clean_prompt) < 4:
        return None

    questions = {
        "acts_on_system": {
            "type": "noul",
            "instructions": "Is the assistant being asked to act on files, code, database, tools or repositories, rather than only explain or advise?"
        },
        "documented_procedure": {
            "type": "noul",
            "instructions": "Would a careful expert answering this consult a specific documented procedure or set of commands, rather than answering from general understanding?"
        },
        "prose_suffices": {
            "type": "noul",
            "instructions": "Could a knowledgeable generalist fully satisfy this request in plain prose, with no code changes, no tools, and no documentation?"
        },
        "is_destructive": {
            "type": "noul",
            "instructions": "Does the request ask to delete, drop, wipe, prune, truncate, or destroy existing files, database tables, or git history?"
        },
        "is_ambiguous": {
            "type": "noul",
            "instructions": "Is the user request so vague, ambiguous, or incomplete that an assistant cannot execute it reliably without asking clarifying questions first?"
        },
        "thematic_block": {
            "type": "choice",
            "instructions": "Which technical domain is the primary focus of this request?",
            "criteria": {
                "core-database": "SQL, PostgreSQL, Supabase, migrations, database schemas, tables, RLS",
                "core-backend": "APIs, FastAPI, Python backend, REST endpoints, JWT auth, routes",
                "core-frontend": "React, Tailwind CSS, UI components, HTML, visual design, frontend",
                "quality-testing": "Vitest, Playwright, Cypress, E2E tests, unit tests, QA, mocking",
                "cloud-devops": "Docker, Kubernetes, containers, CI/CD, deployment, ingress",
                "data-ai-engine": "Excel, spreadsheets, XLSX, PDF generation, data processing, scrapers",
                "general-tools": "Generic programming question or general development tool"
            }
        },
        "intent": {
            "type": "choice",
            "instructions": "What is the primary action requested?",
            "criteria": {
                "create": "Build or add new feature, table, component, endpoint or test",
                "refactor": "Refactor, simplify, clean up or improve existing code",
                "optimize": "Improve performance, speed, query optimization or caching",
                "fix_bug": "Fix error, bug, broken layout or crash",
                "test": "Write or verify tests"
            }
        }
    }

    # Estado estruturado conforme concepts/state.md
    state_payload = {
        "request": clean_prompt
    }

    answers = evaluate_systemone(state_payload, questions, timeout=1.8)
    if not answers:
        return None

    act_score = answers.get("acts_on_system", {}).get("noul", 0.5)
    doc_score = answers.get("documented_procedure", {}).get("noul", 0.5)
    prose_score = answers.get("prose_suffices", {}).get("noul", 0.5)
    gate_score = (act_score + doc_score + (1.0 - prose_score)) / 3.0

    dest_score = answers.get("is_destructive", {}).get("noul", 0.0)
    amb_score = answers.get("is_ambiguous", {}).get("noul", 0.0)
    token_saving = (prose_score >= 0.70 and act_score < 0.35)

    block_ans = answers.get("thematic_block", {})
    intent_ans = answers.get("intent", {})

    # Análise Bimodal de Probabilidades (confidence.md) para detectar tarefas Multi-Stack
    probs = block_ans.get("probabilities", {})
    sorted_probs = sorted(probs.items(), key=lambda x: -x[1])
    top_block, top_p = sorted_probs[0] if sorted_probs else ("general-tools", 1.0)
    second_block, second_p = sorted_probs[1] if len(sorted_probs) > 1 else ("", 0.0)

    # Multi-stack: quando os dois maiores blocos somam >= 0.70 e o segundo bloco tem peso relevante (>= 0.25)
    is_multistack = (top_p + second_p >= 0.70) and (second_p >= 0.25) and (top_block != "general-tools") and (second_block != "general-tools")
    active_blocks = [top_block, second_block] if is_multistack else [top_block]

    return {
        "gate_score": round(gate_score, 2),
        "should_act": gate_score >= 0.30,
        "prose_suffices": round(prose_score, 2),
        "acts_on_system": round(act_score, 2),
        "token_saving_recommended": token_saving,
        "is_destructive": dest_score >= 0.60,
        "destructive_score": round(dest_score, 2),
        "is_ambiguous": amb_score >= 0.60,
        "ambiguity_score": round(amb_score, 2),
        "block": top_block,
        "block_confidence": round(block_ans.get("confidence", 0.0), 2),
        "probabilities": probs,
        "is_multistack": is_multistack,
        "active_blocks": active_blocks,
        "intent": intent_ans.get("choice", "create"),
        "intent_confidence": round(intent_ans.get("confidence", 0.0), 2)
    }

def get_skill_excerpt(sid: str, manifest: dict, max_chars: int = 700) -> str:
    """Carrega o excerpt real de SKILL.md (Progressive Disclosure - skill_suggestion.md)."""
    meta = manifest.get(sid, {})
    target = meta.get("target", sid)

    # Busca em skills_custom ou skills_vault
    candidates = [
        ROOT / "skills_custom" / sid / "SKILL.md",
        ROOT / "skills_vault" / target / "SKILL.md",
        ROOT / "skills_vault" / sid / "SKILL.md"
    ]
    for p in candidates:
        if p.exists():
            try:
                txt = p.read_text(encoding="utf-8", errors="ignore")
                # Pula frontmatter YAML se houver
                if txt.startswith("---"):
                    parts = txt.split("---", 2)
                    if len(parts) >= 3:
                        txt = parts[2].strip()
                # Remove quebras extras
                clean_lines = [l.strip() for l in txt.splitlines() if l.strip() and not l.startswith("#")]
                return " ".join(clean_lines)[:max_chars]
            except Exception:
                pass
    return meta.get("description", meta.get("call_intent", sid))[:max_chars]

def verify_shortlist_fit(prompt: str, candidate_ids: list[str], manifest: dict) -> tuple[str | None, dict[str, float], list[str]]:
    """Progressive Disclosure: Injeta excerpt de SKILL.md e filtra aprovados com fit >= 0.30 (Cookbook Oficial)."""
    if not candidate_ids:
        return None, {}, []

    shortlist = candidate_ids[:4]
    criteria = {}
    questions = {}

    for sid in shortlist:
        meta_desc = manifest.get(sid, {}).get("description", "")[:120]
        excerpt = get_skill_excerpt(sid, manifest, max_chars=700)
        full_context = f"{meta_desc} — {excerpt}" if excerpt and excerpt != meta_desc else meta_desc
        criteria[sid] = full_context[:800]
        questions[f"fits::{sid}"] = {
            "type": "noul",
            "instructions": f"Does the skill '{sid}' do the specific task the user is asking for? Skill documentation: {criteria[sid]}"
        }

    if len(shortlist) > 1:
        questions["which"] = {
            "type": "choice",
            "instructions": "Exactly one of these candidate skills is the right one to load for the user's latest request. Which one? Read what each actually does, not just its name.",
            "criteria": criteria
        }

    # Estado estruturado
    state_payload = {"request": prompt.strip()}

    answers = evaluate_systemone(state_payload, questions, timeout=2.0)
    if not answers:
        return candidate_ids[0], {}, candidate_ids

    fits_scores = {}
    for sid in shortlist:
        fits_scores[sid] = round(answers.get(f"fits::{sid}", {}).get("noul", 0.0), 2)

    best_fit = max(fits_scores.values()) if fits_scores else 0.0
    winner = answers.get("which", {}).get("choice") if "which" in answers else shortlist[0]

    # Limiar Oficial do Cookbook skill_suggestion.md: Rejeição total se nada atingir 0.30
    if best_fit < 0.30:
        return None, fits_scores, []

    # Retorna apenas os candidatos cujo fit individual seja satisfatório (>= 0.30)
    approved = [sid for sid in shortlist if fits_scores.get(sid, 0.0) >= 0.30]
    if winner and winner not in approved and approved:
        winner = approved[0]

    return winner, fits_scores, approved
