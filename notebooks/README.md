# groundline notebooks

An explanatory tour of groundline, in reading order. Every notebook consumes the
package **through the seam only** — `groundline.{ir, parse_forest, graph_view,
explorer}` — never `groundline.frontend.*` (see `docs/DESIGN.md`, principles
#4/#5). Each has a single parameter cell right after its introduction; paths are
`pathlib` throughout.

| Notebook | Teaches | Needs |
|---|---|---|
| `01_getting_started.ipynb` | The IR from scratch: entities, scope-qualified identity, relations, the three confidence strata and the may/must views, graphs, a first Explorer. | Nothing beyond the repo — runs anywhere off the committed `tests/f90` fixtures. |
| `02_explore_corpus.ipynb` | The interactive `Explorer` over the real 458-file MOM6 + FMS2 corpus, and the same neighbourhood data programmatically via `graph_view`. | Corpus access (below). |
| `03_module_dependencies.ipynb` | Module-level structure: `get_module_dependency_graph()`, fan-in/out, acyclicity, subproject partitioning, "which parts of FMS2 does MOM6 actually need", type-extension coupling, an ipycytoscape neighbourhood render. | Corpus access. |
| `04_confidence_queries.ipynb` | The may/must lattice as a query substrate: stratum censuses, unresolved-target classification, must-vs-may reachability with witnessing paths — a preview of the Phase 5 query layer. | Corpus access. |

## Launching

The repo venv must be self-sufficient and the (possibly broken) `~/.local`
user site must stay out of the way, so always launch with `PYTHONNOUSERSITE=1`:

```bash
cd dev-utils/groundline
PYTHONNOUSERSITE=1 .venv/bin/jupyter lab notebooks/
```

If the venv doesn't exist yet (or imports fail on missing packages):

```bash
python3 -m venv .venv
PYTHONNOUSERSITE=1 .venv/bin/pip install -e '.[dev]'
```

Why the env var: on machines where `~/.local` holds a broken package (e.g. a
pandas without its numpy), the user site *shadows* the venv and
`import groundline.explorer` fails on an unrelated pandas error. Conversely, a
venv populated *without* `PYTHONNOUSERSITE=1` can silently satisfy transitive
dependencies from the user site and then break when it's excluded — which is
why the install command above carries the env var too.

## Running on JupyterHub

On a JupyterHub (e.g. NCAR's), the launch section above does not apply: the Hub
serves a *central* JupyterLab, so neither the venv's kernel nor the widget
JavaScript is visible to it by default. A widget is two halves — Python in the
kernel, JS in the Lab frontend — and both must be wired up, once per machine:

```bash
cd dev-utils/groundline

# 1. Kernel half: register the venv as a named kernel ...
PYTHONNOUSERSITE=1 .venv/bin/python -m ipykernel install --user \
    --name groundline --display-name "Python (groundline)"
# ... and bake PYTHONNOUSERSITE=1 into it (Hub-launched kernels won't inherit
# your shell env), by adding to ~/.local/share/jupyter/kernels/groundline/kernel.json:
#     "env": {"PYTHONNOUSERSITE": "1"}

# 2. Frontend half: expose the cytoscape labextension to the Hub's JupyterLab.
#    (Static JS only — no Python lands in ~/.local/lib.)
cp -r .venv/share/jupyter/labextensions/jupyter-cytoscape \
      ~/.local/share/jupyter/labextensions/
```

Then **restart your Jupyter server** (Hub Control Panel → Stop My Server →
relaunch — labextensions are scanned at server start), hard-refresh the browser,
and open notebooks with the **"Python (groundline)"** kernel.

Symptoms if a half is missing: `ModuleNotFoundError: groundline` or a numpy/
pandas ImportError → wrong kernel or missing `env` entry (half 1); dropdowns
render but the graph canvas shows *"Failed to load model class 'CytoscapeModel'
from module 'jupyter-cytoscape'"* → missing labextension (half 2).

## The corpus

Notebooks 02–04 read a corpus of with-sema parse-tree dumps
(`flang -fc1 -fdebug-dump-parse-tree`, files named `*_ptree`). The corpus root
comes from the `GROUNDLINE_DUMPS` environment variable, defaulting to the one on
NCAR's glade filesystem:

```
/glade/work/altuntas/turbo-stack/bin/flang_ptree/MOM6_using_FMS2/   # 458 dumps: FMS2, MOM6, MOM6-infra
```

**There is no TIM corpus yet** — `MOM6_using_TIM/` is an empty skeleton because
the dump-only toolchain cannot build AMReX (`docs/DEVLOG.md`, 2026-05-28). When
one exists, point `GROUNDLINE_DUMPS` at it; nothing in the notebooks is
FMS2-specific.

Without glade access, generate dumps for any Fortran tree you can compile (see
`tests/f90/gen_ptree_files.sh` for the invocation) — or start with notebook 01,
which needs no corpus at all.

## Conventions & output policy

- **Outputs are stripped before committing.** Corpus-derived outputs are bulky
  and machine-specific; the executed state is reproducible in ~1 min. Strip
  with:

  ```bash
  PYTHONNOUSERSITE=1 .venv/bin/jupyter nbconvert --clear-output --inplace notebooks/*.ipynb
  ```

- **Every committed notebook must execute end-to-end headlessly** (from the
  `notebooks/` directory, so relative paths resolve):

  ```bash
  PYTHONNOUSERSITE=1 .venv/bin/jupyter nbconvert --execute --to notebook \
      --stdout notebooks/<nb>.ipynb > /dev/null
  ```

- One parameter cell per notebook, immediately after the intro; edit it (or set
  the environment variables it reads) rather than hunting for paths in the body.
- Seam discipline: if a notebook needs a fact the IR lacks, that is a finding to
  record (`docs/DEVLOG.md`), not a reason to import `groundline.frontend.*`.
