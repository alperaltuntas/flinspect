#!/usr/bin/env python3
"""Regenerate the Track B generated Lean models — both sides of the theorems.

- ``Pilot/Generated.lean``      from the MOM6 production with-sema flang dump
- ``Pilot/GeneratedCpp.lean``   from the TIM kernel header via clang JSON AST

Track B printer driver (DESIGN §2.3). Deterministic: same dump / same header +
same clang in, same Lean out. The clang invocation is pinned here (paths as
constants, CLI overrides) and stamped into GeneratedCpp.lean's header comment;
the JSON is an in-memory intermediate, never committed. Run from anywhere:

    python lean/pilot/generate.py [--corpus DIR] [--cpp-header-dir DIR]
                                  [--cpp-include DIR ...] [--clang EXE]
                                  [--skip-fortran | --skip-cpp]
"""

import argparse
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from flinspect.frontend.clang_kernel import clang_version, extract_kernel \
    as extract_cpp_kernel                                       # noqa: E402
from flinspect.frontend.flang_kernel import extract_kernel, \
    extract_loop_kernel                                         # noqa: E402
from flinspect.kir import pointize                             # noqa: E402
from flinspect.lean_printer import print_module                # noqa: E402

DEFAULT_CORPUS = "/glade/work/altuntas/turbo-stack/bin/flang_ptree/MOM6_using_FMS2"

# Whole-subroutine kernels: (dump file relative to corpus, subroutine name).
# Inline-loop kernels (rule B addressing): (dump rel path, subroutine,
# source-order nest ordinal, generated-def name) — the name records the
# branch↔kernel pairing, since an inline loop has no name of its own.
KERNELS = [
    ("MOM6/MOM_continuity_PPM.o_ptree", "ppm_limit_pos"),
    ("MOM6/MOM_continuity_PPM.o_ptree", "ppm_limit_cw84"),
    # zonal_edge_thickness: nest 1 = the do concurrent under CS%upwind_1st
    ("MOM6/MOM_continuity_PPM.o_ptree", "zonal_edge_thickness", 1,
     "edge_thickness_upwind"),
    # thickness_to_dz_3d nests, in source order: 1 = do-concurrent
    # non-Boussinesq, 2 = plain-DO non-Boussinesq, 3 = do-concurrent
    # Boussinesq, 4 = plain-DO Boussinesq. The plain-DO variants (the
    # default execution path; do_offload=.false.) are the banked ones —
    # rule A's schema lemma is their license.
    ("MOM6/MOM_interface_heights.o_ptree", "thickness_to_dz_3d", 4,
     "thickness_to_dz_3d_boussinesq"),
    ("MOM6/MOM_interface_heights.o_ptree", "thickness_to_dz_3d", 2,
     "thickness_to_dz_3d_nonboussinesq"),
]

# --- C++ side: pinned clang invocation (verified 2026-07-31, clang 21) -------
TURBO_ROOT = REPO.parents[1]
# the TIM kernel headers
DEFAULT_CPP_HEADER_DIR = str(TURBO_ROOT / "submodules/infra/TIM/mom/cpp")
DEFAULT_CPP_INCLUDE_DIRS = [
    # AMReX install (AMReX_REAL.H etc.)
    "/glade/work/altuntas/turbo-stack/bin/gnu/MOM6_using_TIM/amrex/install/include",
    # the TIM kernel headers themselves
    str(TURBO_ROOT / "submodules/infra/TIM/mom/cpp"),
    # mpi.h for AMReX's #include <mpi.h>
    "/glade/work/altuntas/llvm-hpc/include",
]
DEFAULT_CLANG = "clang++"

# (header file name in DEFAULT_CPP_HEADER_DIR, point-function name)
CPP_KERNELS = [
    ("mom_continuity_ppm_kernel.hpp", "ppm_limit_pos_point"),
    ("mom_continuity_ppm_kernel.hpp", "ppm_limit_cw84_point"),
    ("mom_continuity_ppm_kernel.hpp", "edge_thickness_upwind_point"),
    ("mom_interface_heights_kernel.hpp", "thickness_to_dz_3d_boussinesq_point"),
    ("mom_interface_heights_kernel.hpp",
     "thickness_to_dz_3d_nonboussinesq_point"),
]


