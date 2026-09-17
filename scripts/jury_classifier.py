import sys
import os
import json
import re
from pathlib import Path

# Suporte UTF-8 no Windows
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

ROOT = Path(__file__).resolve().parent.parent
VAULT_DIR = ROOT / "skills_vault"
MANIFEST_PATH = ROOT / "skills_manifest.json"

THEMATIC_BLOCKS = {
    "general-tools": {
        "title": "Ferramentas Gerais",
        "keywords": [],
        "min_confidence": 3.0
    },
    "core-frontend": {
        "title": "Frontend & Interface",
        "keywords": ["react", "nextjs", "vite", "tailwind", "css", "html", "ui", "ux", "component", "zustand", "redux", "web"],
        "min_confidence": 3.5
    },
    "core-backend": {
        "title": "Backend, APIs & Auth",
        "keywords": ["fastapi", "express", "node", "api", "rest", "graphql", "auth", "jwt", "oauth", "pydantic", "backend"],
        "min_confidence": 3.5
    },
    "core-database": {
        "title": "Bancos de Dados & Migrations",
        "keywords": ["postgres", "postgresql", "supabase", "sql", "migration", "prisma", "drizzle", "redis", "database"],
        "min_confidence": 3.5
    },
    "quality-testing": {
        "title": "Qualidade, Testes & Arquitetura",
        "keywords": ["vitest", "jest", "playwright", "cypress", "test", "testing", "tdd", "qa", "e2e", "audit", "clean"],
        "min_confidence": 3.5
    },
    "cloud-devops": {
        "title": "DevOps, Infra & Deploy",
        "keywords": ["docker", "kubernetes", "terraform", "ci", "cd", "git", "linux", "vercel", "deploy", "pipeline"],
        "min_confidence": 3.5
    },
    "data-ai-engine": {
        "title": "Dados, IA & Automação",
        "keywords": ["pandas", "excel", "xlsx", "scraping", "llm", "rag", "mcp", "embeddings", "openai", "claude"],
        "min_confidence": 3.5
    },
    "office-docs": {
        "title": "Documentos & Relatórios",
        "keywords": ["pdf", "docx", "pptx", "document", "report", "presentation", "word", "powerpoint"],
        "min_confidence": 3.5
    }
}

class TriMindJudge:
    @staticmethod
    def advocate_view(skill_id: str, desc: str, tags: list[str], block: str) -> dict:
        kws = THEMATIC_BLOCKS.get(block, {}).get("keywords", [])
        hits = [k for k in kws if k in f"{skill_id} {desc} {' '.join(tags)}".lower()]
        return {
            "score": min(7, 3 + len(hits)),
            "argument": f"Aderência ao bloco '{block}'. ({', '.join(hits[:3]) or 'geral'})."
        }

    @staticmethod
    def critic_view(skill_id: str, desc: str, tags: list[str], block: str) -> dict:
        risks = []
        if len(desc) < 60:
            risks.append("descrição concisa")
        if "-" in skill_id and len(skill_id.split("-")) > 3:
            risks.append("alta especificidade")
        if not tags:
            risks.append("metadados limitados")

        return {
            "score": min(7, 3 + len(risks)),
            "argument": f"Atenção: {', '.join(risks) if risks else 'Possível sobreposição de escopo'}."
        }

    @staticmethod
    def judge_verdict(advocate: dict, critic: dict, block: str) -> dict:
        adv_score = advocate["score"]
        crit_score = critic["score"]
        verdict_score = round((adv_score * 0.6) + ((10 - crit_score) * 0.4), 1)
        approved = verdict_score >= 4.0 and block != "general-tools"

        return {
            "assigned_block": block if approved else "general-tools",
            "confidence": verdict_score,
            "approved": approved,
            "ruling": f"Aprovada para '{block}'" if approved else "Direcionada para ferramentas gerais"
        }

