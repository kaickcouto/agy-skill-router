import os
import sys
import re
import json
import time
import base64
import urllib.request
import urllib.error
from pathlib import Path

# Suporte UTF-8 no Windows
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parent
CACHE_DIR = ROOT / ".agent"
COOLDOWN_FILE = CACHE_DIR / ".openrouter_cooldown"
COOLDOWN_SECONDS = 120

# Carrega .env
ENV_PATH = ROOT / ".env"
if ENV_PATH.exists():
    for line in ENV_PATH.read_text(encoding="utf-8-sig").splitlines():
        line = line.strip().lstrip("\ufeff")
        if "=" in line and not line.startswith("#"):
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())

API_KEY = os.environ.get("OPENROUTER_API_KEY")

# Tiers ordenados por velocidade real testada e suporte multimodal
TIER_1_FAST = [
    "inclusionai/ling-3.0-flash-vl:free",  # Multimodal (Visão + Texto) ~1.3s
    "nex-agi/nex-n2.5-mini:free",          # Ultra-rápido ~0.9s
    "nex-agi/nex-n2.5-pro:free"            # Raciocínio rápido ~1.1s
]

TIER_2_FALLBACK = [
    "poolside/laguna-s-2.1:free",          # Código / Refatoração
    "google/gemma-4-31b-it:free",          # Raciocínio profundo
    "nvidia/nemotron-3.5-lightning:free"   # Fallback aberto
]

SYSTEM_PROMPT = """Você é um pré-agente compilador de requisitos técnicos de software.
Sua missão é transformar a solicitação bruta do usuário em uma especificação técnica cirúrgica para o agente programador.
Se houver prints de tela, extraia os componentes de interface e fluxos visuais.
Responda SEM saudações e SEM introduções no formato estrito:

## [ESCOPO CIRÚRGICO]
- Arquivos/módulos exatos a criar ou modificar.

## [STACK & KEYWORDS]
- Tecnologias e termos-chave separados por vírgula (ex: supabase, postgres, react, tailwind, jwt, zod).

## [CONTRATO & VALIDAÇÕES]
- Entradas, retornos esperados, tratamento de erros e regras essenciais.

## [CHECKLIST DE IMPLEMENTAÇÃO]
1. Passo 1
2. Passo 2
3. Passo 3
"""

def is_in_cooldown() -> bool:
    """Verifica se o OpenRouter está em período de espera após erro 429."""
    if COOLDOWN_FILE.exists():
        try:
            ts = float(COOLDOWN_FILE.read_text(encoding="utf-8").strip())
            if time.time() - ts < COOLDOWN_SECONDS:
                return True
        except Exception:
            pass
    return False

def trigger_cooldown():
    """Ativa o Circuit Breaker por 2 minutos evitando travamento em loop no chat."""
    try:
        COOLDOWN_FILE.parent.mkdir(parents=True, exist_ok=True)
        COOLDOWN_FILE.write_text(str(time.time()), encoding="utf-8")
    except Exception:
        pass

def encode_image(image_path: str) -> str:
    p = Path(image_path)
    ext = p.suffix.lower().replace(".", "")
    if ext == "jpg":
        ext = "jpeg"
    with open(p, "rb") as f:
        b64 = base64.b64encode(f.read()).decode("utf-8")
    return f"data:image/{ext};base64,{b64}"

def extract_spec_data(raw_text: str, default_prompt: str) -> tuple[str, list[str]]:
    """Extrai especificação e palavras-chave suportando JSON ou Markdown estruturado."""
    text = raw_text.strip()
    
    # 1. Tenta extrair de JSON
    match_json = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    json_candidate = match_json.group(1) if match_json else text
    try:
        data = json.loads(json_candidate)
        if isinstance(data, dict) and ("keywords" in data or "scope" in data):
            keywords = [str(k).strip().lower() for k in data.get("keywords", []) if str(k).strip()]
            scope_lines = "\n".join(f"- {s}" for s in data.get("scope", []))
            checklist_lines = "\n".join(
                f"{idx}. {item}" if not re.match(r"^\d+\.", item) else item
                for idx, item in enumerate(data.get("checklist", []), 1)
            )
            spec = f"""## [ESCOPO CIRÚRGICO]\n{scope_lines or '- ' + default_prompt}\n\n## [CONTRATO & VALIDAÇÕES]\n{data.get('contract', 'Padrões do projeto.')}\n\n## [CHECKLIST DE IMPLEMENTAÇÃO]\n{checklist_lines or '1. Implementar demanda'}"""
            return spec, keywords
    except Exception:
        pass

    # 2. Extrai de Markdown com blocos bem definidos
    keywords = []
    kw_match = re.search(r"##\s*\[STACK & KEYWORDS\](.*?)(##|\Z)", text, re.DOTALL | re.IGNORECASE)
    if kw_match:
        kw_text = kw_match.group(1).strip()
        keywords = [k.strip().lower() for k in re.split(r"[,;\n\-•]+", kw_text) if len(k.strip()) > 1]

    # Limpa markdown puro
    if "## [ESCOPO" in text:
        return text, keywords

    # Fallback básico
    return text, keywords

