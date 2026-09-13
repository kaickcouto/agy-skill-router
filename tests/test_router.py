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

if __name__ == '__main__':
    unittest.main()
