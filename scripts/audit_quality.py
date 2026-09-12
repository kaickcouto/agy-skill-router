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

BLOCKED_REGEX = [
    r'(^|-)(marketing|copywriting|seo|affiliate|growth|funnel|dropship|influencer|viral|content-strategist|blogwriting)($|-)',
    r'(^|-)(ad|ads|campaign|advertis)($|-)',
    r'(^|-)(odoo|salesforce|sap|drupal|magento|wordpress|shopify|makepad|crossframe)($|-)',
    r'(^|-)(crypto|solidity|web3|nft|token|blockchain|yield)($|-)',
    r'(^|-)(health|diet|fitness|dating|travel|weightloss|recipe|tarot|astrology|psycholog)($|-)',
    r'(^|-)(andruia|accint|xiaohongshu|wechat|douyin|taisly)($|-)',
    r'azure-.*-(java|dotnet|csharp)',
    r'-(java|dotnet|csharp)$'
]

COMPILED_BLOCKED = [re.compile(p, re.IGNORECASE) for p in BLOCKED_REGEX]

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

    # Inspeciona pasta references se existir
    ref_dir = skill_dir / "references"
    ref_files = list(ref_dir.glob("*.md")) if ref_dir.exists() else []
    total_ref_size = sum(len(rf.read_text(encoding="utf-8", errors="ignore")) for rf in ref_files[:10])
    effective_size = size + total_ref_size

    # 1. Profundidade de conteúdo (max 30 pts)
    if effective_size > 4000:
        score += 30
    elif effective_size > 1800:
        score += 20
    elif effective_size > 600:
        score += 10
    else:
        reasons.append("Tamanho insuficiente (< 600 bytes)")

    # 2. Praticidade e exemplos de código ou regras (max 35 pts)
    code_blocks = len(re.findall(r'```[a-zA-Z0-9_\-]+', text))
    for rf in ref_files[:5]:
        r_text = rf.read_text(encoding="utf-8", errors="ignore")
        code_blocks += len(re.findall(r'```[a-zA-Z0-9_\-]+', r_text))

    if code_blocks >= 3:
        score += 25
    elif code_blocks >= 1:
        score += 15
    elif effective_size > 3000:
        score += 15
    else:
        reasons.append("Sem exemplos práticos de código")

    has_scripts = (skill_dir / "scripts").exists() or any(skill_dir.glob("*.py")) or any(skill_dir.glob("*.sh"))
    if has_scripts:
        score += 10
    if len(ref_files) >= 2:
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

    if "|" in text and "-|-" in text:
        score += 5

    # 4. Detecção de lixo / templates / personas vazias (Penalidades)
    for phrase in GENERIC_TEMPLATE_PHRASES:
        if phrase in text_lower:
            score -= 35
            reasons.append("Template genérico não customizado")
            break

    if "persona" in text_lower and code_blocks == 0 and not has_scripts and effective_size < 2500:
        score -= 30
        reasons.append("Persona/Roleplay sem ferramentas técnicas")

    if effective_size < 300:
        score -= 25
        reasons.append("Conteúdo extremamente raso")

    final_score = max(0, min(100, score))
    return final_score, reasons

def is_domain_blocked(skill_name: str) -> tuple[bool, str]:
    if skill_name in OFFICIAL_WHITELIST:
        return False, ""
    for rgx in COMPILED_BLOCKED:
        if rgx.search(skill_name):
            return True, f"Domínio descartado ({rgx.pattern})"
    return False, ""

