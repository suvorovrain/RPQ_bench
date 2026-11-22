"""Runner regressions; no dataset, containers or installed engines required."""
import copy
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

SCRIPTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS))
import smoke_250k as smoke
import benchmark_all as bench


class RunnerTests(unittest.TestCase):
    def test_cli_help_does_not_require_prepared_graph(self):
        with tempfile.TemporaryDirectory() as directory:
            # Import from a fresh tree, which has no Datasets directory at all.
            target = Path(directory) / 'Scripts/competitors'
            target.mkdir(parents=True)
            for name in ['smoke_250k.py', 'benchmark_all.py', 'prepare_basic.py']:
                (target / name).write_text((SCRIPTS / name).read_text())
            for name in ['smoke_250k.py', 'benchmark_all.py']:
                result = subprocess.run([sys.executable, target / name, '--help'], text=True, capture_output=True)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn('usage:', result.stdout)

    def test_pathrex_records_cover_two_optimizers_without_duplicates(self):
        queries = [{'id': str(i)} for i in [1, 2, 3, 5]]
        checks = [{'id': q['id'], 'note': f'optimizer={opt}'} for opt in smoke.PATHREX_OPTIMIZERS for q in queries]
        with patch.object(smoke, 'QUERIES', queries):
            smoke.validate_checks('pathrex', checks)
            bad = copy.deepcopy(checks)
            bad[-1] = bad[0]
            with self.assertRaisesRegex(ValueError, 'duplicate'):
                smoke.validate_checks('pathrex', bad)
            with self.assertRaises(ValueError):
                smoke.validate_checks('pathrex', checks[:-1])

    def test_gb_accepts_matrixmarket_layout_without_binary_index(self):
        query = {'id': '1', 'count': 2, 'pattern': 'p'}
        calls = []
        runner = SimpleNamespace(engine='rpqmatrixGB', args=SimpleNamespace(runs=4, warmups=1),
            run=lambda args: '1;2;1000000\n' * 5,
            add=lambda *args: calls.append(args))
        with tempfile.TemporaryDirectory() as directory, patch.object(smoke, 'DATA', Path(directory)), patch.object(smoke, 'QUERIES', [query]), patch.object(smoke, 'MANIFEST', {'labels': {'1': 'p'}, 'edges': 1}):
            bench.matrices(runner)
            self.assertEqual(calls[0][1], [1.0] * 4)
            runner.engine = 'rpqmatrix'
            with self.assertRaisesRegex(RuntimeError, 'index'):
                bench.matrices(runner)

    def test_wrong_counts_and_missing_samples_cannot_pass(self):
        query = {'id': '1', 'count': 2}
        runner = SimpleNamespace(args=SimpleNamespace(runs=1), add=lambda *args: self.fail('invalid sample accepted'))
        with patch.object(smoke, 'QUERIES', [query]):
            with self.assertRaisesRegex(ValueError, 'Wrong result count'):
                bench.parse_timing(runner, 'TIMING;1;0;1.0;999', 'native')
            with self.assertRaisesRegex(ValueError, 'Out-of-order'):
                bench.parse_timing(runner, 'TIMING;1;2;1.0;2', 'native')

    def test_resume_rejects_changed_inputs_versions_and_run_counts(self):
        current = dict(runs=4, warmups=1, queries=[{'id': '1', 'targets': [2]}],
            pathrex_optimizer='pang-hybrid', dataset_edges=1, dataset_vertices=2,
            source_sha256='source', runtime_lock={'image': 'sha256:fixed'},
            execution_fingerprint={'binary': 'sha256:binary'}, engines=['pathrex', 'duckdb'],
            host='linux', hostname='test-host', cpu_count=2, cpu_affinity=[0, 1], omp_threads=2, omp_env={})
        bench.validate_resume(copy.deepcopy(current), current)
        subset = copy.deepcopy(current)
        subset['engines'] = ['duckdb']
        bench.validate_resume(current, subset)
        for key in ['runs', 'warmups', 'queries', 'source_sha256', 'runtime_lock', 'execution_fingerprint', 'hostname', 'cpu_affinity', 'omp_env']:
            prior = copy.deepcopy(current)
            prior[key] = None
            with self.subTest(key=key), self.assertRaisesRegex(ValueError, key):
                bench.validate_resume(prior, current)
        prior = copy.deepcopy(current)
        prior['engines'] = ['pathrex']
        with self.assertRaisesRegex(ValueError, 'engines'):
            bench.validate_resume(prior, current)


if __name__ == '__main__':
    unittest.main()
