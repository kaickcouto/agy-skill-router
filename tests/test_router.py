import unittest
import sys
import os
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'scripts'))

import auto_route
import manage_skills

class TestSkillRouterRegression(unittest.TestCase):

    def setUp(self):
        self.tmp_ws = ROOT / 'tests' / 'tmp_workspace'
        self.tmp_ws.mkdir(parents=True, exist_ok=True)
        (self.tmp_ws / '.agent').mkdir(parents=True, exist_ok=True)
        manage_skills.set_workspace(self.tmp_ws)

    def tearDown(self):
        manage_skills.reset()
        manage_skills.set_workspace(None)
        if self.tmp_ws.exists():
            import shutil
            shutil.rmtree(self.tmp_ws, ignore_errors=True)

    def test_01_manifest_integrity(self):
        manifest = manage_skills.get_manifest()
        self.assertGreaterEqual(len(manifest), 1300, 'O manifesto deve conter pelo menos 1300 skills indexadas.')
        self.assertIn('python-fastapi-development', manifest)
        self.assertIn('supabase-postgres-best-practices', manifest)
        self.assertIn('webapp-testing', manifest)

    def test_02_fastapi_routing(self):
        res = auto_route.route('criar endpoint fastapi com pydantic e rotas', top_k=2)
        activated = res.get('activated', [])
        self.assertTrue(
            any('fastapi' in s or 'api' in s for s in activated),
            f'Deveria ativar skill de fastapi/api, ativou: {activated}'
        )

    def test_03_supabase_routing(self):
        res = auto_route.route('criar tabela no supabase com rls e migrations', top_k=2)
        activated = res.get('activated', [])
        self.assertTrue(
            any('supabase' in s for s in activated),
            f'Deveria ativar skill de supabase, ativou: {activated}'
        )

    def test_04_playwright_routing(self):
        res = auto_route.route('configurar testes e2e automatizados com playwright', top_k=2)
        activated = res.get('activated', [])
        self.assertTrue(
            any('test' in s or 'playwright' in s for s in activated),
            f'Deveria ativar skill de testes, ativou: {activated}'
        )

    def test_05_excel_reports_routing(self):
        res = auto_route.route('exportar relatorio de orcamentos em planilha excel openpyxl', top_k=2)
        activated = res.get('activated', [])
        self.assertTrue(
            any('xlsx' in s or 'pdf' in s for s in activated),
            f'Deveria ativar skill de excel/xlsx, ativou: {activated}'
        )

    def test_06_pinned_skills_not_stealing_slots(self):
        manage_skills.pin(['supabase-postgres-best-practices'])
        res = auto_route.route('criar tabela no supabase e endpoint fastapi', top_k=2)
        activated = res.get('activated', [])
        self.assertNotIn('supabase-postgres-best-practices', activated, 'Skill ja fixada nao deve roubar vaga de ativacao.')
        manage_skills.unpin(['supabase-postgres-best-practices'])

    def test_07_native_folders_protected_during_reset(self):
        skills_dir = manage_skills.get_active_dir()
        native_dir = skills_dir / 'minha-skill-nativa'
        native_dir.mkdir(parents=True, exist_ok=True)
        (native_dir / 'SKILL.md').write_text('# Nativa', encoding='utf-8')

        manage_skills.add(['xlsx'])
        manage_skills.reset()

        self.assertTrue(native_dir.exists(), 'Diretorio nativo local NUNCA deve ser removido pelo reset.')
        self.assertFalse((skills_dir / 'xlsx').exists(), 'Junction temporaria DEVE ser removida pelo reset.')

    def test_08_hook_stop_json_contract(self):
        hook_path = ROOT / 'scripts' / 'hook_stop.py'
        p = subprocess.Popen(
            [sys.executable, str(hook_path)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        out, err = p.communicate(json.dumps({'workspacePaths': [str(self.tmp_ws)]}))
        self.assertEqual(p.returncode, 0, f'Hook retornou codigo de erro: {err}')
        parsed = json.loads(out.strip())
        self.assertIn('decision', parsed, 'Hook Stop deve retornar JSON valido com decision.')

    def test_09_hook_pre_invocation_json_contract(self):
        hook_path = ROOT / 'scripts' / 'hook_pre_invocation.py'
        p = subprocess.Popen(
            [sys.executable, str(hook_path)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        out, err = p.communicate(json.dumps({'transcriptPath': 'test_fake.jsonl'}))
        self.assertEqual(p.returncode, 0)
        parsed = json.loads(out.strip())
        self.assertIsInstance(parsed, dict, 'Hook PreInvocation deve retornar objeto JSON.')

    def test_10_path_triggered_routing(self):
        res = auto_route.route('ajustar o arquivo migrations_001.sql', top_k=2)
        activated = res.get('activated', [])
        self.assertTrue(
            any('supabase' in s for s in activated),
            f'Extensao .sql deve acionar skills de banco/supabase, ativou: {activated}'
        )

    def test_11_two_tier_domain_classification(self):
        block = auto_route.detect_primary_block('otimizar indices da tabela postgres')
        self.assertEqual(block, 'database', 'Deve classificar o dominio tematico como database.')

    def test_12_skill_affinity_companion_ranking(self):
        auto_route.load_rules()
        companions = auto_route.SKILL_AFFINITY.get('python-fastapi-development', [])
        self.assertIn('api-designer', companions, 'api-designer deve ser companion de python-fastapi-development.')

    def test_13_binary_index_cache(self):
        idx = auto_route.get_index()
        self.assertIsNotNone(idx)
        self.assertGreaterEqual(len(idx.manifest), 1300)
        cache_path = ROOT / '.agent' / 'index_cache.pkl'
        self.assertTrue(cache_path.exists(), 'Cache binario index_cache.pkl deve ser gerado no disco.')

    def test_14_empty_prompt_handling(self):
        res = auto_route.route('', top_k=2)
        self.assertEqual(res.get('status'), 'empty_prompt', 'Prompt vazio deve retornar status empty_prompt imediatamente sem gastar tokens.')
        self.assertEqual(len(res.get('activated', [])), 0)

    def test_15_tech_terms_not_blocked_by_generic_terms(self):
        res = auto_route.route('melhorar o backend fastapi', top_k=2)
        activated = res.get('activated', [])
        self.assertTrue(
            any('fastapi' in s or 'api' in s for s in activated),
            f'Consultas com termos como "backend fastapi" nao devem ser rejeitadas por generic_terms, ativou: {activated}'
        )

    def test_16_path_trigger_already_pinned(self):
        # Fixa as skills de .py para testar quando todas do path ja estao pinned
        manage_skills.pin(['python-fastapi-development', 'api-designer'])
        try:
            res = auto_route.route('editar o arquivo server.py', top_k=2)
            self.assertEqual(res.get('status'), 'already_satisfied_by_pinned')
        finally:
            manage_skills.unpin(['python-fastapi-development', 'api-designer'])

    def test_17_path_traversal_guard_in_remove(self):
        outside_path = ROOT.parent / "unsafe_file.txt"
        # Deve recusar exclusao silenciosa ou alertar sem levantar excecao
        try:
            manage_skills.remove_items_batch([outside_path])
        except Exception as e:
            self.fail(f"remove_items_batch nao deve quebrar ao receber path externo: {e}")

    def test_18_mcp_scoped_pin_unpin(self):
        import mcp_server
        res = mcp_server.handle_pin_skill({"skill_id": "api-designer"})
        self.assertIn("Skills fixadas", res["content"][0]["text"])
        res_unpin = mcp_server.handle_unpin_skill({"skill_id": "api-designer"})
    def test_19_ponytail_custom_skill_resolution(self):
        # Verifica se o find_skill_source encontra a skill customizada ponytail
        src, origin = manage_skills.find_skill_source("ponytail")
        self.assertIsNotNone(src, "Ponytail deve ser localizada pelo gerenciador de skills.")
        self.assertEqual(origin, "custom-router", "Ponytail deve vir de custom-router.")
    def test_20_in_memory_index_cache_invalidation(self):
        idx1 = auto_route.get_index()
        self.assertIsNotNone(idx1)
        expected_mtime = (
            auto_route.MANIFEST_PATH.stat().st_mtime,
            auto_route.RULES_PATH.stat().st_mtime,
            auto_route._get_custom_mtime()
        )
        self.assertEqual(auto_route._CACHED_MTIME, expected_mtime)

    def test_21_taste_skill_routing_and_affinity(self):
        src, origin = manage_skills.find_skill_source("taste-skill")
        self.assertIsNotNone(src, "taste-skill deve ser localizada pelo gerenciador de skills.")
        self.assertEqual(origin, "custom-router", "taste-skill deve vir de custom-router.")
        self.assertTrue((src / "SKILL.md").exists(), "SKILL.md de taste-skill deve existir.")
        # Verifica se taste-skill está presente na matriz de afinidade de frontend-design
        companions = auto_route.SKILL_AFFINITY.get("frontend-design", [])
        self.assertIn("taste-skill", companions, "taste-skill deve ser companion de frontend-design.")

    def test_22_intent_verb_refactor_routes_ponytail(self):
        """Prompt com verbos de intenção de refatoração deve priorizar ponytail."""
        res = auto_route.route("refatore e enxugue o código deste módulo", top_k=2)
        self.assertEqual(res["status"], "routed")
        self.assertIn("ponytail", res["skills"])

    def test_23_intent_verb_aesthetic_routes_taste_skill(self):
        """Prompt com verbos estéticos deve priorizar taste-skill sobre genéricos."""
        res = auto_route.route("redesenhe a interface com estética moderna e clean anti-slop", top_k=2)
        self.assertEqual(res["status"], "routed")
        self.assertIn("taste-skill", res["skills"])

    def test_24_quality_tier_ranking_boost(self):
        """Skills de tier Gold devem receber boost qualitativo sobre skills comuns."""
        index = auto_route.get_index()
        results = index.score("audite a segurança e crie validação com zod")
        skills_ranked = [r[1] for r in results]
        self.assertTrue(len(skills_ranked) > 0)
        # zod-validation-expert e supabase-postgres-best-practices são Gold
        top_two = skills_ranked[:2]
        self.assertTrue(
            "zod-validation-expert" in top_two or "supabase-postgres-best-practices" in top_two,
            f"Esperado gold tier no topo, obtido: {top_two}"
        )

    def test_25_mcp_resource_read_active_junction(self):
        """Verifica se recursos MCP skills://active/<sid> leem corretamente junctions sem falso positivo de traversal."""
        import mcp_server
        manage_skills.add(["supabase-postgres-best-practices"])
        req = {
            "jsonrpc": "2.0",
            "id": "test-res",
            "method": "resources/read",
            "params": {"uri": "skills://active/supabase-postgres-best-practices"}
        }
        # Invocamos diretamente a lógica de resources/read
        uri = req["params"]["uri"]
        raw_sid = uri.replace("skills://active/", "").strip("/")
        sid = mcp_server.validate_skill_id(raw_sid)
        cur_active = manage_skills.get_active_dir()
        active_item = cur_active / sid
        self.assertTrue(active_item.exists(), "Item ativo deve existir.")
        md_path = active_item / "SKILL.md"
        self.assertTrue(md_path.exists(), "SKILL.md deve existir dentro do item ativo.")
        content = md_path.read_text(encoding="utf-8", errors="ignore")
        self.assertNotIn("Acesso negado", content)
        self.assertIn("supabase", content.lower())

    def test_26_dynamic_skills_custom_discovery(self):
        """Verifica se get_manifest() auto-descobre pastas em skills_custom."""
        manifest = manage_skills.get_manifest()
        self.assertIn("ponytail", manifest)
        self.assertIn("taste-skill", manifest)

    def test_27_init_and_lint_skill(self):
        """Verifica scaffolding e linting de novas skills."""
        import shutil
        dummy_name = "test-scaffold-skill"
        dummy_dir = auto_route.ROOT / "skills_custom" / dummy_name
        try:
            skill_file = manage_skills.init_skill(dummy_name, "Skill de teste para validacao de scaffolding.")
            self.assertIsNotNone(skill_file)
            self.assertTrue(skill_file.exists())
            # Lint deve aprovar a skill gerada pelo template
            passed = manage_skills.lint_skill(dummy_name)
            self.assertTrue(passed)

            # Teste de parsing do GitHub spec
            o, r, sub, name = manage_skills._parse_github_spec("vercel-labs/skills@find-skills")
            self.assertEqual(o, "vercel-labs")
            self.assertEqual(r, "skills")
            self.assertEqual(sub, "find-skills")
            self.assertEqual(name, "find-skills")
        finally:
            if dummy_dir.exists():
                shutil.rmtree(dummy_dir, ignore_errors=True)

    def test_28_tdd_and_diagnosing_bugs_routing(self):
        """Verifica se as skills tdd e diagnosing-bugs são roteadas corretamente."""
        res_tdd = auto_route.route("desenvolva este endpoint usando tdd e red-green-refactor", top_k=2)
        self.assertIn("tdd", res_tdd["skills"])

        res_debug = auto_route.route("preciso debugar e investigar esse erro que está quebrando o sistema", top_k=2)
        self.assertIn("diagnosing-bugs", res_debug["skills"])

        res_design = auto_route.route("preciso desacoplar e modularizar a interface deste modulo criando deep modules", top_k=2)
        self.assertIn("codebase-design", res_design["skills"])

if __name__ == '__main__':
    unittest.main()


