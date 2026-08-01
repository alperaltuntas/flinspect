"""The kernel bank: the kernel manifest (``kernels.toml``) and the
generation pipeline — load the manifest, extract both sides of every banked
pair through the :class:`~groundline.frontend.kernel_base.KernelFrontend` seam,
render both generated Lean modules.

This module replaces the Lean project's original ad-hoc ``generate.py`` driver. Nothing here
carries a machine path: every site-specific value — the directory of Fortran
dumps, the C++ sources and include dirs, the compiler, output locations —
lives in a declarative TOML manifest. The production (NCAR / turbo-stack)
instance is ``examples/turbo-stack.kernels.toml``; a self-contained toy
instance is ``examples/quickstart/kernels.toml``.

Manifest shape (stdlib ``tomllib``; string values support ``${ENV_VAR}``
expansion, and relative paths resolve against the manifest file's directory).
``[fortran]`` and ``[cpp]`` configure each language side once — inputs,
toolchain, output module; each ``[[kernel]]`` gives one kernel's location on
each side::

    [fortran]                       # the flang side (omit to disable)
    dumps = "..."                   # dir the kernels' `dump` values resolve under
    sources = "."                   # dir the kernels' `source` values resolve under
    compiler = "flang"              # runs on `source` kernels to dump them fresh
    generated = ".../GeneratedFtn.lean"   # module `kernel generate` writes
    namespace = "Groundline.GeneratedFtn"
    blurb = "..."                   # optional extra header-comment lines

    [cpp]                           # the clang side (omit to disable)
    sources = "."                   # dir the kernels' `source` values resolve under
    include_dirs = ["...", ...]     # pinned -I dirs (part of the kernel identity)
    compiler = "clang++"
    provenance_root = "..."         # optional: files display relative to this
    generated = ".../GeneratedCpp.lean"
    namespace = "Groundline.GeneratedCpp"
    blurb = "..."

    [lean]                          # optional: `kernel verify` checks proofs here
    project = "../lean/groundline"

    [[kernel]]
    name = "ppm_limit_pos"
    fortran = { dump = "MOM6/MOM_continuity_PPM.o_ptree",
                subroutine = "ppm_limit_pos" }      # + optional nest = N,
                                                    #   def_name = "..." for
                                                    #   rule-B inline loops
    cpp     = { source = "mom_continuity_ppm_kernel.hpp",
                function = "ppm_limit_pos_point" }
    pointize = true                 # license: this kernel is a loop nest;
                                    # reduce it to its per-point body

The Fortran side of a kernel names exactly one of ``dump`` (a pre-generated
with-sema dump — for kernels living inside codebases whose modules must be
built before flang can run) or ``source`` (a standalone Fortran file the
pipeline runs flang on, exactly as the C++ side runs clang on its
``source``).

Manifest resolution order (used by the CLI): explicit ``--kernels`` flag >
``$GROUNDLINE_KERNELS`` > ``./kernels.toml`` in the current directory. There is
deliberately no built-in default beyond that.

Trusted-base note: this module is packaging, not semantics — extraction and
printing are exactly the frontend/`kir`/`lean_printer` calls the old driver
made; a malformed manifest raises :class:`ManifestError` (refuse, don't guess).
"""

from __future__ import annotations

import os
import re
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from groundline.frontend.clang_kernel import ClangKernelFrontend, clang_version
from groundline.frontend.flang_kernel import (
    DUMP_FLAGS, FlangKernelFrontend, flang_version,
)
from groundline.frontend.kernel_base import CppKernelSpec, FortranKernelSpec
from groundline.kir import Kernel, UnsupportedConstruct, is_loop_nest, pointize
from groundline.lean_printer import print_module

MANIFEST_ENV = "GROUNDLINE_KERNELS"
MANIFEST_FILENAME = "kernels.toml"


class ManifestError(Exception):
    """A missing, malformed, or internally inconsistent kernel manifest."""


