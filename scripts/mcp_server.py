import sys
import os
import io
import json
import traceback
import contextlib
from pathlib import Path

# Suporte a UTF-8 no Windows
if sys.platform == "win32":
    try:
        sys.stdin.reconfigure(encoding="utf-8")
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(SCRIPT_DIR))

import manage_skills
import auto_route

PROTOCOL_VERSION = "2024-11-05"
SERVER_INFO = {
    "name": "agy-skill-router",
    "version": "1.0.0"
}

TOOLS_DEFINITIONS = [
    {
        "name": "route_skills",
        "description": "Roteia e ativa dinamicamente as melhores skills técnicas para a tarefa do agente usando BM25 e Bundles Coordenados. Desativa automaticamente skills anteriores não fixadas para economia máxima de tokens.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "task": {
                    "type": "string",
                    "description": "Descrição da tarefa a ser executada pelo modelo/agente."
                },
                "top_k": {
                    "type": "integer",
                    "description": "Número máximo de skills a ativar (padrão: 2).",
                    "default": 2
                },
                "block": {
                    "type": "string",
                    "description": "Filtro opcional por bloco temático: core-frontend, cloud-devops, core-backend, data-ai-engine, quality-testing, core-database, office-docs."
                }
            },
            "required": ["task"]
        },
        "annotations": {
            "destructiveHint": False,
            "openWorldHint": True
        }
    },
    {
        "name": "list_skills",
        "description": "Lista todas as skills atualmente ativas e fixadas (pinned) em .agent/skills/.",
        "inputSchema": {
            "type": "object",
            "properties": {}
        },
        "annotations": {
            "readOnlyHint": True
        }
    },
    {
        "name": "reset_skills",
        "description": "Desativa e limpa todas as skills ativas em .agent/skills/ (exceto as fixadas/pinned) para resetar o contexto e economizar tokens.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "force": {
                    "type": "boolean",
                    "description": "Se verdadeiro, remove inclusive as skills fixadas (pinned). Padrão: false.",
                    "default": False
                }
            }
        },
        "annotations": {
            "destructiveHint": True
        }
    },
    {
        "name": "search_skills",
        "description": "Busca no Vault de skills por similaridade BM25 sem ativar nem alterar o diretório de skills.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Termos de busca técnica (ex: 'supabase migrations', 'tailwind', 'excel openpyxl')."
                },
                "top_k": {
                    "type": "integer",
                    "description": "Número de resultados para retornar (padrão: 5).",
                    "default": 5
                },
                "block": {
                    "type": "string",
                    "description": "Filtro opcional por bloco temático."
                }
            },
            "required": ["query"]
        },
        "annotations": {
            "readOnlyHint": True
        }
    },
    {
        "name": "pin_skill",
        "description": "Fixa uma skill no workspace para que ela permaneça ativa permanentemente mesmo após chamadas de reset.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "skill_id": {
                    "type": "string",
                    "description": "ID da skill a fixar (ex: 'supabase-postgres-best-practices')."
                }
            },
            "required": ["skill_id"]
        },
        "annotations": {
            "idempotentHint": True
        }
    },
    {
        "name": "unpin_skill",
        "description": "Desafixa uma skill previamente fixada e a remove de .agent/skills/.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "skill_id": {
                    "type": "string",
                    "description": "ID da skill a desafixar."
                }
            },
            "required": ["skill_id"]
        },
        "annotations": {
            "idempotentHint": True
        }
    }
]

def capture_execution(func, *args, **kwargs):
    """Executa a função capturando saídas de stdout para não quebrar a comunicação JSON-RPC."""
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        ret = func(*args, **kwargs)
    return buf.getvalue().strip(), ret

def handle_route_skills(arguments: dict) -> dict:
    task = arguments.get("task", "")
    top_k = int(arguments.get("top_k", 2))
    block = arguments.get("block")

    stdout_text, res = capture_execution(
        auto_route.route,
        prompt=task,
        top_k=top_k,
        explain=True,
        block=block
    )

    summary = {
        "task": task,
        "bundle_matched": res.get("bundle") if res else None,
        "activated_skills": res.get("activated", []) if res else [],
        "pinned_skills": res.get("pinned", []) if res else [],
        "cli_output": stdout_text
    }
    return {
        "content": [
            {
                "type": "text",
                "text": json.dumps(summary, ensure_ascii=False, indent=2)
            }
        ]
    }

def handle_list_skills(_arguments: dict) -> dict:
    stdout_text, active = capture_execution(manage_skills.list_skills)
    pinned = list(manage_skills.get_pinned())
    return {
        "content": [
            {
                "type": "text",
                "text": json.dumps({
                    "active_skills": active,
                    "pinned_skills": pinned,
                    "details": stdout_text
                }, ensure_ascii=False, indent=2)
            }
        ]
    }

