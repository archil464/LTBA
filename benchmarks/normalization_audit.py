"""Compare exact guarded DAG edits with StandardScaler and a variance audit."""
import argparse
from collections import defaultdict
from copy import deepcopy
from fractions import Fraction
import json
from pathlib import Path
from random import Random
from statistics import median
from time import perf_counter_ns

import numpy as np
import sklearn
from sklearn.preprocessing import StandardScaler

from benchmarks.guarded_dag_equivalence import GuardedDAG, Runner, category
from benchmarks.workbook_incremental import serialized


def fit_scales(mean, scales):
    return StandardScaler().fit(np.stack((mean - scales, mean + scales)))


class ScalerAudit:
    def __init__(self, samples, mean, scaler, names, *, incremental):
        self.samples = samples
        self.scaler = deepcopy(scaler)
        self.columns = [fit_scales(mean[i:i + 1], np.zeros(1))
                        for i in range(samples.shape[1])] if incremental else None
        self.values = self.scaler.transform(samples)
        self.names = names

    def edit(self, changes, fitted):
        guards, values = {}, {}
        affected = []
        for column in changes:
            before = category(self.scaler.var_[column])
            after = category(fitted.var_[column])
            if before != after:
                guards[f's{column}'] = after
            if fitted.scale_[column] != self.scaler.scale_[column]:
                affected.append(column)
            self.scaler.var_[column] = fitted.var_[column]
            self.scaler.scale_[column] = fitted.scale_[column]
        if self.columns is None:
            result = self.scaler.transform(self.samples)
            rows, columns = np.nonzero(result != self.values)
            values = {self.names[r, c]: str(Fraction(float(result[r, c]))) for r, c in zip(rows, columns)}
            self.values = result
        else:
            for column in affected:
                scaler = self.columns[column]
                scaler.scale_[0] = self.scaler.scale_[column]
                result = scaler.transform(self.samples[:, column:column + 1])[:, 0]
                for row in np.flatnonzero(result != self.values[:, column]):
                    values[self.names[row, column]] = str(Fraction(float(result[row])))
                self.values[:, column] = result
        return serialized({'values': values, 'guards': guards})


def run(rows, columns, rng):
    mean = np.arange(columns, dtype=np.int64) + 10
    offsets = ((np.arange(rows)[:, None] + np.arange(columns)[None, :]) % 19) - 9
    samples = mean + offsets
    names = np.asarray([[f'z{r}_{c}' for c in range(columns)] for r in range(rows)])
    inputs, formulas = {}, {}
    for column in range(columns):
        inputs[f's{column}'] = 0
        for row in range(rows):
            name = names[row, column]
            inputs[f'x{row}_{column}'] = int(offsets[row, column])
            formulas[name] = f'x{row}_{column}/s{column}'
    scales = np.zeros(columns, dtype=np.int64)
    initial = fit_scales(mean, scales)
    dag = Runner(GuardedDAG, formulas, inputs)
    scalers = {
        'sklearn_full': ScalerAudit(samples, mean, initial, names, incremental=False),
        'sklearn_incremental': ScalerAudit(samples, mean, initial, names, incremental=True),
    }
    timings = defaultdict(lambda: defaultdict(list))
    counts = defaultdict(list)
    exact_values = dag.values.copy()
    for cycle in range(20):
        batch = cycle % 2 == 1
        targets = list(range(columns)) if batch else [rng.randrange(columns)]
        for step, scale in enumerate((1, 2, 4, 1, 0)):
            kind = ('zero_unit' if step in (0, 4) else 'numeric') + ('_batch' if batch else '_local')
            before = scales.copy()
            scales[targets] = scale
            fitted = fit_scales(mean, scales)
            assert np.array_equal(fitted.var_, scales ** 2)
            assert np.array_equal(fitted.mean_, mean)
            assert np.array_equal(fitted.scale_, np.maximum(scales, 1))
            jobs = {
                'guarded_dag': lambda: dag.edit({f's{c}': scale for c in targets}),
                **{name: (lambda scaler=scaler: scaler.edit(targets, fitted))
                   for name, scaler in scalers.items()},
            }
            order = list(jobs)
            rng.shuffle(order)
            outputs = {}
            for name in order:
                start = perf_counter_ns()
                outputs[name] = jobs[name]()
                timings[kind][name].append((perf_counter_ns() - start) / 1e6)
            oracle = {names[r, c]: Fraction(int(offsets[r, c]), int(scales[c]) or 1)
                      for r in range(rows) for c in range(columns)}
            expected = {'guards': {f's{c}': category(scales[c]) for c in targets
                                  if category(before[c]) != category(scales[c])},
                        'values': {name: str(value) for name, value in oracle.items()
                                   if exact_values[name] != value}}
            assert set(outputs.values()) == {serialized(expected)}
            assert dag.values == oracle
            for scaler in scalers.values():
                assert np.array_equal(scaler.values, offsets / np.maximum(scales, 1))
            exact_values = oracle
            counts[kind].append(len(expected['values']))
    return dict(rows=rows, features=columns, validated_edits=sum(map(len, counts.values())),
                median_ms={kind: {engine: median(samples) for engine, samples in runs.items()}
                           for kind, runs in timings.items()},
                timings_ms=timings,
                median_changed_values={kind: median(values) for kind, values in counts.items()})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=Path('results/normalization_audit/report.json'))
    args = parser.parse_args()
    rng = Random(1729)
    rows = []
    for shape in [(128, 8), (512, 16)]:
        row = run(*shape, rng)
        rows.append(row)
        print(shape, row['median_ms'], flush=True)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps({
        'sklearn_version': sklearn.__version__, 'numpy_version': np.__version__,
        'scope': 'Fixed observation matrix and means; supplied fitted statistics from two-point synthetic '
                 'training sets, fitting outside timing. DAG receives pre-centered inputs. StandardScaler '
                 'full transform versus an incremental column adapter that skips unchanged effective '
                 'scales. All paths emit the same exact value and compact guard deltas as JSON. '
                 'Scales 0, 1, 2, 4 guarantee all results are exactly representable in binary64.',
        'rows': rows,
    }, indent=2) + '\n')


if __name__ == '__main__':
    main()
