"""The ``flinspect`` console script (argparse only; no click/typer).

Command groups are registered side by side in :func:`main` — today only the
Track B ``kernel`` group exists; the relational track's ``check`` / ``report``
commands (DESIGN §4 Phase 4) plug in as sibling ``_add_*_group`` calls.

Import discipline: this module (and everything it pulls in) must stay
widget-free — no ipywidgets/jupyter imports — so the CLI works in a bare venv.

``flinspect kernel`` — the Track B kernel-verification pipeline, driven by a
declarative manifest (``kernels.toml``; see ``flinspect/kernel_bank.py`` for
the schema). Manifest resolution: ``--kernels PATH`` > ``$FLINSPECT_KERNELS``
> ``./kernels.toml``.

    flinspect kernel list        # kernels in the manifest + basic status
    flinspect kernel show NAME   # print one kernel's generated Lean defs
    flinspect kernel generate    # (re)write the generated Lean modules
    flinspect kernel verify      # regenerate + byte-diff against the committed
                                 # files, then `lake build` if lake is on PATH
                                 # (Track B's CI gate; non-zero exit on drift
                                 # or build failure)
"""

from __future__ import annotations

import argparse
import difflib
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Optional

from flinspect import kernel_bank as kb
from flinspect.kir import UnsupportedConstruct
from flinspect.lean_printer import print_kernel

_DIFF_CONTEXT_LINES = 40


def _load(args: argparse.Namespace) -> kb.Manifest:
    return kb.load_manifest(kb.resolve_manifest_path(args.kernels))


def _describe_side(label: str, detail: str, path: Path) -> str:
    status = "ok" if path.exists() else f"MISSING {path}"
    return f"    {label:8s} {detail}  [{status}]"


# --------------------------------------------------------------------------- #
# kernel subcommands
# --------------------------------------------------------------------------- #

def _cmd_list(args: argparse.Namespace) -> int:
    m = _load(args)
    print(f"manifest: {m.path}  ({len(m.kernels)} kernel(s))")
    for e in m.kernels:
        print(e.name)
        if e.fortran is not None:
            nest = f", loop nest {e.fortran.nest}" if e.fortran.nest else ""
            print(_describe_side(
                "fortran:", f"subroutine '{e.fortran.subroutine}'{nest} "
                f"in {e.fortran_dump_label}", e.fortran.dump))
        if e.cpp is not None:
            print(_describe_side(
                "cpp:", f"function '{e.cpp.function}' in {e.cpp_header_label}",
                e.cpp.header))
    outs = [("fortran", m.fortran), ("cpp", m.cpp)]
    for side, cfg in outs:
        if cfg is not None:
            state = "present" if cfg.out.exists() else "not yet generated"
            print(f"{side} output: {cfg.out}  [{state}]")
    return 0


def _cmd_show(args: argparse.Namespace) -> int:
    m = _load(args)
    e = m.kernel(args.name)
    shown = []
    if e.fortran is not None:
        shown.append(print_kernel(kb.extract_fortran_entry(e),
                                  provenance=kb.fortran_provenance(e)))
    if e.cpp is not None:
        if shutil.which(e.cpp.clang):
            shown.append(print_kernel(kb.extract_cpp_entry(e),
                                      provenance=kb.cpp_provenance(e)))
        else:
            print(f"note: '{e.cpp.clang}' not on PATH — skipping the C++ side",
                  file=sys.stderr)
    print("\n".join(shown), end="")
    return 0


def _extract_verbosely(entries, extract, provenance) -> list:
    rendered = []
    for e in entries:
        kernel = extract(e)
        rendered.append((kernel, provenance(e)))
        print(f"extracted {kernel.name}: "
              f"params={[p.name for p in kernel.params]} "
              f"locals={[p.name for p in kernel.locals]}")
    return rendered


def _cmd_generate(args: argparse.Namespace) -> int:
    m = _load(args)
    if not args.skip_fortran and m.fortran is not None:
        text = kb.render_fortran(m, _extract_verbosely(
            kb.fortran_entries(m), kb.extract_fortran_entry,
            kb.fortran_provenance))
        m.fortran.out.write_text(text)
        print(f"wrote {m.fortran.out}")
    if not args.skip_cpp and m.cpp is not None:
        text = kb.render_cpp(m, _extract_verbosely(
            kb.cpp_entries(m), kb.extract_cpp_entry, kb.cpp_provenance))
        m.cpp.out.write_text(text)
        print(f"wrote {m.cpp.out}")
    return 0