# --------------------------------------------------------------------------- #
# Manifest model
# --------------------------------------------------------------------------- #

@dataclass(frozen=True)
class FortranConfig:
    generated: Path
    namespace: str
    dumps: Optional[Path] = None     # root of the kernels' `dump` values
    sources: Path = Path(".")        # root of the kernels' `source` values
    compiler: str = "flang"
    blurb: str = ""


@dataclass(frozen=True)
class CppConfig:
    generated: Path
    namespace: str
    sources: Path
    include_dirs: tuple[str, ...] = ()
    compiler: str = "clang++"
    provenance_root: Optional[Path] = None
    blurb: str = ""


@dataclass(frozen=True)
class KernelEntry:
    """One banked pair. Either side may be absent (``None``); the labels are
    the provenance spellings stamped into the generated doc comments — the
    manifest-relative strings, not resolved absolute paths, so the generated
    files stay byte-stable across machines."""
    name: str
    fortran: Optional[FortranKernelSpec]
    cpp: Optional[CppKernelSpec]
    fortran_label: str = ""
    cpp_label: str = ""
    pointize: bool = False


@dataclass(frozen=True)
class Manifest:
    path: Path                       # the manifest file (resolved)
    fortran: Optional[FortranConfig]
    cpp: Optional[CppConfig]
    kernels: tuple[KernelEntry, ...]
    lean_project: Optional[Path] = None

    def kernel(self, name: str) -> KernelEntry:
        for k in self.kernels:
            if k.name == name:
                return k
        raise ManifestError(
            f"{self.path.name}: no kernel named '{name}' "
            f"(have: {', '.join(k.name for k in self.kernels)})")


# --------------------------------------------------------------------------- #
# Loading
# --------------------------------------------------------------------------- #

_ENV_RE = re.compile(r"\$\{(\w+)\}")


def _expand(text: str, context: str) -> str:
    """Expand ``${VAR}`` from the environment; an unset variable refuses."""
    def sub(m: re.Match) -> str:
        val = os.environ.get(m.group(1))
        if val is None:
            raise ManifestError(
                f"{context}: ${{{m.group(1)}}} is not set in the environment")
        return val
    return _ENV_RE.sub(sub, text)


def _check_keys(table: dict, allowed: dict[str, type], required: set[str],
                context: str) -> None:
    """Refuse unknown keys and missing required keys; type-check values."""
    unknown = sorted(set(table) - set(allowed))
    if unknown:
        raise ManifestError(f"{context}: unknown key(s) {unknown} "
                            f"(allowed: {sorted(allowed)})")
    missing = sorted(required - set(table))
    if missing:
        raise ManifestError(f"{context}: missing required key(s) {missing}")
    for key, typ in allowed.items():
        if key in table and not isinstance(table[key], typ):
            raise ManifestError(f"{context}: '{key}' must be of type "
                                f"{typ.__name__}, got {type(table[key]).__name__}")


def _path(value: str, base: Path, context: str) -> Path:
    p = Path(_expand(value, context))
    if not p.is_absolute():
        p = base / p
    # Lexical cleanup only (no symlink resolution): keeps `a/b/../c` out of
    # CLI output and provenance-free config paths.
    return Path(os.path.normpath(p))


def resolve_manifest_path(explicit: Optional[str] = None) -> Path:
    """Resolution order: explicit (CLI flag) > $GROUNDLINE_KERNELS >
    ./kernels.toml. No other default exists."""
    if explicit:
        return Path(explicit)
    env = os.environ.get(MANIFEST_ENV)
    if env:
        return Path(env)
    cwd_manifest = Path(MANIFEST_FILENAME)
    if cwd_manifest.is_file():
        return cwd_manifest
    raise ManifestError(
        f"no kernel manifest: pass --kernels PATH, set ${MANIFEST_ENV}, or run "
        f"from a directory containing {MANIFEST_FILENAME}")


