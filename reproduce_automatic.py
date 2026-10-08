"""Reproduce the automatic ten-capture timing model from saved observations."""
import csv
import json
from pathlib import Path
from timing import fit_multi


def main():
    root = Path(__file__).resolve().parent
    run = json.loads((root / 'docs/validation/reference/published_automatic.json').read_text())['id']
    folder = root / 'results' / run
    with (folder / 'timing/phase_observations.csv').open() as stream:
        rows = list(csv.DictReader(stream))
    for row in rows:
        for key in ('omega_deg_s', 'phase_delta_deg', 'phase_delta_mod120_deg',
                    'phase_residual_std_deg', 'phase_period_deg'):
            if row.get(key):
                row[key] = float(row[key])
    model, _ = fit_multi(rows)
    expected = json.loads((folder / 'timing/overall_offset.json').read_text())
    for key in ('candidate_tau_ms', 'standard_error_ms', 'phase_residual_std_deg',
                'student_t_95_low_ms', 'student_t_95_high_ms'):
        if abs(model[key] - expected[key]) > 1e-9:
            raise RuntimeError('Automatic mismatch: ' + key)
    print(json.dumps(model, indent=2))


if __name__ == '__main__':
    main()