def call_openrouter(prompt: str, image_path: str = None, system_prompt: str = None, max_tokens: int = 1000) -> dict:
    if is_in_cooldown():
        raise RuntimeError("OpenRouter em cooldown (rate limit 429 ativo). Bypass instantâneo para motor local.")

    if not API_KEY:
        raise ValueError("OPENROUTER_API_KEY não configurada no .env.")

    sys_p = system_prompt or SYSTEM_PROMPT
    content = [{"type": "text", "text": prompt}]
    if image_path and Path(image_path).exists():
        content.append({
            "type": "image_url",
            "image_url": {"url": encode_image(image_path)}
        })

    messages = [
        {"role": "system", "content": sys_p},
        {"role": "user", "content": content}
    ]

    last_error = None
    for tier in [TIER_1_FAST, TIER_2_FALLBACK]:
        payload = {
            "model": tier[0],
            "models": tier,
            "route": "fallback",
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": 0.1
        }
        req = urllib.request.Request(
            "https://openrouter.ai/api/v1/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {API_KEY}",
                "Content-Type": "application/json",
                "HTTP-Referer": "https://github.com/google/antigravity",
                "X-Title": "AGY Pre-Agent"
            }
        )
        try:
            with urllib.request.urlopen(req, timeout=12) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                model_used = data.get("model", tier[0])
                msg = data["choices"][0]["message"]
                raw_text = msg.get("content") or msg.get("reasoning") or ""

                spec, keywords = extract_spec_data(raw_text, prompt)
                return {
                    "model_used": model_used,
                    "spec": spec,
                    "keywords": keywords
                }
        except Exception as e:
            err_msg = str(e)
            if "429" in err_msg or "rate limit" in err_msg.lower():
                trigger_cooldown()
            last_error = e
            continue

    raise RuntimeError(f"Todos os tiers falharam: {last_error}")

def expand_query(query: str) -> list[str]:
    """Extrai termos técnicos e conceitos de demandas vagas usando TypeSafe AI (Tier 0) com fallback OpenRouter."""
    try:
        import typesafe_client
        res = typesafe_client.classify_task(query)
        if res and res.get("should_act") and res.get("gate_score", 0.0) >= 0.30:
            block = res.get("block", "")
            intent = res.get("intent", "")
            block_terms = {
                "core-database": ["database", "sql", "postgres", "supabase", "migrations"],
                "core-backend": ["backend", "api", "fastapi", "endpoints", "auth"],
                "core-frontend": ["frontend", "ui", "react", "tailwind", "components"],
                "quality-testing": ["testing", "vitest", "playwright", "unit", "e2e"],
                "cloud-devops": ["docker", "kubernetes", "containers", "ci", "deploy"],
                "data-ai-engine": ["excel", "xlsx", "pdf", "reports", "data"]
            }
            terms = block_terms.get(block, []) + ([intent] if intent else [])
            if terms:
                return terms[:6]
    except Exception:
        pass

    if is_in_cooldown():
        return []

    prompt = f"Gere de 4 a 6 termos técnicos para a demanda: '{query}'. Responda estritamente apenas palavras separadas por vírgula."
    try:
        data = call_openrouter(
            prompt,
            system_prompt="Você é um extrator de termos técnicos de software. Responda apenas termos técnicos separados por vírgula sem explicações.",
            max_tokens=150
        )
        raw = data.get("spec", "")
        terms = [t.strip().lower() for t in re.split(r'[,;\n\-•]+', raw) if len(t.strip()) > 1]
        clean_terms = []
        for t in terms:
            t_sub = re.sub(r'[^a-zA-Z0-9_\- ]', '', t).strip()
            if t_sub and len(t_sub) >= 3 and not any(w in t_sub for w in ["termo", "exemplo", "aqui", "resposta"]):
                clean_terms.append(t_sub)
        return clean_terms[:6]
    except Exception:
        return []

