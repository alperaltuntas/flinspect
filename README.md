# What is flinspect?

flinspect is a structural introspection and reasoning tool for large Fortran HPC systems. It is built on top of LLVM/flang parse trees to explore, visualize, and understand the structure and dependencies within complex Fortran projects.

At a high level, flinspect:

 - Consumes compiler-produced parse trees (from flang)
 - Reconstructs semantic structure of large Fortran codebases
 - Builds a graph-based internal model of:
   - modules
   - subprograms
   - interfaces
   - derived types
   - USE dependencies
   - call relationships

 - Exposes that model interactively via Jupyter (Explorer + widgets)
 - Scales to multi-project / multi-tree analysis (ParseForest)
 
flinspect is :

 - a structural reasoning substrate
 - a code comprehension accelerator
 - a foundation for correctness and modernization tooling

## Working with flinspect:

flinspect is currently a prototype used primarily for the TURBO project. See the notebooks
directory for examples. To be able to run those notebooks, first install the conda environment:

```bash
conda env create -f environment.yml
```

After installing the flinspect conda environment, activate it and also install
pygraphviz:

```bash
conda activate flinspect
conda install -c conda-forge pygraphviz
```

You are now ready to explore the Jupyter notebooks under `notebooks/`.

**Note**, however, that the notebooks will require flang parse tree files for MOM6
and its libraries. These are available on NCAR's glade file system and paths are
specified in all the notebooks.

If you don't have access to NCAR's glade file system, you will need to create
flang parse trees on your local machine.

## What does flinspect do?
Core Functionality:
 1. Parse Tree Analysis: Parses flang-generated parse tree files to extract structural information from Fortran code including:
    - Modules, programs, and subprograms
    - Subroutines and functions
    - Interfaces and derived types
    - Other lower level constructs
    - Dependencies in the form of imports, calls, and other relationships.
 2. Dependency Graph Generation: Creates visual representations of:
    - Module dependency graphs
    - Call graphs showing subroutine/function relationships
    - Interactive network visualizations using NetworkX and ipycytoscape
 3. Interactive Code Explorer: Provides a Jupyter widget-based interface (Explorer class) that allows users to:
    - Browse and filter code elements by category (Subroutine, Function, Interface, Derived Type)
    - Search and inspect specific program units
    - Visualize relationships between code components

4. Multi-Project Analysis: Through the ParseForest class, it can analyze multiple parse trees simultaneously, enabling comprehensive analysis of large codebases with multiple components.

## Key Classes and Components:
 - ParseTree: Reads and parses individual flang parse tree files
 - ParseForest: Manages collections of parse trees for multi-file analysis
 - Explorer: Interactive Jupyter widget for code exploration
 - Node classes: Represent different Fortran constructs (Module, Subroutine, Function, etc.)
 - NodeRegistry: Manages object interning and relationships

## How does flinspect work?
Technical Architecture:

 1. Input Processing: Takes flang-generated parse tree files as input (typically stored in build directories like /flang_ptree/)
 
 2. Parsing Pipeline:
    - It iterates through parse tree files line by line
    - Identifies and extracts Fortran language constructs using pattern matching
    - Builds internal representations of code structure
 
 3. Relationship Analysis:
    - Tracks module USE statements and dependencies
    - Identifies subroutine and function call relationships
    - Resolves call targets across modules
 
 4. Visualization:
    - Uses NetworkX for graph data structures
    - Leverages ipycytoscape for interactive network visualization in Jupyter
    - Provides widget-based interfaces for user interaction

## Dependencies:
 - Python 3.14 (specific version requirement)
 - NetworkX for graph analysis
 - Jupyter ecosystem (jupyterlab, ipywidgets, ipycytoscape) for interactive interfaces
 - z3-solver for constraint solving (in the works)

## Why was flinspect created?

Large Fortran HPC codebases (like climate models, computational fluid dynamics codes, etc.) often consist of:

 - Thousands of source files
 - Complex module hierarchies
 - Intricate dependency relationships
 - Legacy code with unclear structure, subpar coding practices, and insufficient documentation

Solution Goals:
1. Code Understanding: Help developers and researchers understand the structure of complex Fortran codebases
2. Dependency Analysis: Identify and visualize how different parts of the code interact
3. Refactoring Support: Provide insights needed for safe code refactoring and modernization
4. Documentation Aid: Generate visual documentation of code architecture
5. Development Efficiency: Speed up navigation and comprehension of large codebases

Target Use Cases:
1. HPC Software Development: Understanding and maintaining large scientific computing codes
2. Code Review and Analysis: Systematic analysis of Fortran project structure
3. Legacy Code Modernization: Planning refactoring efforts for older Fortran codebases

## Future directions

