import sys
import os
import io
import re
import json
import contextlib
from pathlib import Path

# Suporte UTF-8 no Windows
if sys.platform == "win32":
    try:
        sys.stdin.reconfigure(encoding="utf-8")
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parent
STATE_FILE = ROOT / ".agent" / ".pre_agent_last_step"
sys.path.insert(0, str(SCRIPT_DIR))

ACTION_TRIGGERS = {
    "crie", "criar", "faca", "fazer", "adicione", "adicionar", "refatore", "refatorar",
    "altere", "alterar", "corrija", "corrigir", "implemente", "implementar", "teste", "testar",
    "migration", "endpoint", "rotas", "rota", "tela", "telas", "bug", "erro", "componente", "setup",
    "deploy", "docker", "banco", "tabela", "schema", "api", "apis", "query", "interface",
    "script", "hook", "mcp", "view", "controller", "service", "crud", "auth", "login",
    "sql", "postgres", "supabase", "tailwind", "fastapi", "react", "pydantic", "vitest", "playwright",
    "pdf", "excel", "xlsx", "relatorio", "filtro", "kpi", "dashboard"
}

def should_trigger_pre_agent(prompt: str) -> bool:
    """Evita congelar o chat em conversas casuais enquanto captura demandas técnicas curtas."""
    clean = prompt.lower().strip()
    if len(clean) < 6:
        return False
    # Pula saudações e dúvidas conceituais genéricas
    if clean.startswith(("o que e", "o que é", "como funciona", "qual a diferenca", "qual a diferença", "explique", "me diga", "ola", "oi", "bom dia", "boa tarde", "boa noite")):
        return False
    # Aciona se contiver termo de ação técnica
    return any(term in clean for term in ACTION_TRIGGERS)

def get_unprocessed_user_request(transcript_path: str) -> tuple[int, str]:
    if not transcript_path or not Path(transcript_path).exists():
        return -1, ""
    try:
        with open(transcript_path, "r", encoding="utf-8") as f:
            user_lines = [l for l in f if '"type":"USER_INPUT"' in l]
            if not user_lines:
                return -1, ""
            last_obj = json.loads(user_lines[-1])
            step_idx = last_obj.get("step_index", -1)
            content = last_obj.get("content", "")
            match = re.search(r"<USER_REQUEST>(.*?)</USER_REQUEST>", content, re.DOTALL)
            prompt = match.group(1).strip() if match else content.strip()
            return step_idx, prompt
    except Exception:
        return -1, ""

def main():
    try:
        raw_stdin = sys.stdin.read()
        if not raw_stdin.strip():
            sys.stdout.write("{}\n")
            return
        payload = json.loads(raw_stdin)
    except Exception:
        sys.stdout.write("{}\n")
        return

    transcript_path = payload.get("transcriptPath")
    workspace_paths = payload.get("workspacePaths") or []
    conv_id = payload.get("conversationId", "default")
    
    workspace = Path(workspace_paths[0]) if workspace_paths and Path(workspace_paths[0]).exists() else None
    state_file = (ROOT / ".agent" / f".pre_agent_last_step_{conv_id}") if conv_id else STATE_FILE

    step_idx, user_prompt = get_unprocessed_user_request(transcript_path)

    # Gating: ignora se for prompt trivial, casual ou não-técnico
    if step_idx < 0 or not should_trigger_pre_agent(user_prompt):
        sys.stdout.write("{}\n")
        return

    # Garante idempotência: processa cada mensagem do usuário exatamente uma vez
    if state_file.exists():
        try:
            last_processed = int(state_file.read_text(encoding="utf-8").strip())
            if step_idx <= last_processed:
                sys.stdout.write("{}\n")
                return
        except Exception:
            pass

    # Registra o step atual antes de chamar o modelo
    try:
        state_file.parent.mkdir(parents=True, exist_ok=True)
        state_file.write_text(str(step_idx), encoding="utf-8")
    except Exception:
        pass

    # Executa a decomposição técnica silenciando logs intermediários no stdout
    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf):
            import manage_skills
            if workspace:
                manage_skills.set_workspace(workspace)
            import pre_agent
            res = pre_agent.pre_agent_decompose(user_prompt, auto_route_skills=True)
        
        spec = res.get("spec", "")
        skills = res.get("activated_skills", [])
        model = res.get("model_used", "free-tier")

        msg_lines = [
            f"### [PRÉ-AGENTE TÉCNICO (Modelo: {model})]",
            spec
        ]
        if skills:
            msg_lines.append(f"\n> [!NOTE]\n> Skills auto-injetadas em `.agent/skills/`: {', '.join(skills)}")

        output = {
            "injectSteps": [
                {
                    "ephemeralMessage": "\n".join(msg_lines)
                }
            ]
        }
        sys.stdout.write(json.dumps(output, ensure_ascii=False) + "\n")
    except Exception:
        sys.stdout.write("{}\n")

if __name__ == "__main__":
    main()
