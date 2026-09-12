import os
import sys
import re
import json
import shutil
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
QUARANTINE_DIR = ROOT / "skills_quarantine"
MANIFEST_PATH = ROOT / "skills_manifest.json"

GENERIC_TEMPLATE_PHRASES = [
    "when you need specialized assistance with this domain",
    "the task is unrelated to",
    "todo: fill",
    "lorem ipsum",
    "insert description here",
    "[placeholder]",
    "<placeholder>"
]

OFFICIAL_WHITELIST = {
    "pdf", "xlsx", "docx", "pptx", "frontend-design", "webapp-testing",
    "mcp-builder", "canvas-design", "algorithmic-art", "brand-guidelines",
    "doc-coauthoring", "internal-comms", "slack-gif-creator", "theme-factory",
    "web-artifacts-builder", "claude-api", "academy-guide"
}

def calculate_quality_score(skill_dir: Path) -> tuple[int, list[str]]:
    if skill_dir.name in OFFICIAL_WHITELIST:
        return 95, ["Skill oficial auditada"]

    score = 0
    reasons = []

    doc = skill_dir / "SKILL.md"
    if not doc.exists():
        doc = skill_dir / "README.md"

    if not doc.exists():
        return 0, ["Arquivo SKILL.md ou README.md ausente"]

    text = doc.read_text(encoding="utf-8", errors="ignore")
    size = len(text)
    text_lower = text.lower()

    # 1. Profundidade de conteúdo (max 30 pts)
    if size > 4000:
        score += 30
    elif size > 1800:
        score += 20
    elif size > 600:
        score += 10
    else:
        reasons.append("Tamanho insuficiente (< 600 bytes)")

    # 2. Praticidade e exemplos de código ou regras (max 35 pts)
    code_blocks = len(re.findall(r'```[a-zA-Z0-9_\-]+', text))
    if code_blocks >= 3:
        score += 25
    elif code_blocks >= 1:
        score += 15
    elif size > 3000:
        # Guia conceitual/arquitetural detalhado
        score += 15
    else:
        reasons.append("Sem exemplos práticos de código")

    has_scripts = (skill_dir / "scripts").exists() or any(skill_dir.glob("*.py")) or any(skill_dir.glob("*.sh"))
    if has_scripts:
        score += 10

    # 3. Estrutura e organização (max 25 pts)
    headers = len(re.findall(r'^#{1,3}\s+', text, re.MULTILINE))
    if headers >= 4:
        score += 10
    elif headers >= 2:
        score += 5

    has_frontmatter = bool(re.search(r'^---\s*\n(.*?)\n---', text, re.DOTALL))
    if has_frontmatter:
        score += 10

    # Checklist / Tabelas de apoio
    if "|" in text and "-|-" in text:
        score += 5

    # 4. Detecção de lixo / templates / personas vazias (Penalidades)
    for phrase in GENERIC_TEMPLATE_PHRASES:
        if phrase in text_lower:
            score -= 35
            reasons.append(f"Template genérico não customizado")
            break

    # Persona pura sem código e sem scripts
    if "persona" in text_lower and code_blocks == 0 and not has_scripts and size < 2500:
        score -= 30
        reasons.append("Persona/Roleplay sem ferramentas técnicas")

    # Título ou descrição vazia/inútil
    if size < 300:
        score -= 25
        reasons.append("Conteúdo extremamente raso")

    final_score = max(0, min(100, score))
    return final_score, reasons

def run_audit(dry_run: bool = True, min_score: int = 40):
    print(f"[*] Iniciando Auditoria Justa de Qualidade (Corte Mínimo: {min_score} pts)...")
    print(f"[*] Modo: {'SIMULAÇÃO (Nenhum arquivo será movido)' if dry_run else 'APLICAR PENEIRA (Movendo lixo para quarentena)'}")

    skills = sorted([d for d in VAULT_DIR.iterdir() if d.is_dir() and not d.name.startswith((".", "_"))])
    
    tier_gold = []
    tier_silver = []
    quarantined = []

    for s in skills:
        score, reasons = calculate_quality_score(s)
        if score >= 65:
            tier_gold.append((score, s))
        elif score >= min_score:
            tier_silver.append((score, s))
        else:
            quarantined.append((score, s, reasons))

    print("\n" + "="*50)
    print(f"[*] Total de Skills Analisadas: {len(skills)}")
    print(f"  [+] Tier Ouro (Excelente >= 65 pts): {len(tier_gold)}")
    print(f"  [+] Tier Prata (Sólido {min_score}-64 pts):  {len(tier_silver)}")
    print(f"  [-] Tier Baixo / Peneiradas (< {min_score} pts): {len(quarantined)}")
    print("="*50)

    if quarantined:
        print("\n[*] Amostra de Skills Reprovadas na Peneira:")
        for sc, path, reasons in quarantined[:12]:
            r_str = "; ".join(reasons) if reasons else "Score baixo geral"
            print(f"  - [{sc:2d} pts] {path.name:32} -> {r_str}")

    if not dry_run:
        QUARANTINE_DIR.mkdir(parents=True, exist_ok=True)
        moved = 0
        for _, path, _ in quarantined:
            dst = QUARANTINE_DIR / path.name
            if dst.exists():
                if dst.is_dir():
                    shutil.rmtree(dst, ignore_errors=True)
                else:
                    dst.unlink(missing_ok=True)
            try:
                shutil.move(str(path), str(dst))
                moved += 1
            except Exception:
                pass
        print(f"\n[OK] Peneira concluída! {moved} skills foram movidas para skills_quarantine/.")
        print("[*] Reexecutando scripts/setup_skills.py para atualizar o manifesto...")
        import setup_skills
        setup_skills.run()

if __name__ == "__main__":
    apply_changes = "--apply" in sys.argv
    min_score = 40
    for arg in sys.argv:
        if arg.startswith("--min-score="):
            min_score = int(arg.split("=")[1])

    run_audit(dry_run=not apply_changes, min_score=min_score)
