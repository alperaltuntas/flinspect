# The relational track

!!! info "This page is a stub — deliberately"

    The relational track will be documented here **after its CLI lands**
    (the `groundline check` / `report` command groups are designed but not
    built). Until then, this page only says what the track is, so readers
    of this manual know what the other half of the tool does. The engineering
    detail lives in the repository's
    [`docs/`](https://github.com/alperaltuntas/groundline/tree/main/docs).

groundline's original, top-down face models a whole Fortran codebase as
**structural facts**: modules, subprograms, interfaces, and derived types as
scope-qualified entities; USE dependencies, containment, interface
membership, and call relationships as relations over them. It consumes the
same flang with-sema dumps as the kernel track (458 files of MOM6 + FMS2 in the
production corpus) and is browsable today through a Jupyter explorer and
NetworkX graphs.

Its distinguishing design decision is that **resolution confidence is a
first-class fact**. Every call edge carries the stratum the compiler's
semantic analysis actually supports:

- `resolved` — sema names the callee;
- `assumed` — dynamic dispatch classified through the declared type's
  binding table (an override may win at runtime);
- `unresolved` — the target is not in the parsed universe (externals,
  unparsed libraries), kept as a first-class ghost entity rather than
  dropped.

*May* and *must* views of the call graph derive from the strata, so analyses
can be sound in whichever direction they need — never silently optimistic.

**Planned, not built:** a relational query layer over these facts (closure,
difference, reachability) and a CI gate that fails on forbidden structural
edges — which is also what will generate the kernel track's proof obligations
("provable in isolation" is a relational query) and complete the combined
gate sketched in [Limits & roadmap](limits.md#the-other-half-of-the-vision).