def handle_reset_skills(arguments: dict) -> dict:
    force = bool(arguments.get("force", False))
    stdout_text, _ = capture_execution(manage_skills.reset, force=force)
    return {
        "content": [
            {
                "type": "text",
                "text": stdout_text or "Reset concluído com sucesso."
            }
        ]
    }

def handle_search_skills(arguments: dict) -> dict:
    query = arguments.get("query", "")
    top_k = int(arguments.get("top_k", 5))
    block = arguments.get("block")

    stdout_text, matches = capture_execution(
        auto_route.search,
        query=query,
        top_k=top_k,
        block=block
    )
    return {
        "content": [
            {
                "type": "text",
                "text": json.dumps({
                    "query": query,
                    "results": matches,
                    "formatted_output": stdout_text
                }, ensure_ascii=False, indent=2)
            }
        ]
    }

def handle_pin_skill(arguments: dict) -> dict:
    sid = arguments.get("skill_id", "").strip()
    if not sid:
        raise ValueError("skill_id é obrigatório")
    stdout_text, _ = capture_execution(manage_skills.pin, [sid])
    return {
        "content": [
            {
                "type": "text",
                "text": stdout_text
            }
        ]
    }

def handle_unpin_skill(arguments: dict) -> dict:
    sid = arguments.get("skill_id", "").strip()
    if not sid:
        raise ValueError("skill_id é obrigatório")
    stdout_text, _ = capture_execution(manage_skills.unpin, [sid])
    return {
        "content": [
            {
                "type": "text",
                "text": stdout_text
            }
        ]
    }

TOOL_HANDLERS = {
    "route_skills": handle_route_skills,
    "list_skills": handle_list_skills,
    "reset_skills": handle_reset_skills,
    "search_skills": handle_search_skills,
    "pin_skill": handle_pin_skill,
    "unpin_skill": handle_unpin_skill,
}

def send_json(data: dict):
    payload = json.dumps(data, ensure_ascii=False)
    sys.stdout.write(payload + "\n")
    sys.stdout.flush()

def main():
    while True:
        try:
            line = sys.stdin.readline()
            if not line:
                break
            line = line.strip()
            if not line:
                continue

            try:
                request = json.loads(line)
            except Exception as e:
                send_json({
                    "jsonrpc": "2.0",
                    "id": None,
                    "error": {"code": -32700, "message": f"Parse error: {str(e)}"}
                })
                continue

            req_id = request.get("id")
            method = request.get("method")
            params = request.get("params", {})

            # 1. Initialize
            if method == "initialize":
                send_json({
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {
                        "protocolVersion": PROTOCOL_VERSION,
                        "capabilities": {
                            "tools": {}
                        },
                        "serverInfo": SERVER_INFO
                    }
                })
            # 2. Notification initialized
            elif method == "notifications/initialized":
                pass
            # 3. Ping
            elif method == "ping":
                send_json({
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {}
                })
            # 4. List tools
            elif method == "tools/list":
                send_json({
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {
                        "tools": TOOLS_DEFINITIONS
                    }
                })
            # 5. Call tool
            elif method == "tools/call":
                tool_name = params.get("name")
                tool_args = params.get("arguments", {})

                handler = TOOL_HANDLERS.get(tool_name)
                if not handler:
                    send_json({
                        "jsonrpc": "2.0",
                        "id": req_id,
                        "result": {
                            "content": [{"type": "text", "text": f"Ferramenta desconhecida: '{tool_name}'"}],
                            "isError": True
                        }
                    })
                    continue

                try:
                    tool_result = handler(tool_args)
                    send_json({
                        "jsonrpc": "2.0",
                        "id": req_id,
                        "result": tool_result
                    })
                except Exception as ex:
                    send_json({
                        "jsonrpc": "2.0",
                        "id": req_id,
                        "result": {
                            "content": [{"type": "text", "text": f"Erro na execução da tool '{tool_name}': {str(ex)}\n{traceback.format_exc()}"}],
                            "isError": True
                        }
                    })
            else:
                if req_id is not None:
                    send_json({
                        "jsonrpc": "2.0",
                        "id": req_id,
                        "error": {"code": -32601, "message": f"Method not found: {method}"}
                    })
        except Exception as loop_ex:
            sys.stderr.write(f"[MCP SERVER ERROR] {traceback.format_exc()}\n")
            sys.stderr.flush()

if __name__ == "__main__":
    main()
