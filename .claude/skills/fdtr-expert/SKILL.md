---
name: fdtr-expert
description: Use when the user explicitly asks for expert analysis, diagnosis, or strategy recommendations on FDTR tasks with ambiguous goals. Not triggered by routine commands.
---

# FDTR Expert

High-level FDTR expert workflow for ambiguous requests. When the user gives a
clear instruction, use the existing skills directly. Use this skill when the
user asks for judgment, diagnosis, strategy comparison, or when the task is
underspecified.

---

## Activation

This skill activates only when the user explicitly requests expert analysis.
Typical triggers:

- "help me analyze this data" / "how should I approach this"
- "the fit results look wrong" / "I'm not sure what to fit"
- "design an experiment for X" / "what measurement setup should I use"
- "compare strategies" / "which approach is better"

**Do not** activate for routine commands that have an unambiguous execution path
through existing skills.

### Mode classification

On activation, classify the task into one of two modes and identify the
analysis target.

```text
Mode:
  data-backed  — user has FDTR data to process or fit
  design-only  — user is planning an experiment before data are available

Must clarify (state assumptions explicitly; do not hide them):
  - user goal
  - material system and layer structure
  - target parameters
  - what is known vs. unknown
```

---

## Decision Flow

The expert workflow is iterative, not linear. Both modes share a common core
(Parameter Roles → Scheme Design → Execution → Result Review) but differ in
scope and constraints:

- **Data-backed** is constrained by available data and data quality. It uses
  sensitivity/uncertainty to validate the fitting scheme before committing, then
  can iterate based on actual fit results.
- **Design-only** explores the parameter space more freely — no actual fitting,
  but sensitivity and uncertainty calculations are used to evaluate whether a
  candidate measurement setup can reliably extract the target parameters.

### Entry paths

```text
DATA-BACKED                                 DESIGN-ONLY

  Activation                                  Activation
      │                                           │
      ▼                                           │
  Data Assessment                                 │
  (quality OK?)                                   │
   no ──► diagnose / exclude                      │
          re-assess or stop                       │
   yes ──► Parameter Roles                        │
                 │                                │
                 └──────────┐     ┌───────────────┘
                            ▼     ▼
                        Parameter Roles
```

### Shared loop (both modes)

```text
  Parameter Roles ◄──────────────────────┐
        │                                │
        ▼                                │
  Scheme Design  ──► generate configs    │
        │           via fdtr-config      │
        │           (+ sensitivity /     │
        │            uncertainty configs │
        │            if needed)          │
        ▼                                │
  Execution  ──► delegate to             │
        │         existing skills        │
        ▼                                │
  Result Review                          │
  (acceptable?)                          │
   │         │                           │
  no        yes                          │
   │         │                           │
   ▼         ▼                           │
 backtrack  Output                       │
 (see below)recommend                    │
   │                                     │
   └─────────────────────────────────────┘
```

### Backtracking

When a result is not acceptable, backtrack to the appropriate point:

```text
Issue detected                      Backtrack to
──────────────                      ────────────
Data quality problems               Data Assessment
Wrong model or parameter roles      Parameter Roles
Poor parameter separability         Scheme Design
Unstable or unreliable results      Scheme Design (revise strategy)
Sensitivity/uncertainty not viable  Scheme Design (try alternative setup)
Multiple iterations no improvement  Stop — explain limitations to user
```

Changes that require explicit user confirmation before proceeding:

- changing layer structure or adding/removing a physical layer
- changing material identity
- large deviations from measured thickness or spot size
- discarding a significant portion of data without clear evidence
- reporting a low-sensitivity nuisance parameter as a main result

---

## Data Assessment

**Input:** scan-data output + user-supplied information
**Output:** usable data range (groups, xdata range) + exclusions + reasoning
**Applies to:** data-backed mode only

### What to evaluate

scan-data provides file/group/metadata summaries. Beyond that, assess:

1. **Repeatability** — are nominally repeated measurements at comparable
   coordinates and mutually consistent?
2. **Phase integrity** — any jumps, discontinuities, or unwrap artifacts?
3. **Signal quality** — isolated spikes, abnormal amplitude, excessive noise?
4. **Coverage** — is the xdata range sufficient for the intended target
   parameters?