def load_manifest(path: Path | str) -> Manifest:
    path = Path(path)
    if not path.is_file():
        raise ManifestError(f"kernel manifest not found: {path}")
    with open(path, "rb") as f:
        try:
            data = tomllib.load(f)
        except tomllib.TOMLDecodeError as e:
            raise ManifestError(f"{path}: {e}") from None
    name = path.name
    base = path.resolve().parent
    _check_keys(data, {"fortran": dict, "cpp": dict, "lean": dict,
                       "kernel": list}, set(), name)

    fortran = _load_fortran(data.get("fortran"), base, name)
    cpp = _load_cpp(data.get("cpp"), base, name)

    lean_project = None
    if "lean" in data:
        _check_keys(data["lean"], {"project": str}, {"project"},
                    f"{name} [lean]")
        lean_project = _path(data["lean"]["project"], base, f"{name} [lean]")

    kernels = tuple(_load_kernel(tbl, i, fortran, cpp, name)
                    for i, tbl in enumerate(data.get("kernel", []), start=1))
    names = [k.name for k in kernels]
    dupes = sorted({n for n in names if names.count(n) > 1})
    if dupes:
        raise ManifestError(f"{name}: duplicate kernel name(s) {dupes}")
    return Manifest(path=path.resolve(), fortran=fortran, cpp=cpp,
                    kernels=kernels, lean_project=lean_project)


def _load_fortran(tbl: Optional[dict], base: Path, name: str) \
        -> Optional[FortranConfig]:
    if tbl is None:
        return None
    ctx = f"{name} [fortran]"
    _check_keys(tbl, {"dumps": str, "sources": str, "compiler": str,
                      "generated": str, "namespace": str, "blurb": str},
                {"generated", "namespace"}, ctx)
    dumps = tbl.get("dumps")
    return FortranConfig(generated=_path(tbl["generated"], base, ctx),
                         namespace=_expand(tbl["namespace"], ctx),
                         dumps=_path(dumps, base, ctx) if dumps else None,
                         sources=_path(tbl.get("sources", "."), base, ctx),
                         compiler=_expand(tbl.get("compiler", "flang"), ctx),
                         blurb=tbl.get("blurb", ""))


def _load_cpp(tbl: Optional[dict], base: Path, name: str) -> Optional[CppConfig]:
    if tbl is None:
        return None
    ctx = f"{name} [cpp]"
    _check_keys(tbl, {"sources": str, "include_dirs": list, "compiler": str,
                      "provenance_root": str, "generated": str,
                      "namespace": str, "blurb": str},
                {"generated", "namespace"}, ctx)
    include_dirs = tuple(str(_path(d, base, ctx))
                         for d in tbl.get("include_dirs", []))
    root = tbl.get("provenance_root")
    return CppConfig(generated=_path(tbl["generated"], base, ctx),
                     namespace=_expand(tbl["namespace"], ctx),
                     sources=_path(tbl.get("sources", "."), base, ctx),
                     include_dirs=include_dirs,
                     compiler=_expand(tbl.get("compiler", "clang++"), ctx),
                     provenance_root=_path(root, base, ctx) if root else None,
                     blurb=tbl.get("blurb", ""))


