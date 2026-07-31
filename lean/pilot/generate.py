#!/usr/bin/env python3
"""Regenerate Pilot/Generated.lean from the MOM6 production with-sema dump.

Track B printer driver (DESIGN §2.3). Deterministic: same dump in, same Lean
out. Run from anywhere:

    python lean/pilot/generate.py [--corpus DIR]
"""

import argparse
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from flinspect.frontend.flang_kernel import extract_kernel     # noqa: E402
from flinspect.kir import pointize                             # noqa: E402
from flinspect.lean_printer import print_module                # noqa: E402

DEFAULT_CORPUS = "/glade/work/altuntas/turbo-stack/bin/flang_ptree/MOM6_using_FMS2"

# (dump file relative to corpus, subroutine name)
KERNELS = [
    ("MOM6/MOM_continuity_PPM.o_ptree", "ppm_limit_pos"),
]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--corpus", default=DEFAULT_CORPUS)
    args = ap.parse_args()

    rendered = []
    for rel, sub in KERNELS:
        dump = Path(args.corpus) / rel
        kernel = pointize(extract_kernel(dump, sub))
        rendered.append((kernel, f"`{sub}` in `{rel}` (flang with-sema dump)"))
        print(f"extracted {sub}: params={[p.name for p in kernel.params]} "
              f"locals={[p.name for p in kernel.locals]}")

    out = Path(__file__).parent / "Pilot" / "Generated.lean"
    out.write_text(print_module(rendered, namespace="TrackB.Generated"))
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