5. **Regime behavior** — do low-frequency or high-frequency regions behave
   abnormally?

### Output

1. Extract usable data (selected groups, trimmed xdata range) into a new
   subfolder, then run `scan-data` on it to generate an updated paths spec for
   downstream tools.
2. Record assessment conclusions (which groups were kept, excluded, or flagged,
   and why) in context. These conclusions should be included in the final
   summary at the end of the expert workflow.

### Expert experience

- Do not treat `scan-data` grouping as final. It is only a first-pass
  organization.
- A repeated filename or group name does not guarantee a valid repeat. The same
  name may include multiple independent measurements, interrupted runs, or
  re-measurements after a failed scan.
- Do not average data from clearly different positions, frequency ranges,
  measurement conditions, or measurement batches.
- If coordinate differences are small and xdata ranges are comparable,
  interpolation-based averaging is acceptable. Interpolation must not be used to
  merge data from different conditions or failed/restarted runs.
- Do not average clearly inconsistent repeats. If sample inhomogeneity causes
  different positions to show different phase values, flag this explicitly;
  averaged fitting can be tried, but separate-group fitting may be needed if
  the averaged fit is poor.
- Pre-fit data assessment should focus on smoothness, repeatability, and phase
  integrity. Deeper model consistency is usually judged after fitting in Result
  Review.
- Isolated abnormal points may be removed. Segment-level curve abnormalities
  usually make the group suspicious or unusable.
- Start with the most reliable-looking data group for trial fitting. If the
  result is poor or sample inhomogeneity is suspected, fit groups separately
  and compare.
- Offset data often have less ideal signal quality than frequency sweeps and
  can be affected by spot quality and alignment.
- Offset scans with asymmetry, abnormal trends, or local bumps should be
  treated as suspicious. They may be tested diagnostically (e.g., fitting one
  side only) but should not be trusted as the main offsetfit input without
  caution.
- Diagnostic plots and statistics are primarily for AI/expert judgment and do
  not need to be shown to the user unless requested.

---

## Parameter Roles

**Input:** material system + user goal + data assessment output (if applicable)
**Output:** role label and allowed adjustment range for each parameter
**Applies to:** both modes

### Role labels

```text
target              — the main result the user cares about
nuisance-fitted     — must be fitted but is not the core result
candidate-fitted    — possible to fit if sensitivity/uncertainty supports it
calibrated-fixed    — measured or calibrated separately
literature-fixed    — taken from literature values
ignored             — not treated as independent (e.g., thin adhesion layer)
```

For design-only mode, also classify:

```text
design variable     — parameter whose value is being chosen (e.g., transducer
                      thickness, spot size, frequency range)
calibration-needed  — parameter that requires independent measurement before
                      the target can be reliably extracted
```

### Allowed adjustment boundaries

Define before fitting what the AI is allowed to vary and by how much.
Adjustments within these ranges are diagnostic; anything beyond requires user
confirmation.

### Expert experience

- Parameter roles must be assigned from the user goal first, then refined by
  sensitivity/uncertainty analysis.
- Do not assume the target parameter from the material system alone. If the user
  says "thermal conductivity," clarify whether they mean in-plane, cross-plane,
  film, substrate, or interface conductance.
- Interface conductance is often unknown. If it is not the main research target
  but still affects the target parameter, classify it as `nuisance-fitted`.
- Do not simultaneously fit multiple interface conductances by default. Use
  sensitivity/uncertainty to decide which interface is identifiable.
- In multilayer or thin-film stacks, interface conductances and cross-plane
  thermal conductivity of thin layers may behave like serial thermal resistances
  and can be strongly correlated.
- If a lower or remote interface has low sensitivity, consider fixing it and
  fitting only the dominant interface parameter.
- Transducer thermal conductivity and thickness are usually `calibrated-fixed`,
  not freely fitted, unless their uncertainty is central to the analysis.
- Spot size is usually `calibrated-fixed`; treat it as `candidate-fitted` only
  when spotfit or offset data provide sufficient sensitivity, or when spot
  calibration is unreliable.
