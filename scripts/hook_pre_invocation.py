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
    step_idx, user_prompt = get_unprocessed_user_request(transcript_path)

    # Ignora prompts triviais, vazios ou muito curtos
    if step_idx < 0 or not user_prompt or len(user_prompt) < 15:
        sys.stdout.write("{}\n")
        return

    # Garante idempotência: processa cada mensagem do usuário exatamente uma vez
    if STATE_FILE.exists():
        try:
            last_processed = int(STATE_FILE.read_text(encoding="utf-8").strip())
            if step_idx <= last_processed:
                sys.stdout.write("{}\n")
                return
        except Exception:
            pass

    # Registra o step atual antes de chamar o modelo
    try:
        STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        STATE_FILE.write_text(str(step_idx), encoding="utf-8")
    except Exception:
        pass

    # Executa a decomposição técnica silenciando stdout intermediário
    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf):
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
