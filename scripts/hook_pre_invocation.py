import sys
import os
import io
import re
import json
import time
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

    # 1. Avaliação probabilística oficial via TypeSafe AI (3-Noul Gate: acts + doc + (1-prose))
    try:
        import typesafe_client
        res = typesafe_client.classify_task(prompt)
        if res:
            return bool(res.get("should_act"))
    except Exception:
        pass

    # 2. Fallback heurístico
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
    if step_idx < 0:
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
        # Limpeza periódica de arquivos de estado com mais de 48 horas
        now_ts = time.time()
        for old_f in state_file.parent.glob(".pre_agent_last_step_*"):
            try:
                if now_ts - old_f.stat().st_mtime > 172800:
                    old_f.unlink()
            except Exception:
                pass
    except Exception:
        pass

    # Avaliação rápida com TypeSafe System One (0ms em cache)
    ts_eval = None
    try:
        import typesafe_client
        ts_eval = typesafe_client.classify_task(user_prompt)
    except Exception:
        pass

    # Guardrail 1: Economia de Tokens para dúvidas conceituais/explicativas
    if ts_eval and ts_eval.get("token_saving_recommended"):
        output = {
            "injectSteps": [
                {
                    "ephemeralMessage": "> [!TIP]\n> **[PROTOCOLO DE ECONOMIA DE TOKENS ATIVO]**\n> Esta solicitação é puramente explicativa/conceitual. Responda em prosa direta e concisa. NÃO dispare ferramentas, varreduras de arquivos nem subagentes desnecessários."
                }
            ]
        }
        sys.stdout.write(json.dumps(output, ensure_ascii=False) + "\n")
        return

    # Guardrail 2: Alerta de Ambiguidade extrema para tarefas não-acionáveis
    if ts_eval and ts_eval.get("is_ambiguous") and not ts_eval.get("should_act"):
        output = {
            "injectSteps": [
                {
                    "ephemeralMessage": "> [!WARNING]\n> **[ALERTA DE AMBIGUIDADE]**\n> A solicitação é vaga ou incompleta. Em vez de adivinhar o escopo e gastar tokens com código especulativo, alinhe os requisitos com o usuário primeiro."
                }
            ]
        }
        sys.stdout.write(json.dumps(output, ensure_ascii=False) + "\n")
        return

    # Gating: ignora se for prompt trivial, casual ou não-técnico
    should_act = ts_eval.get("should_act") if ts_eval else should_trigger_pre_agent(user_prompt)
    if not should_act:
        sys.stdout.write("{}\n")
        return

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

        msg_lines = []
        if ts_eval and ts_eval.get("is_destructive"):
            msg_lines.append("> [!CAUTION]\n> **[GUARDRAIL DE SEGURANÇA: AÇÃO POTENCIALMENTE DESTRUTIVA]**\n> Detectada intenção de exclusão ou alteração profunda de dados/código. Exija confirmação explícita do usuário antes de prosseguir com remoções irreversíveis.\n")

        msg_lines.append(f"### [PRÉ-AGENTE TÉCNICO (Modelo: {model})]")
        msg_lines.append(spec)
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