- Heat capacity is usually `literature-fixed` unless the user goal or
  uncertainty analysis justifies treating it otherwise.
- Non-target layer thickness and thermal properties should ideally be calibrated
  or fixed. If they are uncertain, treat them as `candidate-fitted` only if
  sensitivity/uncertainty supports fitting.
- A `candidate-fitted` parameter should enter the fit only if sensitivity is
  sufficient and uncertainty remains acceptable.
- Unknown does not automatically mean fitted. If a parameter can be calibrated,
  calibration is preferred over fitting, especially when it is not the main
  target.
- When a non-target parameter strongly affects the target result but cannot be
  calibrated, use sensitivity/uncertainty to decide whether it can be fitted or
  whether additional data dimensions are needed.
- The number of simultaneously fitted parameters should remain small unless
  sensitivity/uncertainty supports a larger combination.
- In design-only mode, uncertain transducer properties, spot size, thickness, or
  interface conductance can be scanned as parameter ranges to test their impact.
  Heat capacity usually remains literature-fixed.
- Interface conductance can be scanned over an experience-based preliminary range
  such as `1e7–1e8 W/m²K`, but this range is not universal and must not be
  treated as a hard constraint.
---

## Scheme Design

**Input:** parameter roles + data availability + data assessment output
**Output:** candidate scheme + generated config files
**Applies to:** both modes

### Design candidate schemes

For each candidate scheme, specify:

- strategy (freqfit / offsetfit / spotfit / iterfit)
- which parameters are fitted, with initial bounds
- xdata range
- why this scheme is appropriate
- known risks

### Generate configs

After designing candidate schemes, generate the corresponding config files:

- **Base config** — use `fdtr-config` to generate the analysis config.
- **Sensitivity config** — generate if the scheme needs sensitivity validation
  before execution.
- **Uncertainty config** — generate if the scheme needs uncertainty validation
  before execution.

When calling `fdtr-config` within this expert workflow, skip the default
user-confirmation step after config generation. 

Do not execute calculations in this section. Config generation only.

### When to use each strategy

**freqfit** — standard choice for frequency-sweep data; suitable for
cross-plane thermal transport and interface resistance.

**offsetfit** — use when lateral heat spreading is important, especially for
in-plane thermal conductivity or when spatial information helps decouple
parameters.

**spotfit** — use when spot size is uncertain and sensitivity supports spot
extraction; do not use as an unconstrained way to force a good residual.

**iterfit** — use when one data type cannot reliably constrain all target
parameters and different measurement dimensions have complementary sensitivity.
Each step must have a clear target supported by sensitivity/uncertainty. Do not
use iterfit merely because a built-in default pipeline is available.

For **design-only** mode: design sensitivity sweeps over candidate setups and
prepare configs that explore which configuration best identifies the target
parameters.

### Expert experience

- Two-parameter fitting is usually more reliable than three-parameter fitting.
- For Au/fused silica calibration: `S_0` is the target, `TBC_1` is usually a
  nuisance-fitted parameter. A common scheme is freqfit with both as fitted
  parameters.
- `S_0` (Au thermal conductivity) should be calibrated separately before being
  fixed in more complex systems.
- For Au/graphite semi-infinite substrate, iterfit can separate parameters:
  high-frequency offset amplitude → `spot_size`; offset phase → `Sr_N`
  (graphite in-plane); frequency sweep → `Sz_N` (graphite cross-plane) +
  `TBC_N` (Au/graphite interface). Layer index N depends on the actual stack
  configuration.
- Do not trust offsetfit only because it converges; check raw signal quality and
  consistency with frequency-sweep results.
- Iterfit should repeat the step sequence until parameters are basically stable;
  convergence is judged by parameter stability, not a strict numerical
  threshold.
- Very low frequencies are often weakly sensitive to many parameters.
- <!-- TODO: more system-specific scheme recommendations — to be populated via
  interview -->

---

## Execution

**Input:** config files generated in Scheme Design
**Output:** calculation results (sensitivity, uncertainty, fit results —
depending on mode and scheme)
**Applies to:** both modes

Do not modify configs at this stage. If results indicate a problem, backtrack
to Scheme Design.

### Scheme validation (both modes)