The long term vision for flinspect is to turn flinspect from a structural explorer into a relational reasoning system over Fortran programs, very much in the spirit of the Alloy model checker, but grounded in real compiler-derived facts rather than abstract models.

This will include a declarative query and constraint language (or tooling) over the program graph
based on sets, relations, and quantification.

Where the universe is:

 - Modules
 - Subroutines
 - Functions
 - Interfaces
 - Derived types
 - Calls
 - USE dependencies
 - Containment relationships

And the relations are things like:

 - calls
 - called_by
 - uses
 - defined_in
 - contains
 - exports
 - imports

With relational operators:

 - `.`	relational join
 - `&`	intersection
 - `+`	union
 - `-`	difference
 - `*`	transitive closure
 - `~`	inverse relation

Example:
   ```
   s.calls            -- callees of s
   ~calls.s           -- callers of s
   s.(calls*)         -- transitive callees

   -- quantification:
   all s: Subroutine |
       some f: Function |
           f in ~calls.s
   ```

### Reasoning:

A Z3-based constraint solver will be integrated to support these queries and reasoning tasks over the program graph:

 - translate quantified relational constraints
 - ask:
   - Is this property violated?
   - Show me a counterexample subroutine/

This will turn flinspect into:
 - A bounded program logic checker for Fortran architecture


All of this will enable:

 - architectural invariants
 - modernization safety checks 
 - refactoring preconditions
 - GPU kernel isolation reasoning
 - CI-enforced structural properties

### An Example Use Case: Code Modernization for GPU offlading and Performance Portability

### A. Identifying GPU-Candidate Kernels (Leaf & Near-Leaf Routines)
  
     **Question:**
     Which routines are structurally eligible to become AMReX GPU kernels?

     **Property:**
     A GPU kernel candidate must:
     -  Not call MPI
     -  Not perform I/O
     -  Not allocate memory
     -  Only call other GPU-safe routines

     **Specification sketch:**

      ```
      gpu_kernel_candidate(s) iff
         no f in s.(calls*) |
            f in HostOnly
      ```
### B. Enforcing Host / Device Separation

   **Question:**
   Have we accidentally introduced host-only calls into device-callable code?
   
   This happens all the time during incremental porting.

   **Property:**
   ```
   no s: DeviceCallable |
       some f in s.(calls*) |
           f in HostOnly
   ```
   
   **Outcome**:
    - Counterexample = exact call chain
    - CI-enforceable structural invariant

### C. Ensuring Kernel Call Graph Closure
   
   **Question:**
   Does every GPU kernel only call routines that have been ported?
   
   **Property:**
   ```
   all s: GPU_Kernel |
       s.(calls*) in GPU_Port
   ```
   This is transitive closure reasoning, which most tools cannot express.



### D. Detecting Hidden Global State Access

   **Question:**
   Which routines access module-level state that breaks GPU execution?

   **Relations**
   - accesses_global : Subroutine -> ModuleVariable
   - defined_in : Variable -> Module

   **Property**
   ```
   no s: GPU_Kernel |
       some v in s.accesses_global |
           v notin DeviceAccessible
   ```
   
   This lets us:

    - identify refactoring targets
    - justify moving state into AMReX data structures

 ### E. Mapping Physics vs Infrastructure Boundaries
   
   **Question:**
   Are physics kernels accidentally depending on infrastructure layers?
   
   This is architectural drift and kills performance portability.
   
   **Property**
   ```
   no s: Physics |
       some f in s.(calls*) |
           f in Infrastructure
   ```
   
### F. Ensuring AMReX-Compatibility of Call Signatures

   **Question:**
   Do GPU-callable routines obey AMReX calling conventions?

   **Relations**
   - has_argument : Subroutine -> Argument
   - argument_type : Argument -> Type

   **Property**
   ```
   all s: GPU_Kernel |
       all a in s.arguments |
           a.type in {Real, Integer, AMReXArray}
   ```
   
   Now signature correctness becomes checkable, not aspirational.
   
### G. Detecting Accidental Synchronization Points

   **Question:**
   Where do we accidentally force host/device sync?

   **Property**
   ```
   some s: GPU_Kernel |
       some f in s.(calls*) |
           f in SynchronizingCall
   ```

   **Result:**

    - Exact routine + call chain
    - Immediate performance red flag

### H. Supporting Incremental Porting Strategy
   
   **Question:**
   What is the minimal cut to port next?
   
   This is a graph problem, not a coding problem.
   
   **Query**
   ```
   frontier = calls*(GPU_Port) - GPU_Port
   ```
   
   This gives us:

    - Next candidates to port
    - Objective progress metrics

