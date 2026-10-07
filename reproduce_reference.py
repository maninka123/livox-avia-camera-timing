"""Reproduce the saved ten-capture timing model without the eight omitted bags."""
import csv
import json
from pathlib import Path
from timing import fit_multi

def main():
    root = Path(__file__).resolve().parent
    comparison = json.loads((root / 'docs/published_comparison.json').read_text())['id']
    folder = root / 'results' / comparison
    with (folder / 'phase_observations.csv').open() as stream:
        rows = list(csv.DictReader(stream))
    for row in rows:
        for key in ('omega_deg_s', 'phase_delta_mod120_deg', 'phase_residual_std_deg'):
            if key in row:
                row[key] = float(row[key])
    model, _ = fit_multi(rows)
    expected = json.loads((folder / 'model.json').read_text())
    for key in ('candidate_tau_ms', 'standard_error_ms', 'phase_residual_std_deg',
                'student_t_95_low_ms', 'student_t_95_high_ms'):
        if abs(model[key] - expected[key]) > 1e-9:
            raise RuntimeError('Reference mismatch: ' + key)
    print(json.dumps(model, indent=2))

if __name__ == '__main__':
    main()
