import sys
import os
import io
import re
import json
import traceback
import contextlib
from pathlib import Path
from urllib.parse import unquote, urlparse

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
                },
                "workspace_dir": {
                    "type": "string",
                    "description": "Caminho absoluto opcional do projeto externo alvo onde as skills serão injetadas."
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
    },
    {
        "name": "skill_info",
        "description": "Retorna o card de classificação detalhado de uma skill: intenção de chamada, triggers de demanda e stack técnica.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "skill_id": {
                    "type": "string",
                    "description": "ID da skill a inspecionar (ex: 'supabase-postgres-best-practices')."
                }
            },
            "required": ["skill_id"]
        },
        "annotations": {
            "readOnlyHint": True
        }
    },
    {
        "name": "apply_preset",
        "description": "Aplica um perfil de skills pré-configurado no workspace (ex: 'cms', 'fullstack', 'qa'), fixando as skills essenciais para não serem desativadas em resets.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "preset_name": {
                    "type": "string",
                    "description": "Nome do preset (ex: 'cms', 'fullstack', 'qa')."
                },
                "workspace_dir": {
                    "type": "string",
                    "description": "Caminho opcional do projeto alvo."
                }
            },
            "required": ["preset_name"]
        },
        "annotations": {
            "idempotentHint": True
        }
    }
]

def capture_execution(func, *args, **kwargs):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        ret = func(*args, **kwargs)
    return buf.getvalue().strip(), ret

SKILL_ID_REGEX = re.compile(r'^[a-zA-Z0-9_\-]+$')

def validate_skill_id(sid: any) -> str:
    if not sid or not isinstance(sid, str):
        raise ValueError("skill_id é obrigatório e deve ser uma string.")
    sid = sid.strip()
    if not SKILL_ID_REGEX.match(sid):
        raise ValueError(f"skill_id inválido '{sid}': use apenas letras, números, hífens e underscores.")
    return sid

def safe_int(val, default: int = 2, min_val: int = 1, max_val: int = 10) -> int:
    try:
        return max(min_val, min(max_val, int(val)))
    except (ValueError, TypeError):
        return default

@contextlib.contextmanager
def scoped_workspace(ws_arg: str | None):
    old_ws = manage_skills.CURRENT_WORKSPACE
    try:
        if ws_arg and isinstance(ws_arg, str):
            ws_path = Path(ws_arg).resolve()
            if ws_path.exists() and ws_path.is_dir():
                manage_skills.set_workspace(ws_path)
        yield
    finally:
        manage_skills.CURRENT_WORKSPACE = old_ws

