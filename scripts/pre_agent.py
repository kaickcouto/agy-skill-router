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

# Carrega .env
ENV_PATH = ROOT / ".env"
if ENV_PATH.exists():
    for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if "=" in line and not line.startswith("#"):
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())

API_KEY = os.environ.get("OPENROUTER_API_KEY")

# Tiers ordenados por velocidade real testada (< 1.5s) e suporte multimodal
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
Sua missão é decompor o pedido bruto do usuário em uma especificação técnica cirúrgica para o agente programador executar sem desperdiçar tokens com dúvidas.
Se houver print/imagem, extraia os componentes de tela e fluxos visuais.
Responda SEM saudações e SEM introduções no formato estrito:

## [ESCOPO CIRÚRGICO]
- Arquivos/módulos exatos a criar ou modificar.

## [STACK & KEYWORDS]
- Tecnologias e termos-chave separados por vírgula (ex: supabase, postgres, react, tailwind, jwt, zod, test).

## [CONTRATO & VALIDAÇÕES]
- Entradas, retornos esperados, tratamento de erros e regras de negócio.

## [CHECKLIST DE IMPLEMENTAÇÃO]
1. Passo 1
2. Passo 2
3. Passo 3
"""

def encode_image(image_path: str) -> str:
    p = Path(image_path)
    ext = p.suffix.lower().replace(".", "")
    if ext == "jpg":
        ext = "jpeg"
    with open(p, "rb") as f:
        b64 = base64.b64encode(f.read()).decode("utf-8")
    return f"data:image/{ext};base64,{b64}"

def call_openrouter(prompt: str, image_path: str = None, system_prompt: str = None, max_tokens: int = 800) -> dict:
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
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                model_used = data.get("model", tier[0])
                msg = data["choices"][0]["message"]
                raw_text = msg.get("content") or msg.get("reasoning") or ""

                # Extrai palavras-chave do bloco STACK & KEYWORDS
                keywords = []
                match = re.search(r"##\s*\[STACK & KEYWORDS\](.*?)(##|\Z)", raw_text, re.DOTALL | re.IGNORECASE)
                if match:
                    kw_text = match.group(1).strip()
                    keywords = [k.strip() for k in re.split(r"[,;\n\-•]+", kw_text) if k.strip() and len(k.strip()) > 1]

                return {
                    "model_used": model_used,
                    "spec": raw_text.strip(),
                    "keywords": keywords
                }
        except Exception as e:
            last_error = e
            continue

    raise RuntimeError(f"Todos os tiers falharam: {last_error}")

def expand_query(query: str) -> list[str]:
    """Extrai termos técnicos e conceitos de demandas vagas ou informais usando IA gratuita."""
    prompt = f"Gere de 4 a 6 termos técnicos, ferramentas e bibliotecas específicas para atender a seguinte necessidade de desenvolvimento: '{query}'. Responda estritamente apenas os termos técnicos separados por vírgula."
    try:
        data = call_openrouter(
            prompt,
            system_prompt="Você é um extrator de termos técnicos de software. Responda apenas termos técnicos separados por vírgula sem explicações.",
            max_tokens=250
        )
        raw = data.get("spec", "")
        terms = [t.strip().lower() for t in re.split(r'[,;\n\-•]+', raw) if len(t.strip()) > 1]
        clean_terms = []
        for t in terms:
            t_sub = re.sub(r'[^a-zA-Z0-9_\- ]', '', t).strip()
            if t_sub and len(t_sub) >= 3 and not any(w in t_sub for w in ["termo", "exemplo", "aqui", "resposta", "analis"]):
                clean_terms.append(t_sub)
        return clean_terms[:6]
    except Exception:
        return []

def pre_agent_decompose(task: str, image_path: str = None, auto_route_skills: bool = False, top_k: int = 3) -> dict:
    """Executa a decomposição via OpenRouter e correlaciona com o catálogo de skills do AGY."""
    sys.path.insert(0, str(SCRIPT_DIR))
    import auto_route
    import manage_skills

    # 1. Decomposição com IA gratuita
    try:
        res = call_openrouter(task, image_path)
    except Exception as e:
        # Fallback offline gracioso se não houver internet ou cota
        res = {
            "model_used": "offline-heuristic",
            "spec": f"## [AVISO]\nFalha no OpenRouter ({e}). Decomposição via heurística local.\n\n## [CHECKLIST]\n1. Executar tarefa: '{task}'",
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
