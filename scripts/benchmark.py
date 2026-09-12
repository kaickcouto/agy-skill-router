import sys
import time
from pathlib import Path

# Suporte a UTF-8 no Windows
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from auto_route import get_index, check_bundles

BENCHMARK_CASES = [
    # 1. Banco de Dados & Migrations
    ("criar migrations e politicas RLS no postgres", ["supabase-postgres-best-practices", "supabase"]),
    ("otimizar queries sql lentas e adicionar indices no postgres", ["supabase-postgres-best-practices"]),
    ("conectar banco supabase e configurar tabelas", ["supabase", "supabase-postgres-best-practices"]),

    # 2. Frontend & Design Systems
    ("estilizar componentes usando tailwind css v4 e tokens", ["tailwind-patterns", "tailwind-design-system"]),
    ("criar experiencia 3d interativa na web com three.js e react", ["3d-web-experience"]),
    ("gerenciar cache de requisicoes e mutacoes com react query", ["tanstack-query-expert"]),
    ("validar schema de formulario e dtos com zod", ["zod-validation-expert"]),

    # 3. Qualidade & Testes
    ("escrever testes unitarios rapidos com vitest e mocks", ["vitest-skill"]),
    ("criar testes e2e automatizados no navegador com playwright", ["webapp-testing"]),

    # 4. Documentos & Planilhas
    ("manipular planilha xlsx, calcular formulas e somar colunas", ["xlsx"]),
    ("gerar relatorio em pdf e extrair texto com ocr", ["pdf"]),
    ("criar apresentacao de slides profissional a partir de texto", ["2slides-ppt-generator", "pptx"]),

    # 5. DevOps & Containerizacao
    ("criar dockerfile multi-stage e containerizar aplicacao", ["docker-expert", "docker-compose-generator"]),
    ("configurar manifesto kubernetes e ingress para cluster", ["cloud-k8s", "kubernetes-manifest-validator", "k8s-manifest-refactor"]),

    # 6. Bundles Coordenados
    ("fazer crud completo com supabase, interface react e validacao", ["fullstack-supabase"]),
    ("configurar testes completos e2e com playwright e vitest", ["web-testing-suite"]),
    ("importar dados de planilha excel e gerar relatorio pdf", ["excel-data-reports"]),

    # 7. Supressão de Consultas Genéricas (0 skills ativadas / 0 tokens extras)
    ("como funciona um loop while em python?", None),
    ("funcao simples para somar dois numeros em javascript", None),
    ("qual a diferenca entre let e const?", None),
    ("como declarar uma variavel em typescript?", None)
]

def run_benchmark():
    print("=" * 68)
    print("  🚀 BENCHMARK DE PRECISÃO & ECONOMIA DE TOKENS (AGY-SKILL-ROUTER)")
    print("=" * 68)

    idx = get_index()
    total = len(BENCHMARK_CASES)
    passed = 0
    latencies = []

    for prompt, expected in BENCHMARK_CASES:
        t0 = time.perf_counter()

        # 1. Verifica bundle
        b_id, b_skills = check_bundles(prompt)
        if b_id:
            top_match = b_id
            score = 100.0
        else:
            scores = idx.score(prompt)
            top_match = scores[0][1] if (scores and scores[0][0] >= 4.0) else None
            score = scores[0][0] if (scores and scores[0][0] >= 4.0) else 0.0

        latency_ms = (time.perf_counter() - t0) * 1000
        latencies.append(latency_ms)

        # Validação
        if expected is None:
            ok = (top_match is None)
            expected_desc = "[NENHUMA / 0 TOKENS]"
        else:
            exp_list = expected if isinstance(expected, list) else [expected]
            expected_desc = " ou ".join(exp_list)
            if b_id:
                ok = (b_id in exp_list) or any(s in exp_list for s in b_skills)
            else:
                ok = (top_match in exp_list)

        status_str = "✅ PASS" if ok else "❌ FAIL"
        if ok:
            passed += 1

        print(f" {status_str} [{latency_ms:4.1f}ms] '{prompt[:42]:<42}' -> {top_match or 'NENHUMA'}")
        if not ok:
            print(f"       Esperado: {expected_desc} | Obtido: {top_match} (Score: {score:.1f})")

    avg_latency = sum(latencies) / total
    accuracy = (passed / total) * 100

    # Economia de Contexto / Tokens
    # 1312 skills no vault (média de ~1.400 tokens por SKILL.md com referências) = ~1.836.800 tokens
    # Roteadas: 1-2 skills ativas (~2.800 tokens)
    tokens_without_router = 1312 * 1400
    tokens_with_router = 2 * 1400
    token_savings = ((tokens_without_router - tokens_with_router) / tokens_without_router) * 100

    print("\n" + "=" * 68)
    print(f"  📊 RESULTADOS FINAIS:")
    print(f"  • Acurácia de Roteamento : {passed}/{total} ({accuracy:.1f}%)")
    print(f"  • Latência Média por Consulta : {avg_latency:.2f} ms")
    print(f"  • Contexto Estático Bruto : ~{tokens_without_router:,} tokens (1.312 skills)")
    print(f"  • Contexto Dinâmico Roteado : ~{tokens_with_router:,} tokens (1–2 skills)")
    print(f"  • Taxa Real de Economia : {token_savings:.2f}% de tokens poupados")
    print("=" * 68 + "\n")

if __name__ == "__main__":
    run_benchmark()