def render(corpus: str) -> str:
    """The full Generated.lean text for KERNELS — also imported by the pytest
    golden test, so the committed file and the test can't drift apart."""
    rendered = []
    for entry in KERNELS:
        if len(entry) == 2:
            rel, sub = entry
            kernel = pointize(extract_kernel(Path(corpus) / rel, sub))
            prov = f"`{sub}` in `{rel}` (flang with-sema dump)"
        else:
            rel, sub, nest, name = entry
            kernel = pointize(
                extract_loop_kernel(Path(corpus) / rel, sub, nest, name))
            prov = (f"loop nest {nest} of `{sub}` in `{rel}` "
                    f"(flang with-sema dump)")
        rendered.append((kernel, prov))
        print(f"extracted {kernel.name}: "
              f"params={[p.name for p in kernel.params]} "
              f"locals={[p.name for p in kernel.locals]}")
    return print_module(rendered, namespace="TrackB.Generated")


def render_cpp(header_dir: str = DEFAULT_CPP_HEADER_DIR,
               include_dirs: list = DEFAULT_CPP_INCLUDE_DIRS,
               clang: str = DEFAULT_CLANG) -> str:
    """The full GeneratedCpp.lean text for CPP_KERNELS — imported by the pytest
    golden test just like :func:`render`. Provenance (clang version + the full
    pinned invocation) is stamped into the module header."""
    rendered = []
    for header_name, fn in CPP_KERNELS:
        header = Path(header_dir) / header_name
        try:
            display = str(header.resolve().relative_to(TURBO_ROOT))
        except ValueError:
            display = str(header)
        kernel = extract_cpp_kernel(header, fn, clang=clang,
                                    include_dirs=include_dirs)
        rendered.append((kernel, f"`{fn}` in `{display}` (clang JSON AST)"))
        print(f"extracted {fn}: params={[p.name for p in kernel.params]} "
              f"locals={[p.name for p in kernel.locals]}")
    includes = "\n".join(f"  -I{d}" for d in include_dirs)
    blurb = f"""\
Emitted by `flinspect.lean_printer` (Track B; DESIGN §2.3) from clang JSON ASTs
(`flinspect.frontend.clang_kernel`). Regenerate with `lean/pilot/generate.py`.
Fidelity against the hand-written pilot models is machine-checked in
`Pilot/FidelityCpp.lean`.

Extraction provenance (pinned):
  {clang_version(clang)}
  -std=c++20 -fsyntax-only -Xclang -ast-dump=json -Xclang -ast-dump-filter
{includes}"""
    return print_module(rendered, namespace="TrackB.GeneratedCpp", blurb=blurb)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--corpus", default=DEFAULT_CORPUS)
    ap.add_argument("--cpp-header-dir", default=DEFAULT_CPP_HEADER_DIR)
    ap.add_argument("--cpp-include", action="append", default=None,
                    help="override the pinned -I dirs (repeatable)")
    ap.add_argument("--clang", default=DEFAULT_CLANG)
    ap.add_argument("--skip-fortran", action="store_true")
    ap.add_argument("--skip-cpp", action="store_true")
    args = ap.parse_args()

    pilot = Path(__file__).parent / "Pilot"
    if not args.skip_fortran:
        out = pilot / "Generated.lean"
        out.write_text(render(args.corpus))
        print(f"wrote {out}")
    if not args.skip_cpp:
        include_dirs = args.cpp_include or DEFAULT_CPP_INCLUDE_DIRS
        out = pilot / "GeneratedCpp.lean"
        out.write_text(render_cpp(args.cpp_header_dir, include_dirs, args.clang))
        print(f"wrote {out}")


if __name__ == "__main__":
    main()