def classify_skill(skill_id: str, desc: str, tags: list[str]) -> dict:
    # 1. Avaliação oficial via TypeSafe AI (Choice para Bloco + Score para Qualidade)
    try:
        import typesafe_client
        if typesafe_client.get_api_key():
            questions = {
                "block": {
                    "type": "choice",
                    "instructions": "Which technical thematic block does this engineering skill belong to?",
                    "criteria": {
                        "core-frontend": "UI components, React, Next.js, Tailwind CSS, HTML/CSS, frontend design",
                        "core-backend": "APIs, FastAPI, Node.js, Express, Python backend, REST, GraphQL, JWT auth",
                        "core-database": "PostgreSQL, Supabase, SQL, migrations, database schemas, tables, RLS",
                        "quality-testing": "Testing, Vitest, Playwright, Cypress, QA, E2E, code quality and audit",
                        "cloud-devops": "Docker, Kubernetes, CI/CD, deployment, cloud infrastructure, Linux",
                        "data-ai-engine": "Data processing, spreadsheets, XLSX, PDF, scrapers, AI prompts, LLMs",
                        "office-docs": "Office documents, Word docx, presentations pptx, report formatting",
                        "general-tools": "Generic programming concepts, syntax or general developer utilities"
                    }
                },
                "quality": {
                    "type": "score",
                    "instructions": "How production-grade, specific, and actionable is this skill description?",
                    "criteria": [
                        "Vague, superficial or lacks concrete scope",
                        "Adequate description with identifiable use cases",
                        "Highly specific production-grade engineering guide"
                    ]
                }
            }
            state = {"skill_id": skill_id, "description": desc[:500], "tags": tags[:8]}
            answers = typesafe_client.evaluate_systemone(state, questions, timeout=2.0)
            if answers and "block" in answers:
                b_ans = answers["block"]
                q_ans = answers.get("quality", {})
                block = b_ans.get("choice", "general-tools")
                b_conf = b_ans.get("confidence", 0.8)
                q_score = q_ans.get("score", 0.5)
                return {
                    "block": block,
                    "confidence": round(b_conf * 10, 1),
                    "quality_score": round(q_score, 2),
                    "advocate": f"TypeSafe AI Jev: classificada em '{block}' com probabilidade {b_ans.get('probabilities', {}).get(block, 1.0):.2f}.",
                    "critic": f"Qualidade da documentação avaliada em {q_score:.2f}/1.00.",
                    "verdict": f"Aprovada para '{block}' via TypeSafe System One"
                }
    except Exception:
        pass

    # 2. Fallback heurístico (TriMindJudge)
    best_block = "general-tools"
    best_score = 0

    text = f"{skill_id} {desc} {' '.join(tags)}".lower()
    for block_name, cfg in THEMATIC_BLOCKS.items():
        if not cfg["keywords"]:
            continue
        score = sum(3 if k in skill_id.lower() else 1 for k in cfg["keywords"] if k in text)
        if score > best_score:
            best_score = score
            best_block = block_name

    adv = TriMindJudge.advocate_view(skill_id, desc, tags, best_block)
    crit = TriMindJudge.critic_view(skill_id, desc, tags, best_block)
    verdict = TriMindJudge.judge_verdict(adv, crit, best_block)

    return {
        "block": verdict["assigned_block"],
        "confidence": verdict["confidence"],
        "advocate": adv["argument"],
        "critic": crit["argument"],
        "verdict": verdict["ruling"]
    }

def run_classification(apply_to_manifest: bool = False):
    if not MANIFEST_PATH.exists():
        print("[!] Erro: skills_manifest.json não encontrado.")
        return

    with open(MANIFEST_PATH, "r", encoding="utf-8") as f:
        manifest = json.load(f)

    print(f"[*] Executando Conselho Tri-Mind em {len(manifest)} skills...")
    block_counts = {}

    for item in manifest:
        analysis = classify_skill(item["id"], item.get("description", ""), item.get("tags", []))
        item["thematic_block"] = analysis["block"]
        item["review"] = {
            "confidence": analysis["confidence"],
            "advocate": analysis["advocate"],
            "critic": analysis["critic"],
            "verdict": analysis["verdict"]
        }
        block_counts[analysis["block"]] = block_counts.get(analysis["block"], 0) + 1

    print("\n" + "="*50)
    print("[*] Deliberação Concluída pelo Juiz:")
    for b, count in sorted(block_counts.items(), key=lambda x: x[1], reverse=True):
        title = THEMATIC_BLOCKS.get(b, {}).get("title", "Ferramentas Gerais")
        print(f"  [{b:16}] ({count:4d} skills) -> {title}")
    print("="*50)

    if apply_to_manifest:
        with open(MANIFEST_PATH, "w", encoding="utf-8") as f:
            json.dump(manifest, f, indent=2, ensure_ascii=False)
        print(f"\n[OK] Manifesto atualizado em: {MANIFEST_PATH.name}")

if __name__ == "__main__":
    apply_flag = "--apply" in sys.argv
    if len(sys.argv) > 1 and sys.argv[1] not in ("--apply",):
        target_id = sys.argv[1]
        with open(MANIFEST_PATH, "r", encoding="utf-8") as f:
            manifest = {item["id"]: item for item in json.load(f)}
        if target_id in manifest:
            m = manifest[target_id]
            res = classify_skill(target_id, m.get("description", ""), m.get("tags", []))
            print(f"\n[JULGAMENTO DA SKILL: {target_id}]")
            print(f"  • Bloco Atribuído : {res['block']}")
            print(f"  • Confiança Juiz  : {res['confidence']}/10")
            print(f"  • Advogado (Bom)  : {res['advocate']}")
            print(f"  • Crítico (Ruim)  : {res['critic']}")
            print(f"  • Veredito Final  : {res['verdict']}")
        else:
            print(f"[!] Skill '{target_id}' não encontrada no manifesto.")
    else:
        run_classification(apply_to_manifest=apply_flag)