def handle_route_skills(arguments: dict) -> dict:
    task = str(arguments.get("task") or "").strip()
    top_k = safe_int(arguments.get("top_k"), default=2, min_val=1, max_val=5)
    block = str(arguments.get("block")).strip() if arguments.get("block") else None
    ws = arguments.get("workspace_dir")

    with scoped_workspace(ws):
        stdout_text, res = capture_execution(
            auto_route.route,
            prompt=task,
            top_k=top_k,
            explain=True,
            block=block
        )

    activated = res.get("activated", []) if res else []
    summary_message = (
        f"[AGY-SKILL-ROUTER] Ativação concluída para: '{task}'. "
        f"Skills ativas em .agent/skills/: {', '.join(activated) if activated else 'Nenhuma (tarefa genérica)'}. "
        f"Consulte o arquivo SKILL.md correspondente para aplicar as regras de engenharia."
    )

    summary = {
        "status": "success",
        "message": summary_message,
        "bundle_matched": res.get("bundle") if res else None,
        "activated_skills": activated,
        "pinned_skills": res.get("pinned", []) if res else [],
        "workspace": str(manage_skills.get_active_dir().parent),
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

def handle_list_skills(arguments: dict) -> dict:
    ws = arguments.get("workspace_dir")
    with scoped_workspace(ws):
        stdout_text, active = capture_execution(manage_skills.list_skills)
        pinned = list(manage_skills.get_pinned())
        return {
            "content": [
                {
                    "type": "text",
                    "text": json.dumps({
                        "workspace": str(manage_skills.get_active_dir().parent),
                        "active_skills": active,
                        "pinned_skills": pinned,
                        "details": stdout_text
                    }, ensure_ascii=False, indent=2)
                }
            ]
        }

def handle_reset_skills(arguments: dict) -> dict:
    ws = arguments.get("workspace_dir")
    force = bool(arguments.get("force", False))
    with scoped_workspace(ws):
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
    query = str(arguments.get("query") or "").strip()
    top_k = safe_int(arguments.get("top_k"), default=5, min_val=1, max_val=20)
    block = str(arguments.get("block")).strip() if arguments.get("block") else None

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
    sid = validate_skill_id(arguments.get("skill_id"))
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
    sid = validate_skill_id(arguments.get("skill_id"))
    stdout_text, _ = capture_execution(manage_skills.unpin, [sid])
    return {
        "content": [
            {
                "type": "text",
                "text": stdout_text
            }
        ]
    }

def handle_skill_info(arguments: dict) -> dict:
    sid = validate_skill_id(arguments.get("skill_id"))
    stdout_text, meta = capture_execution(auto_route.info, sid)
    return {
        "content": [
            {
                "type": "text",
                "text": json.dumps(meta, ensure_ascii=False, indent=2) if meta else stdout_text
            }
        ]
    }

def handle_apply_preset(arguments: dict) -> dict:
    pname = str(arguments.get("preset_name") or "").strip()
    if not pname:
        raise ValueError("preset_name é obrigatório.")
    if not re.match(r'^[a-zA-Z0-9_\-]+$', pname):
        raise ValueError(f"preset_name inválido '{pname}': use apenas letras, números e hífens.")
    ws = arguments.get("workspace_dir")
    with scoped_workspace(ws):
        stdout_text, ok = capture_execution(auto_route.apply_preset, pname)
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
    "skill_info": handle_skill_info,
    "apply_preset": handle_apply_preset,
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

            # 1. Initialize com decodificação segura de URI
            if method == "initialize":
                root_uri = params.get("rootUri") or ""
                ws_folders = params.get("workspaceFolders") or []
                if ws_folders and isinstance(ws_folders, list) and ws_folders[0].get("uri"):
                    root_uri = ws_folders[0]["uri"]

                if root_uri:
                    parsed = urlparse(root_uri)
                    clean_path = unquote(parsed.path)
                    if sys.platform == "win32" and clean_path.startswith("/"):
                        clean_path = clean_path[1:]
                    target_path = Path(clean_path).resolve()
                    if target_path.exists() and target_path.is_dir():
                        manage_skills.set_workspace(target_path)

                send_json({
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {
                        "protocolVersion": PROTOCOL_VERSION,
                        "capabilities": {
                            "tools": {},
                            "resources": {}
                        },
                        "serverInfo": SERVER_INFO
                    }
                })
            elif method == "notifications/initialized":
                pass
            elif method == "ping":
                send_json({
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {}
                })
            elif method == "tools/list":
                send_json({
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {
                        "tools": TOOLS_DEFINITIONS
                    }
                })
            elif method == "resources/list":
                active_skills = []
                cur_active = manage_skills.get_active_dir()
                if cur_active.exists():
                    active_skills = [s.name for s in cur_active.iterdir() if s.name != ".gitkeep"]
                resources = [
                    {
                        "uri": f"skills://active/{s}",
                        "name": f"Active Skill: {s}",
                        "mimeType": "text/markdown",
                        "description": f"Instruções do arquivo SKILL.md para {s}"
                    }
                    for s in active_skills
                ]
                send_json({
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {
                        "resources": resources
                    }
                })
            elif method == "resources/read":
                uri = params.get("uri", "")
                content = ""
                mime = "text/markdown"
                cur_active = manage_skills.get_active_dir()
                if uri.startswith("skills://active/"):
                    raw_sid = uri.replace("skills://active/", "").strip("/")
                    try:
                        sid = validate_skill_id(raw_sid)
                        target_dir = (cur_active / sid).resolve()
                        if not target_dir.is_relative_to(cur_active.resolve()):
                            content = f"[!] Acesso negado: Tentativa de Path Traversal detectada em '{raw_sid}'."
                        else:
                            md_path = target_dir / "SKILL.md"
                            if md_path.exists():
                                content = md_path.read_text(encoding="utf-8", errors="ignore")
                            else:
                                content = f"[!] Arquivo SKILL.md não encontrado para '{sid}' em {cur_active}."
                    except ValueError as ve:
                        content = f"[!] ID de skill inválido: {str(ve)}"
                elif uri.startswith("skills://vault/"):
                    raw_sid = uri.replace("skills://vault/", "").strip("/")
                    try:
                        sid = validate_skill_id(raw_sid)
                        target_dir = (manage_skills.VAULT_DIR / sid).resolve()
                        if not target_dir.is_relative_to(manage_skills.VAULT_DIR.resolve()):
                            content = f"[!] Acesso negado: Tentativa de Path Traversal detectada em '{raw_sid}'."
                        else:
                            md_path = target_dir / "SKILL.md"
                            if md_path.exists():
                                content = md_path.read_text(encoding="utf-8", errors="ignore")
                            else:
                                content = f"[!] Arquivo SKILL.md não encontrado no vault para '{sid}'."
                    except ValueError as ve:
                        content = f"[!] ID de skill inválido: {str(ve)}"
                else:
                    content = f"[!] URI não suportada: {uri}"

                send_json({
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {
                        "contents": [
                            {
                                "uri": uri,
                                "mimeType": mime,
                                "text": content
                            }
                        ]
                    }
                })
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
                except (ValueError, FileNotFoundError) as ve:
                    send_json({
                        "jsonrpc": "2.0",
                        "id": req_id,
                        "result": {
                            "content": [{"type": "text", "text": f"[ERRO] {str(ve)}"}],
                            "isError": True
                        }
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