## More ideas:

 - CI-Enforceable Structural Contracts: Once we have this logic layer, we can write architecture tests:
      ```
      assert no_cycles_in module_dependency_graph
      assert all GPU_Kernel ⊆ GPU_Port
      assert no DeviceCallable calls HostOnly
      ```
   
   This will allow us to say:
    - "This refactor is structurally safe."
    - That’s a new capability in Earth system modeling software engineering.

   "We use a relational program logic to enforce architectural invariants during GPU modernization of MOM6."

## More on Supporting Incremental Porting Strategy 

1. Reframing the Problem

    Incremental GPU porting is not “convert routines one by one."
  
    It is:
  
    A sequence of graph cuts that monotonically expand a GPU-safe subgraph
    while preserving global correctness and performance invariants.
  
    Once we see it that way, everything snaps into place.

2. The Program as a Graph with a Moving Frontier

   Model the codebase as a directed graph:
   
    - Nodes = subroutines / functions
    - Edges = calls
    - Labels = properties (GPU-safe, host-only, MPI, etc.)
   
   At any point in time, we have:
   
   - GPU_Port – routines already ported
   - HostOnly – routines that cannot be ported
   - Unknown – everything else

   The frontier is:
   ``` 
   frontier = calls*(GPU_Port) - GPU_Port
   ```
   
   This is the minimal interface between:
   - what is already device-safe
   - and what still blocks expansion

   This frontier is not heuristic — it is structurally minimal.

3. What “Minimal Cut" Really Means Here

   Important clarification:
   
   We are not cutting the graph arbitrarily.

   We are looking for the smallest set of routines whose transformation unlocks further GPU expansion.

   Formally:
   
     A minimal set of nodes whose inclusion into GPU_Port strictly reduces the size of the frontier.
   
   That’s a partial order over refactorings.

4. Classifying Frontier Nodes (This Is the Real Power)

   Once we compute the frontier, flinspect + logic can classify each node:

   A. Pure blockers (easy wins)

    - No MPI
    - No I/O
    - No global state
    - Just not yet ported

   ```
   easy = frontier - HostOnly - GlobalAccess - SyncPoints
   ```

   These are low-risk, high-reward.

   B. Structural blockers (refactor required)

    - Access module state
    - Have non-AMReX-friendly arguments
    - Mix physics and infrastructure
   ```
   structural = frontier & GlobalAccess
   ```

   These tell you where to refactor, not port blindly.

   C. Hard blockers (design decisions)

    - MPI calls
    - I/O
    - Synchronization primitives
   ```
   hard = frontier & HostOnly
   ```
   These identify where architectural boundaries must be drawn.

5. Turning This into a Stepwise Refactoring Strategy

    - Step 0: Baseline

      - Compute calls*
      - Tag obvious HostOnly routines
      - Establish invariants

    - Step 1: Seed the GPU Subgraph

      Pick a small, obvious kernel set:
      ```
      GPU_Port = {tracer_update, advect_velocity}
      ```
      Verify:
      ```
      assert no s in GPU_Port calls HostOnly
      ```
    - Step 2: Compute Frontier
      ```
      frontier = calls*(GPU_Port) - GPU_Port
      ```
      This answers:
   
         "What must be addressed next?"

    - Step 3: Rank Frontier by Portability Cost

      Define relations:
      ```
      violates(s) -> {MPI, IO, Global, Sync}
      ```
      Then:
      ```
      cost(s) = |violates(s)|
      ```

      Now we have a quantitative modernization roadmap.

    - Step 4: Transform One Equivalence Class at a Time

      Pick a class:

       - all routines that only violate GlobalAccess

      Refactor them together:

       - move state into AMReX data

       - change call signatures

      This avoids whack-a-mole refactoring.

    - Step 5: Expand GPU_Port and Recompute

      This is the loop:
      ```
      analyze -> refactor -> verify -> expand -> repeat
      ```

      Each iteration is:
       - smaller
       - safer
       - provably monotonic

    - 6. Comparison to Traditional Porting

         Traditional approach:

          - Pick "important" routines
          - Port them
          - Discover blockers late
          - Backtrack

         Our approach:
          - Makes blockers explicit
          - Orders work by structural necessity
          - Prevents wasted effort
   
   7. Making This CI-Enforceable:

      Once this exists, we can assert:
      ```
      assert frontier_size decreases each release
      ```

      or
      ```
      assert no new HostOnly edges cross into GPU_Port
      ```

      **That’s a regression test for modernization progress.**

   8. How This Generalizes Beyond GPUs

      This exact strategy applies to:

       - OpenMP -> GPU
       - Fortran -> C++ kernels
       - Monolithic -> layered refactors
       - Introducing autodiff
       - Enforcing purity / reentrancy

      It’s a general transformation calculus for scientific software.

   In Summary:

      We treat GPU modernization as a monotonic expansion of a verified subgraph, guided by relational analysis.