def _verify_side(side: str, fresh: str, committed_path: Path) -> bool:
    """Byte-diff one regenerated module against its committed file."""
    if not committed_path.is_file():
        print(f"DRIFT [{side}]: {committed_path} does not exist — "
              f"run `flinspect kernel generate`")
        return False
    committed = committed_path.read_text()
    if fresh == committed:
        print(f"ok [{side}]: {committed_path.name} matches a fresh regeneration")
        return True
    fd, tmp_name = tempfile.mkstemp(prefix=f"{committed_path.stem}.",
                                    suffix=".fresh.lean")
    os.close(fd)
    tmp = Path(tmp_name)
    tmp.write_text(fresh)
    print(f"DRIFT [{side}]: {committed_path} differs from a fresh "
          f"regeneration (written to {tmp})")
    diff = list(difflib.unified_diff(
        committed.splitlines(), fresh.splitlines(),
        fromfile=str(committed_path), tofile=str(tmp), lineterm=""))
    for line in diff[:_DIFF_CONTEXT_LINES]:
        print(line)
    if len(diff) > _DIFF_CONTEXT_LINES:
        print(f"... ({len(diff) - _DIFF_CONTEXT_LINES} more diff lines)")
    return False


def _cmd_verify(args: argparse.Namespace) -> int:
    m = _load(args)
    ok = True
    if not args.skip_fortran and m.fortran is not None:
        ok &= _verify_side("fortran", kb.render_fortran(m), m.fortran.out)
    if not args.skip_cpp and m.cpp is not None:
        if shutil.which(m.cpp.clang) is None:
            print(f"error: '{m.cpp.clang}' not on PATH — cannot verify the "
                  f"C++ side (pass --skip-cpp to verify the Fortran side only)")
            ok = False
        else:
            ok &= _verify_side("cpp", kb.render_cpp(m), m.cpp.out)
    if m.lake_dir is not None:
        if shutil.which("lake") is None:
            print("note: `lake` not on PATH — skipping the Lean build tier of "
                  "the gate (activate a Lean toolchain to run it)")
        elif not ok:
            print("skipping `lake build` — fix the drift above first")
        else:
            print(f"running `lake build` in {m.lake_dir} ...")
            proc = subprocess.run(["lake", "build"], cwd=m.lake_dir)
            if proc.returncode != 0:
                print(f"FAIL: lake build exited {proc.returncode}")
                ok = False
            else:
                print("ok [lean]: lake build succeeded")
    return 0 if ok else 1


# --------------------------------------------------------------------------- #
# Wiring
# --------------------------------------------------------------------------- #

def _add_kernel_group(sub: argparse._SubParsersAction) -> None:
    kernel = sub.add_parser(
        "kernel", help="Track B kernel bank: list, show, generate, verify")
    ksub = kernel.add_subparsers(dest="kernel_command", required=True,
                                 metavar="SUBCOMMAND")
    manifest_opt = argparse.ArgumentParser(add_help=False)
    manifest_opt.add_argument(
        "--kernels", metavar="PATH", default=None,
        help=f"kernel manifest (default: ${kb.MANIFEST_ENV}, "
             f"then ./{kb.MANIFEST_FILENAME})")

    p = ksub.add_parser("list", parents=[manifest_opt],
                        help="kernels in the manifest + basic status")
    p.set_defaults(func=_cmd_list)

    p = ksub.add_parser("show", parents=[manifest_opt],
                        help="print one kernel's generated Lean defs")
    p.add_argument("name", metavar="NAME")
    p.set_defaults(func=_cmd_show)

    skip_opts = argparse.ArgumentParser(add_help=False)
    skip_opts.add_argument("--skip-fortran", action="store_true")
    skip_opts.add_argument("--skip-cpp", action="store_true")

    p = ksub.add_parser("generate", parents=[manifest_opt, skip_opts],
                        help="(re)write the generated Lean modules")
    p.set_defaults(func=_cmd_generate)

    p = ksub.add_parser(
        "verify", parents=[manifest_opt, skip_opts],
        help="regenerate, byte-diff against the committed files, lake build "
             "(non-zero exit on drift or failure)")
    p.set_defaults(func=_cmd_verify)


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="flinspect",
        description="flang-based inspection tooling for large Fortran HPC "
                    "codebases")
    sub = parser.add_subparsers(dest="command", required=True,
                                metavar="COMMAND")
    _add_kernel_group(sub)
    # Relational-track groups (`check`, `report`; DESIGN §4 Phase 4) register
    # here as siblings: _add_check_group(sub), _add_report_group(sub).
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except kb.ManifestError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    except UnsupportedConstruct as e:
        print(f"error: outside the supported kernel subset — {e}",
              file=sys.stderr)
        return 2
    except FileNotFoundError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