def pre_agent_decompose(task: str, image_path: str = None, auto_route_skills: bool = False, top_k: int = 3) -> dict:
    """Executa a decomposição técnica e correlação com o catálogo de skills do AGY."""
    sys.path.insert(0, str(SCRIPT_DIR))
    import auto_route
    import manage_skills

    # 1. Decomposição com IA (TypeSafe Jev como acelerador / OpenRouter multimodal / fallback local)
    res = None
    if not image_path:
        try:
            import typesafe_client
            ts_eval = typesafe_client.classify_task(task)
            if ts_eval and ts_eval.get("should_act") and ts_eval.get("gate_score", 0.0) >= 0.30:
                expanded = expand_query(task)
                keywords = list(set(auto_route.tokenize(task) + expanded))
                res = {
                    "model_used": "typesafe-jev-systemone",
                    "spec": f"## [ESCOPO CIRÚRGICO]\n- Tarefa: {task}\n- Domínio: {ts_eval.get('block')} (Confiança: {int(ts_eval.get('block_confidence', 1.0)*100)}%)\n- Intenção: {ts_eval.get('intent')}\n\n## [CONTRATO & VALIDAÇÕES]\n- Conformidade técnica com padrões do projeto e tipagem formal.\n\n## [CHECKLIST DE IMPLEMENTAÇÃO]\n1. Inspecionar arquivos e dependências no workspace\n2. Executar alterações cirúrgicas para '{task}'\n3. Validar execução e testes",
                    "keywords": keywords,
                    "typesafe_eval": ts_eval
                }
        except Exception:
            pass

    if not res:
        try:
            res = call_openrouter(task, image_path)
        except Exception as e:
            res = {
                "model_used": "offline-local",
                "spec": f"## [AVISO]\nBypass do OpenRouter ({e}). Decomposição via motor local.\n\n## [CHECKLIST]\n1. Executar demanda: '{task}'",
                "keywords": auto_route.tokenize(task)
            }

    # 2. Correlaciona com o Vault de Skills via BM25
    query = " ".join(res["keywords"]) if res["keywords"] else task
    matched_skills = []
    activated_skills = []

    try:
        index = auto_route.get_index()
        scores = index.score(query)[:top_k]
        matched_skills = [sid for score, sid, _ in scores if score >= 3.0]

        if auto_route_skills and matched_skills:
            activated_skills = manage_skills.add(matched_skills)
    except Exception:
        pass

    res["suggested_skills"] = matched_skills
    res["activated_skills"] = activated_skills
    return res

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="AGY Pre-Agent: Decompilador de requisitos com fallback gratuito")
    parser.add_argument("task", nargs="?", help="Descrição da demanda técnica")
    parser.add_argument("--image", "-i", help="Caminho opcional para print/mockup")
    parser.add_argument("--route", "-r", action="store_true", help="Ativa automaticamente as skills recomendadas em .agent/skills/")
    parser.add_argument("--json", "-j", action="store_true", help="Retorna saída estruturada em JSON")

    args = parser.parse_args()

    if not args.task:
        parser.print_help()
        sys.exit(0)

    result = pre_agent_decompose(args.task, image_path=args.image, auto_route_skills=args.route)

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"=== PRÉ-AGENTE AGY [Modelo: {result['model_used']}] ===\n")
        print(result["spec"])
        print("\n--- SKILLS AGY SUGERIDAS ---")
        if result["suggested_skills"]:
            print(f"Skills identificadas: {', '.join(result['suggested_skills'])}")
            if args.route:
                print(f"[*] Injetadas com sucesso em .agent/skills/: {', '.join(result['activated_skills'])}")
            else:
                print("[Dica] Para injetá-las automaticamente, rode com a flag --route ou -r")
        else:
            print("Nenhuma skill adicional necessária (modo base do AGY).")
