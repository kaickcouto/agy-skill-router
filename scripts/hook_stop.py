import sys
import os
import json
import io
import contextlib
from pathlib import Path

# Suporte UTF-8 no Windows
if sys.platform == 'win32':
    try:
        sys.stdin.reconfigure(encoding='utf-8')
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(SCRIPT_DIR))

def main():
    workspace = None
    try:
        raw_stdin = sys.stdin.read()
        if raw_stdin.strip():
            payload = json.loads(raw_stdin)
            ws_paths = payload.get('workspacePaths') or []
            if ws_paths:
                workspace = Path(ws_paths[0])
    except Exception:
        pass

    try:
        import manage_skills
        if workspace and workspace.exists():
            manage_skills.set_workspace(workspace)
        
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            manage_skills.reset()
    except Exception:
        pass

    sys.stdout.write(json.dumps({'decision': 'allow'}) + '\n')

if __name__ == '__main__':
    main()