When fitting modes are not clear, run sensitivity and/or uncertainty to validate whether the
proposed scheme can reliably extract the target parameters. This step is
conceptually the same for both modes — data-backed just operates with more
constraints (known data range, fixed parameters) and typically needs fewer
iterations.

```text
sensitivity / uncertainty  →  Result Review (pre-fit)
                                   │
                              not viable ──► backtrack to Scheme Design
                              viable     ──► proceed
```

### Fitting (data-backed only)

After scheme validation passes:

```text
fitting (fdtr-config → fdtr-iterpipeline)
        │
        ▼
uncertainty on fit results (fdtr-uncertainty, optional)
        │
        ▼
Result Review (post-fit)
```

Do not run fitting in design-only mode.

### Expert experience

- <!-- TODO: execution-order preferences (sensitivity before fit? uncertainty
  before iterfit?) — to be populated via interview -->
- <!-- TODO: common pitfalls during execution — to be populated via interview
  -->

---

## Result Review

**Input:** calculation results from Execution (fit results, sensitivity
outputs, uncertainty outputs, diagnostic plots)
**Output:** accept / accept with caveats / backtrack (specify target) / stop
**Applies to:** both modes

### Data-backed review checklist

1. **Residual quality** — is the fit curve consistent with data shape?
2. **Physical plausibility** — are fitted values within expected ranges?
3. **Sensitivity support** — do fitted parameters have adequate sensitivity
   over the used xdata range?
4. **Uncertainty magnitude** — are uncertainties acceptable for the intended
   use?
5. **Parameter correlation** — are fitted parameters sufficiently decoupled
   (check covariance)?
6. **Consistency** — are results consistent with literature, calibration, or
   other data types?
7. **Boundary issues** — did any parameter hit its bound? This often signals a
   problem.

### Design-only review checklist

1. **Parameter identifiability** — does sensitivity show that the target
   parameters are distinguishable in the proposed measurement range?
2. **Uncertainty viability** — can the target parameters be extracted with
   acceptable uncertainty under the assumed known-parameter errors?
3. **Parameter separability** — are target parameters sufficiently decoupled
   from nuisance parameters?
4. **Setup robustness** — is the recommended setup robust to reasonable
   variations in design variables?

### Decision

```text
accept                → output recommendation
accept with caveats   → output with noted limitations
backtrack             → return to the section indicated in backtracking rules
stop                  → conditions insufficient; explain to user
```

### Expert experience

- If a parameter hits its bound, the fit is constrained by the bound, not by
  the data — investigate before trusting the result.
- If offset and frequency-sweep data have incompatible individual optima, a
  compromise parameter set may be more appropriate than choosing one optimum.
- If fitting requires unreasonable thickness or spot-size adjustments, suspect
  data, calibration, or model issues.
- Uncertainty is not only for error bars; it also identifies which known
  parameters need better calibration.
- If low-frequency data fit poorly but high-frequency data are good, fitting
  only the high-frequency range is acceptable with explanation.
- <!-- TODO: system-specific result benchmarks — to be populated via interview
  -->

---

## General Rules

Hard constraints that apply across all sections.

1. **Do not skip to fitting when the goal is ambiguous.** Clarify the system,
   parameter roles, and boundaries first.
2. **Sensitivity and uncertainty are decision tools, not just output plots.**
   Use them to decide whether a scheme is viable before committing to it.
3. **Do not choose a strategy only because it gives the smallest residual.**
   Evaluate residual quality, physical plausibility, sensitivity, uncertainty,
   and consistency.
4. **Do not fit extra parameters just because the optimizer converges.**
5. **Do not report low-sensitivity nuisance parameters as strong physical
   conclusions.**
6. **Do not invent literature values, benchmark ranges, or dominant uncertainty
   sources.** If unknown, say so.
7. **Do not silently change layer structure, material identity, or measured
   parameters.** These require explicit reasoning and usually user confirmation.
8. **Do not average data groups that are visibly inconsistent or measured at
   significantly different positions.**
9. **Mark all assumptions explicitly.** If information is missing, state what
   was assumed and why.
10. **Delegate execution to existing skills.** This skill decides *what* and
    *why*; existing skills handle *how*.