def _load_kernel(tbl: dict, ordinal: int, fortran: Optional[FortranConfig],
                 cpp: Optional[CppConfig], name: str) -> KernelEntry:
    ctx = f"{name} [[kernel]] #{ordinal}"
    _check_keys(tbl, {"name": str, "fortran": dict, "cpp": dict,
                      "pointize": bool}, {"name"}, ctx)
    kname = tbl["name"]
    ctx = f"{name} kernel '{kname}'"

    fspec, flabel = None, ""
    if "fortran" in tbl:
        if fortran is None:
            raise ManifestError(f"{ctx}: has a fortran side but the manifest "
                                f"has no [fortran] section")
        ftbl = tbl["fortran"]
        _check_keys(ftbl, {"dump": str, "source": str, "subroutine": str,
                           "nest": int, "def_name": str}, {"subroutine"},
                    f"{ctx} fortran")
        if ("dump" in ftbl) == ("source" in ftbl):
            raise ManifestError(
                f"{ctx}: give exactly one of fortran.dump (a pre-generated "
                f"flang dump, resolved under [fortran] dumps) or "
                f"fortran.source (a standalone Fortran file groundline runs "
                f"flang on, resolved under [fortran] sources)")
        dump = src = None
        if "dump" in ftbl:
            if fortran.dumps is None:
                raise ManifestError(
                    f"{ctx}: fortran.dump given, but the [fortran] section "
                    f"names no dumps directory")
            flabel = _expand(ftbl["dump"], f"{ctx} fortran")
            dump = _path(flabel, fortran.dumps, f"{ctx} fortran")
        else:
            flabel = _expand(ftbl["source"], f"{ctx} fortran")
            src = _path(flabel, fortran.sources, f"{ctx} fortran")
        nest = ftbl.get("nest")
        def_name = ftbl.get("def_name")
        if nest is None:
            if def_name is not None:
                raise ManifestError(f"{ctx}: def_name is only meaningful with "
                                    f"nest (inline-loop addressing)")
            if ftbl["subroutine"] != kname:
                raise ManifestError(
                    f"{ctx}: a whole-subroutine kernel is named after its "
                    f"subroutine — rename the entry to "
                    f"'{ftbl['subroutine']}' or address a loop nest")
        fspec = FortranKernelSpec(
            subroutine=ftbl["subroutine"], dump=dump, source=src,
            compiler=fortran.compiler, nest=nest,
            def_name=(def_name or kname) if nest is not None else None)

    cspec, clabel = None, ""
    if "cpp" in tbl:
        if cpp is None:
            raise ManifestError(f"{ctx}: has a cpp side but the manifest has "
                                f"no [cpp] section")
        ctbl = tbl["cpp"]
        _check_keys(ctbl, {"source": str, "function": str},
                    {"source", "function"}, f"{ctx} cpp")
        raw = _expand(ctbl["source"], f"{ctx} cpp")
        source = _path(raw, cpp.sources, f"{ctx} cpp")
        clabel = raw
        if cpp.provenance_root is not None:
            try:
                clabel = str(source.resolve().relative_to(
                    cpp.provenance_root.resolve()))
            except ValueError:
                clabel = str(source)
        cspec = CppKernelSpec(source=source, function=ctbl["function"],
                              include_dirs=cpp.include_dirs,
                              compiler=cpp.compiler)

    if fspec is None and cspec is None:
        raise ManifestError(f"{ctx}: needs a fortran and/or cpp side")
    return KernelEntry(name=kname, fortran=fspec, cpp=cspec,
                       fortran_label=flabel, cpp_label=clabel,
                       pointize=tbl.get("pointize", False))


# --------------------------------------------------------------------------- #
# Extraction + rendering (what generate/show/verify share)
# --------------------------------------------------------------------------- #

def fortran_provenance(entry: KernelEntry) -> str:
    spec = entry.fortran
    if spec.nest is None:
        return (f"`{spec.subroutine}` in `{entry.fortran_label}` "
                f"(flang with-sema dump)")
    return (f"loop nest {spec.nest} of `{spec.subroutine}` in "
            f"`{entry.fortran_label}` (flang with-sema dump)")


def cpp_provenance(entry: KernelEntry) -> str:
    return (f"`{entry.cpp.function}` in `{entry.cpp_label}` "
            f"(clang JSON AST)")


def extract_fortran_entry(entry: KernelEntry) -> Kernel:
    """Extract one entry's Fortran side. A kernel that is already per-point
    (scalar arguments, no loop) passes through as written. A loop nest is a
    different thing from a point function, so it refuses unless the entry
    carries ``pointize = true`` — the explicit license to reduce the loop to
    its per-point body via :func:`~groundline.kir.pointize`."""
    k = FlangKernelFrontend().extract(entry.fortran)
    if is_loop_nest(k):
        if not entry.pointize:
            raise UnsupportedConstruct(
                f"{k.name}: the Fortran kernel is a loop nest, which is not "
                f"the same thing as a point function — to compare its "
                f"per-point body, set `pointize = true` on this kernel's "
                f"manifest entry (see the manual's Pointize page)")
        return pointize(k)
    if entry.pointize:
        raise UnsupportedConstruct(
            f"{k.name}: `pointize = true`, but the kernel is not a loop "
            f"nest — drop the option; the kernel is compared as written")
    return k