def run_audit(dry_run: bool = True, min_score: int = 60, engineering_only: bool = True, top_limit: int = None):
    print(f"[*] Iniciando Auditoria Bidirecional (Vault & Quarentena)...")
    print(f"[*] Filtro de Engenharia: {'ATIVO (foco em desenvolvimento e dados)' if engineering_only else 'DESATIVADO'}")
    print(f"[*] Corte Mínimo: {min_score} pts")

    # Coleta todas as skills de ambos os diretórios
    all_skills = {}
    if VAULT_DIR.exists():
        for d in VAULT_DIR.iterdir():
            if d.is_dir() and not d.name.startswith((".", "_")):
                all_skills[d.name] = (d, "vault")
    if QUARANTINE_DIR.exists():
        for d in QUARANTINE_DIR.iterdir():
            if d.is_dir() and not d.name.startswith((".", "_")):
                all_skills[d.name] = (d, "quarantine")

    to_vault = []
    to_quarantine = []

    for name, (path, current_loc) in sorted(all_skills.items()):
        name_lower = name.lower()

        if engineering_only:
            blocked, b_reason = is_domain_blocked(name_lower)
            if blocked:
                to_quarantine.append((0, path, [b_reason], current_loc))
                continue

        score, reasons = calculate_quality_score(path)
        
        # Coleta contagem de código e tamanho total para desempate
        doc = path / "SKILL.md"
        doc_text = doc.read_text(encoding="utf-8", errors="ignore") if doc.exists() else ""
        ref_dir = path / "references"
        ref_text = " ".join(f.read_text(encoding="utf-8", errors="ignore") for f in ref_dir.glob("*.md")) if ref_dir.exists() else ""
        full_text = doc_text + " " + ref_text
        code_blocks = len(re.findall(r'```[a-zA-Z0-9_\-]+', full_text))
        total_size = len(full_text)

        if score >= min_score or name_lower in OFFICIAL_WHITELIST:
            to_vault.append((score, path, current_loc, code_blocks, total_size))
        else:
            to_quarantine.append((score, path, reasons, current_loc))

    # Se houver limite estrito (ex: top 550)
    if top_limit and len(to_vault) > top_limit:
        print(f"[*] Aplicando corte de elite para exatamente Top {top_limit} skills...")
        # Ordena: Oficiais Anthropic primeiro (score 200), depois score, depois número de códigos, depois tamanho
        to_vault.sort(key=lambda x: (
            200 if x[1].name.lower() in OFFICIAL_WHITELIST else x[0],
            x[3],
            x[4]
        ), reverse=True)

        cutoff_vault = to_vault[:top_limit]
        overflow = to_vault[top_limit:]
        
        for sc, path, loc, cb, sz in overflow:
            to_quarantine.append((sc, path, [f"Fora do Top {top_limit} de densidade técnica"], loc))
        
        to_vault = cutoff_vault

    print("\n" + "="*55)
    print(f"[*] Total de Skills Avaliadas: {len(all_skills)}")
    print(f"  [+] Aprovadas para o Vault:    {len(to_vault)}")
    print(f"  [-] Mantidas na Quarentena:   {len(to_quarantine)}")
    print("="*55)

    if not dry_run:
        VAULT_DIR.mkdir(parents=True, exist_ok=True)
        QUARANTINE_DIR.mkdir(parents=True, exist_ok=True)

        restored = 0
        quarantined = 0

        for item in to_vault:
            sc, path, loc = item[0], item[1], item[2]
            if loc == "quarantine":
                dst = VAULT_DIR / path.name
                if dst.exists():
                    shutil.rmtree(dst, ignore_errors=True)
                shutil.move(str(path), str(dst))
                restored += 1

        for item in to_quarantine:
            sc, path, reasons, loc = item[0], item[1], item[2], item[3]
            if loc == "vault":
                dst = QUARANTINE_DIR / path.name
                if dst.exists():
                    shutil.rmtree(dst, ignore_errors=True)
                shutil.move(str(path), str(dst))
                quarantined += 1

        print(f"\n[OK] Ajuste de elite aplicado:")
        print(f"    - Restauradas para o Vault: {restored}")
        print(f"    - Enviadas para Quarentena: {quarantined}")
        print("[*] Reexecutando scripts/setup_skills.py para atualizar o manifesto...")
        import setup_skills
        setup_skills.run()

if __name__ == "__main__":
    apply_changes = "--apply" in sys.argv
    eng_only = "--all" not in sys.argv
    min_score = 60
    top_limit = None
    for arg in sys.argv:
        if arg.startswith("--min-score="):
            min_score = int(arg.split("=")[1])
        elif arg.startswith("--top="):
            top_limit = int(arg.split("=")[1])

    run_audit(dry_run=not apply_changes, min_score=min_score, engineering_only=eng_only, top_limit=top_limit)
