"""Package workers retain their request identity across app restarts."""
import subprocess
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from algorithms.support import job_registry


class WorkerLaunchTests(unittest.TestCase):
    def test_commands_allow_only_workers_and_resolve_request_paths(self):
        request = Path('results/example/request.json')
        for module in job_registry.WORKER_MODULES:
            command = job_registry.worker_command(module, request)
            self.assertEqual(command[1:3], ['-m', module])
            self.assertEqual(command[3], str(request.resolve()))
        with self.assertRaisesRegex(ValueError, 'Unknown processing worker'):
            job_registry.worker_command('unrelated.module', request)
        self.assertEqual(job_registry.ROOT, Path(job_registry.__file__).resolve().parents[2])

    @unittest.skipUnless(Path('/proc').is_dir(), 'Worker recovery uses Linux process identity')
    def test_live_package_workers_recover_and_reject_other_requests_or_workspaces(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            support = root / 'algorithms' / 'support'
            support.mkdir(parents=True)
            (root / 'algorithms' / '__init__.py').touch()
            (support / '__init__.py').touch()
            out = root / 'results' / 'example'
            out.mkdir(parents=True)
            request = out / 'request.json'
            request.write_text('{}')
            for module in job_registry.WORKER_MODULES:
                with self.subTest(module=module):
                    (support / (module.rsplit('.', 1)[1] + '.py')).write_text('import time\ntime.sleep(30)\n')
                    process = subprocess.Popen(job_registry.worker_command(module, request), cwd=root)
                    try:
                        with patch.object(job_registry, 'ROOT', root), patch.object(job_registry, 'workers', {}):
                            tick = None
                            for _ in range(40):
                                tick = job_registry.identity(process.pid, request)
                                if tick is not None:
                                    break
                                time.sleep(.02)
                            self.assertIsNotNone(tick)
                            self.assertIsNone(job_registry.identity(process.pid, out / 'other.json'))
                            with patch.object(job_registry, 'ROOT', root / 'different_workspace'):
                                self.assertIsNone(job_registry.identity(process.pid, request))
                            job_registry.remember('example', process, out)
                            job_registry.workers.clear()
                            recovered = job_registry.restore('example', out)
                            self.assertIsInstance(recovered, job_registry.RecoveredWorker)
                            self.assertIsNone(recovered.poll())
                            recovered.terminate()
                            process.wait(timeout=5)
                            self.assertIsNotNone(recovered.poll())
                    finally:
                        if process.poll() is None:
                            process.terminate()
                            process.wait(timeout=5)


if __name__ == '__main__':
    unittest.main()
