"""Keep processing provenance and documented paths correct after rearrangements."""
import ast
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from urllib.parse import unquote

from algorithms.support.common import ROOT, processing_code_hashes


class ProjectLayoutTests(unittest.TestCase):
    def test_launcher_preserves_app_options_from_another_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            interpreter = Path(directory)/'python stub'
            interpreter.write_text('#!'+sys.executable+'\nimport json,os,sys\nprint(json.dumps({"args":sys.argv[1:],"cwd":os.getcwd(),"threads":os.environ["OPENBLAS_NUM_THREADS"],"omp":os.environ["OMP_NUM_THREADS"]}))\n')
            interpreter.chmod(0o700)
            result = subprocess.run(['bash',str(ROOT/'launch.sh'),'--help','--port','8891'],
                                    cwd=directory,capture_output=True,text=True,timeout=15,
                                    env=dict(os.environ,STUDIO_PYTHON=str(interpreter),OPENBLAS_NUM_THREADS='8',OMP_NUM_THREADS='8'))
            self.assertEqual(result.returncode,0,result.stderr)
            data=json.loads(result.stdout)
            self.assertEqual(data['args'],['app.py','--help','--port','8891'])
            self.assertEqual(data['cwd'],str(ROOT))
            self.assertEqual((data['threads'],data['omp']),('1','1'))

    def test_launcher_rejects_an_explicit_missing_interpreter(self):
        with tempfile.TemporaryDirectory() as directory:
            result = subprocess.run(['bash',str(ROOT/'launch.sh'),'--help'],cwd=directory,
                                    capture_output=True,text=True,timeout=15,
                                    env=dict(os.environ,STUDIO_PYTHON=str(Path(directory)/'missing-python')))
            self.assertEqual(result.returncode,1)
            self.assertIn('Python environment missing',result.stderr)

    def test_code_snapshot_tracks_algorithm_changes_and_ignores_supporting_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            files = {
                'app.py':'# app\n', 'process_bag.py':'# CLI\n',
                'algorithms/support/pipeline.py':'# processing\n',
                'algorithms/livox/new_method.py':'# sensor method\n',
                'docs/validation/evidence/check.py':'# verification\n',
                '.venv/site-packages/library.py':'# dependency\n',
                'results/example/generated.py':'# output\n',
                'verification/old_run/check.py':'# local evidence\n'
            }
            for name, text in files.items():
                path = root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(text)
            hashes = processing_code_hashes(root)
            self.assertEqual(set(hashes), {'app.py','process_bag.py','algorithms/support/pipeline.py','algorithms/livox/new_method.py'})
            (root / 'docs/validation/evidence/check.py').write_text('# changed evidence\n')
            self.assertEqual(hashes, processing_code_hashes(root))
            path = root / 'algorithms/livox/new_method.py'
            path.write_text('# changed sensor method\n')
            changed = processing_code_hashes(root)
            self.assertNotEqual(hashes[path.relative_to(root).as_posix()], changed[path.relative_to(root).as_posix()])
            self.assertEqual(changed['app.py'], hashlib.sha256((root / 'app.py').read_bytes()).hexdigest())

    def test_current_documentation_links_resolve(self):
        documents = [ROOT/'README.md', ROOT/'algorithms/README.md', ROOT/'results/README.md']
        for folder in ('docs','docs/guides','docs/validation'):
            documents.extend((ROOT/folder).glob('*.md'))
        for document in documents:
            self.assertTrue(document.is_file(), str(document))
            for target in re.findall(r'!?\[[^\]]*\]\(([^)]+)\)', document.read_text()):
                if '://' in target or target.startswith('#'):
                    continue
                with self.subTest(document=document.relative_to(ROOT), target=target):
                    path = document.parent / unquote(target.split('#')[0])
                    self.assertTrue(path.exists(), 'Broken documentation link: '+str(path))

    def test_runtime_sources_use_package_imports_and_project_data_paths(self):
        legacy = {'common','bag_io','calibration','camera_localization','localization','sensors','timing',
                  'scan_reader','scan_variability','visuals','timing_visualization','batch_analysis',
                  'job_registry','pipeline','batch_worker'}
        hashes = processing_code_hashes()
        self.assertIn('algorithms/support/pipeline.py', hashes)
        for folder in ('algorithms','bagfiles','calibrations','results','static','templates'):
            self.assertTrue((ROOT/folder).is_dir(), folder)
        self.assertTrue((ROOT/'config.json').is_file())
        for relative in hashes:
            tree = ast.parse((ROOT/relative).read_text(), filename=relative)
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom):
                    self.assertNotIn(node.module, legacy, relative)
                elif isinstance(node, ast.Import):
                    for alias in node.names:
                        self.assertNotIn(alias.name, legacy, relative)


if __name__ == '__main__':
    unittest.main()
