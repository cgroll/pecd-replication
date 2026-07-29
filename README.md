# PECD Replication

Replicating [PECD](https://data.jrc.ec.europa.eu/dataset/pecd)'s (the
Pan-European Climate Database) wind and solar PV capacity-factor
methodology for Germany, from public data (ERA5 weather, MaStR plant
register, SMARD generation) — one building block toward forecasting the
DE-LU bidding zone's headline variables (wind, PV, residual load). See
[the book's introduction](book/markdown/index.md) for the full
motivation, methodology, and a validation ladder for each step.

Published as a [MyST](https://mystmd.org/) Jupyter Book at
https://cgroll.github.io/pecd-replication/. The data pipeline is managed
by [DVC](https://dvc.org/); dependencies by [uv](https://docs.astral.sh/uv/).

## Current status

Both workstreams are checked against SMARD's actual net generation over
the full 2019-2025 backtest, alongside PECD's own official product and
this project's original naive physics baseline:

| Workstream | PECD official × MaStR | Naive physics baseline | This project's own replication |
|---|---|---|---|
| Wind onshore | MAE 0.029, corr 0.985 | MAE 0.089, corr 0.931 | **MAE 0.065, corr 0.983** |
| Solar PV | MAE 0.016, corr 0.981 | MAE 0.057, corr 0.926 | **MAE 0.046, corr 0.937** |

Wind's own replication is essentially converged with PECD's own accuracy;
solar has closed much of the gap from the naive baseline but still has a
meaningfully larger unresolved gap than wind. See
[Current status](book/markdown/index.md#current-status-how-well-does-each-replication-work)
in the book for what's driving the remaining gaps and what's still open.

## Running it

```bash
# Install uv if you haven't already — https://docs.astral.sh/uv/
curl -LsSf https://astral.sh/uv/install.sh | sh

uv sync
```

```bash
make dry-run   # preview what would run
make run       # execute the pipeline (dvc repro)
make serve     # open http://localhost:3000 — live book preview
```

## Project layout

```
project-root/
├── pecdr/               # Python package — shared utilities
│   └── paths.py         # Centralized path config
├── pipeline/            # Numbered pipeline scripts (data acquisition + analysis)
├── book/                # MyST book source
│   ├── notebooks/       # Executed notebooks (DVC output, tracked in git)
│   ├── markdown/        # Static content, incl. the project introduction
│   └── myst.yml         # TOC and site settings
├── data/                # Git-ignored data (cached by DVC)
├── output/images/       # Figures (tracked in git)
├── dvc.yaml             # Pipeline DAG
├── dvc.lock             # Pipeline state (checksums) — tracked in git
└── contribution_conventions.md   # Detailed conventions for contributors/AI
```

See [contribution_conventions.md](contribution_conventions.md) for full
details on adding pipeline stages, writing analysis scripts, and DVC
usage.

## Common DVC commands

| Command | Effect |
|---------|--------|
| `dvc repro --dry` | Dry run — show what would execute |
| `dvc repro` | Run pipeline (only rebuilds what's out of date) |
| `dvc repro -f <stage>` | Force-re-run a specific stage |
| `dvc repro <stage>` | Build one specific stage (and its dependencies) |
| `dvc repro --force` | Re-run everything unconditionally |
| `dvc dag` | Print the pipeline DAG |

Prefer `dvc commit -f <stage>` over `dvc repro` when a stage's output was
already produced out-of-band (e.g. run manually) — `dvc repro` walks the
*entire* upstream graph and will silently re-run any stage missing from
`dvc.lock`, which can mean re-running an expensive upstream computation
just to refresh a cheap downstream one.