def extract_cpp_entry(entry: KernelEntry) -> Kernel:
    """Extract one entry's C++ side (point functions extract as written; no
    pointize on this side — the clang frontend has no loop support yet)."""
    return ClangKernelFrontend().extract(entry.cpp)


def fortran_entries(m: Manifest) -> list[KernelEntry]:
    return [k for k in m.kernels if k.fortran is not None]


def cpp_entries(m: Manifest) -> list[KernelEntry]:
    return [k for k in m.kernels if k.cpp is not None]


def extract_all_fortran(m: Manifest) -> list[tuple[Kernel, str]]:
    return [(extract_fortran_entry(e), fortran_provenance(e))
            for e in fortran_entries(m)]


def extract_all_cpp(m: Manifest) -> list[tuple[Kernel, str]]:
    return [(extract_cpp_entry(e), cpp_provenance(e)) for e in cpp_entries(m)]


def _regen_line(m: Manifest) -> str:
    return (f"Regenerate with `groundline kernel generate` "
            f"(manifest: `{m.path.name}`).")


def fortran_blurb(m: Manifest) -> str:
    """The Fortran module header. When any kernel is source-mode (flang runs
    on demand), the pinned flang invocation is stamped as provenance —
    exactly as the C++ header stamps clang."""
    text = ("Emitted by `groundline.lean_printer` from "
            "flang with-sema\nparse-tree dumps "
            "(`groundline.frontend.flang_kernel`).\n" + _regen_line(m))
    if m.fortran.blurb:
        text += "\n" + m.fortran.blurb
    if any(e.fortran.source is not None for e in fortran_entries(m)):
        text += (f"\n\nExtraction provenance (pinned):\n"
                 f"  {flang_version(m.fortran.compiler)}\n"
                 f"  {' '.join(DUMP_FLAGS)}")
    return text


def cpp_blurb(m: Manifest) -> str:
    """The C++ module header, with the pinned clang invocation stamped as
    provenance (requires the manifest's clang on PATH)."""
    text = ("Emitted by `groundline.lean_printer` from "
            "clang JSON ASTs\n(`groundline.frontend.clang_kernel`).\n"
            + _regen_line(m))
    if m.cpp.blurb:
        text += "\n" + m.cpp.blurb
    text += (f"\n\nExtraction provenance (pinned):\n"
             f"  {clang_version(m.cpp.compiler)}\n"
             f"  -std=c++20 -fsyntax-only -Xclang -ast-dump=json "
             f"-Xclang -ast-dump-filter")
    for d in m.cpp.include_dirs:
        text += f"\n  -I{d}"
    return text


def render_fortran(m: Manifest,
                   extracted: Optional[list[tuple[Kernel, str]]] = None) -> str:
    """The full generated-Fortran-side Lean module text."""
    if m.fortran is None:
        raise ManifestError(f"{m.path.name}: no [fortran] section")
    return print_module(extracted if extracted is not None
                        else extract_all_fortran(m),
                        namespace=m.fortran.namespace, blurb=fortran_blurb(m))


def render_cpp(m: Manifest,
               extracted: Optional[list[tuple[Kernel, str]]] = None) -> str:
    """The full generated-C++-side Lean module text."""
    if m.cpp is None:
        raise ManifestError(f"{m.path.name}: no [cpp] section")
    return print_module(extracted if extracted is not None
                        else extract_all_cpp(m),
                        namespace=m.cpp.namespace, blurb=cpp_blurb(m))
