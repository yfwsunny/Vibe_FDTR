---
name: fdtr-expert
description: Use only when the user explicitly requests FDTR expert mode, expert analysis, expert diagnosis, or expert strategy recommendations. Not triggered by routine commands.
---

# FDTR Expert

High-level FDTR expert workflow for explicitly requested expert mode. This skill
decides what should be analyzed, why, in what order, with what boundaries, and
how to judge whether the result is reliable.

It does not replace existing FDTR execution skills. When the user gives a clear
routine instruction without asking for expert mode, use the standard routed
skills directly.

---

## Activation

### Rules

- Activate only when the user explicitly requests FDTR expert mode, expert
  analysis, expert diagnosis, or expert strategy recommendations.
- Do not activate for routine commands that have a clear execution path through
  `scan-data`, `fdtr-config`, `fdtr-sensitivity`, `fdtr-uncertainty`, or
  `fdtr-iterpipeline`.
- Once activated, classify the task as `data-backed` or `design-only` and state
  assumptions explicitly.

Typical explicit triggers:

- "work in expert mode"
- "please use expert analysis"
- "use expert mode to compare strategies"
- "give an expert recommendation for this measurement setup"

Must clarify or state assumptions for:

```text
User goal
Material system and layer structure
Target parameters
What is known vs. unknown
Assumed parameters such as spot_size, TBC, d_0, and transducer conductivity if not provided
Allowed adjustments
```

---

## Decision Flow

Classify the request into one mode:

| Mode          | Use when                                                          | Main constraint                                                              | Typical output                                                   |
| ------------- | ----------------------------------------------------------------- | ---------------------------------------------------------------------------- | ---------------------------------------------------------------- |
| `data-backed` | FDTR data already exist and may be processed, analyzed, or fitted | available data, data quality, measured xdata range, known sample information | selected data, validated fitting scheme, fit/review result       |
| `design-only` | the user is planning measurements before data exist               | assumed stack, parameter ranges, measurement ranges, calibration assumptions | measurement/fitting plan supported by sensitivity or uncertainty |

Workflow loops:

```text
data-backed:
Data Assessment -> Parameter Roles -> Scheme Design -> Execution -> Result Review
        ^                                  ^                         |
        |----------------------------------|-------------------------|

design-only:
Parameter Roles -> Scheme Design -> Execution -> Result Review
       ^                  ^                         |
       |------------------|-------------------------|
```

Once expert mode is explicitly activated, if the goal is underspecified,
identify which unknown parameters the available information may constrain
instead of defaulting to the simplest fitting method.

For data-backed tasks with unclear target parameters or fitted-parameter
combinations, use sensitivity/uncertainty analysis like a design task before
committing to a fitting strategy.

### Backtracking

When a result is not acceptable, return to the appropriate stage:

| Issue detected                                                              | Backtrack to                    |
| --------------------------------------------------------------------------- | ------------------------------- |
| Data quality problems                                                       | Data Assessment                 |
| Wrong model or parameter roles                                              | Parameter Roles                 |
| Poor parameter separability                                                 | Scheme Design                   |
| Unstable or unreliable results                                              | Scheme Design                   |
| Sensitivity or uncertainty not viable                                       | Scheme Design                   |
| Multiple iterations of the method or parameters choices show no improvement | Stop and explain the limitation |

Changes that require explicit user confirmation before proceeding:

- changing layer structure or adding/removing a physical layer
- changing material identity
- large deviations from measured thickness or spot size
- discarding a significant portion of data without clear evidence
- reporting a low-sensitivity nuisance parameter as a main result

---

## General Rules

Global constraints that apply across all expert-mode stages:

1. **Do not skip to fitting when the goal is ambiguous.** Clarify the system,
   parameter roles, and allowed adjustment boundaries first.
2. **Mark all assumptions explicitly.** If any target parameter, nuisance
   parameter, interface, constraint set, or fitting/fixing choice is not fully
   specified, state what is being analyzed and assumed.
3. **Sensitivity and uncertainty are decision tools.** Use them to decide
   whether a scheme is viable.
4. **Design-only recommendations must be calculation-backed for the actual
   stack and assumed values.** Do not rely on experience alone or present lab
   experience as a validated conclusion.
5. **Do not choose a strategy only because it gives the smallest residual.**
   Evaluate residual quality, physical plausibility, sensitivity, uncertainty, and
   parameter correlation.
6. **Do not fit extra parameters just because the optimizer converges.** Usually no more than 2 fitting parameters for a single data line. More
   fitted parameters require sensitivity/uncertainty support and an explicit
   reliability warning.
7. **Do not report low-sensitivity nuisance-fitted parameters as strong physical
   conclusions.**
8. **Do not silently change layer structure, material identity, or measured
   parameters.**
9. **Do not invent literature values, benchmark ranges, or dominant uncertainty
   sources.** If unknown, say so or retrieve/verify the source when needed.
10. **Judge sensitivity by absolute magnitude and curve-shape separability, not
    sign.** A sign change or crossing zero point is not an identifiability argument.
11. **Delegate execution to existing skills.** This skill decides what and why;
    routed skills handle how.
12. **Explore large option spaces systematically.** For many candidate parameter
    combinations, measurement variants, or design ranges, use systematic
    exploration rather than a few hand-picked trials. Use delegated sub-agents or
    explicit sweeps when available, and keep each variant's inputs, outputs, and
    decision status traceable.
13. **Do not finish an expert process until supporting artifacts are traceable.** Intermediate files and folders must be moved into a single folder, key
    outputs supporting the final result must be renamed by meaning, and any
    averaged fit must trace how many repeats were found, used, and excluded.
14. **Keep expert answers concise.** Give the direct recommendation first, then
    decision conditions, then the minimum representative numerical evidence.
    Do not print intermediate results unless requested.
    Expert answer order:

```text
direct recommendation -> fitting/fixing decision -> representative evidence -> assumptions and risks
```

---

## Data Assessment

**Input:** `scan-data` output plus user-supplied information
**Output:** usable groups/ranges, exclusions, cautions, and reasoning
**Applies to:** data-backed mode only

### Rules

- Treat `scan-data` grouping as first-pass organization, not final expert
  judgment; Must inspect all the data files. Use maximum and minimum of xdata and ydata as the first fast criteria to inspect the data.
- Must execute the point-by-point data variation check. First check applicablility of read image tool. If applicable, plot all candidate curves together and visually inspect all data. If not, compute cross-file standard deviation at each xdata point for data inspection. Stack signals onto a common xdata grid when needed. 
- Assess repeatability, phase integrity, signal quality, xdata
  coverage, and abnormal low/high-regime behavior before accepting data for
  fitting.
- Before accepting an averaged fit, explicitly decide which nominal repeats are
  averaged, excluded, or fitted separately.
- Do not average data from clearly different positions, frequency or offset
  ranges, measurement conditions, measurement batches, or clearly inconsistent
  repeats. If sample inhomogeneity may be responsible, flag it and consider
  separate-group fitting.
- Avoid data with obvious local jump, branch split, or point-specific deviation. Isolated abnormal points may be removed only with a recorded reason; segment
  abnormalities make the group suspicious or unusable until investigated.
- Express the accepted selection through paths spec/config when practical. A
  separate cleaned data directory may be created when it improves isolation or
  traceability. Never modify the raw source data.

Data assessment output should be concise:

```markdown
Data assessment decision

Use for fitting
- groups:
- xdata range:

Use with caution
- groups/points:
- reason:

Exclude
- groups/points:
- reason:
```

### Expert experience

- A repeated filename or group name does not guarantee a valid repeat. The same
  name may include independent measurements, interrupted runs, or re-measurement
  after a failed scan.
- If coordinate differences are small and xdata ranges are comparable,
  interpolation-based averaging can be acceptable. Interpolation must not merge
  data from different conditions or failed/restarted runs.
- Pre-fit assessment usually focuses on smoothness, repeatability, and phase
  integrity. Deeper model consistency is usually judged after fitting.
- Start with the most reliable-looking data group for trial fitting. If the
  result is poor or sample inhomogeneity is suspected, fit groups separately and
  compare.
- Phase signals are especially prone to jumps, discontinuities, and unwrap
  artifacts.
- Offset data often have less ideal raw quality than frequency sweeps and can be
  affected by spot quality and alignment.
- Offset scans with asymmetry, abnormal trends, or local bumps can be tested
  diagnostically, for example by fitting one side only, but should not be
  trusted as primary offsetfit input without caution.
- Diagnostic plots and statistics are primarily for AI/expert judgment and do
  not need to be shown to the user unless requested.

---

## Parameter Roles

**Input:** material system, user goal, and data assessment output if applicable
**Output:** role label and allowed adjustment range for each parameter
**Applies to:** both modes

### Role labels

```text
target              - the primary reported result the user cares about
nuisance-fitted     - fitted simply because it is unknown. Not the primary target
candidate-fitted    - possible to fit if sensitivity/uncertainty supports it
calibrated-fixed    - measured or calibrated separately
literature-fixed    - taken from literature values
ignored             - not treated as independent, such as a thin adhesion layer
```

For design-only mode, also mark these roles when useful:

```text
design variable     - value being chosen, such as transducer thickness or spot size
calibration-needed  - must be measured independently before reliable extraction
assumed             - fixed only for the design calculation
```

### Rules

- Assign parameter roles from the user goal first, then refine them using
  sensitivity and uncertainty.
- Unknown does not automatically mean fitted. If a non-target parameter can be
  calibrated, calibration is preferred over fitting.
- A `candidate-fitted` parameter enters a fit only if sensitivity is sufficient
  and uncertainty remains acceptable.
- When a non-target parameter strongly affects the target and cannot be
  calibrated, use sensitivity/uncertainty to decide whether it can be fitted or
  whether an additional data dimension is needed.
- Do not simultaneously fit multiple interface conductances by default. Use
  sensitivity/uncertainty to decide which interface is identifiable.
- Prefer no more than two simultaneously fitted parameters. Fitting more than
  two requires sensitivity and uncertainty support plus an explicit warning
  about local minima and initial-value dependence.
- An anisotropic layer has two conductivities, `Sr_N` and `Sz_N`. Before fixing
  either, check whether each direction is recoverable. Do not fit one direction
  by default when the user asks for "thermal conductivity" of an anisotropic
  layer.
- Do not treat spot size as fixed when user does not explicilty requested and usable high-frequency offset-amplitude data are available.
- Define allowed adjustment ranges before fitting. Large changes to thickness,
  spot size, layer structure, material identity, or parameter meaning require
  explicit user confirmation.

### Expert experience

- Interface conductance is often unknown. If it is not the main research target
  but still affects the target, classify it as `nuisance-fitted`.
- In multilayer or thin-film stacks, interface conductances and cross-plane
  thermal conductivity of thin layers can behave like serial thermal
  resistances and can be strongly correlated.
- If a lower or remote interface has low sensitivity, consider fixing it and
  fitting only the dominant interface parameter.
- Transducer thermal conductivity and thickness are usually
  `calibrated-fixed`, not freely fitted, unless requested or supported by sensitivity/uncertainty analysis.
- Spot size is usually `calibrated-fixed`. If spot size is not provided and usable high-frequency offset-amplitude data exist, classify it as `candidate-fitted` using spotfit rather than assumed. Treat it as `candidate-fitted` also when strong evidence suggests the nominal spot
  value is unreliable.
- Heat capacity is usually `literature-fixed` unless the user goal or
  uncertainty analysis justifies treating it otherwise.
- Non-target layer thicknesses and thermal properties are ideally
  calibrated or fixed.
- In design-only mode, uncertain transducer properties, spot size, thickness, or
  interface conductance can be scanned as parameter ranges to test their impact.
  Heat capacity usually remains literature-fixed.
- Interface conductance can be scanned over an experience-based preliminary
  range such as `1e7-1e8 W/m^2K`, but this range is not universal and must not
  be treated as a hard constraint.

---

## Scheme Design

**Input:** parameter roles, data availability, and data assessment output
**Output:** candidate scheme and generated config files
**Applies to:** both modes

### Rules

- Design candidate schemes before fitting. For each scheme, specify strategy,
  fitted parameters, xdata range, initial bounds, rationale, and risks.
- Generate base configs with `fdtr-config`. Generate sensitivity and uncertainty
  configs when the scheme needs design or validation before execution.
- When calling `fdtr-config` within this expert workflow, self-review and skip the default
  user-confirmation step after config generation.
- When comparing setups or ranges for extracting one parameter, compare that
  parameter's sensitivity against poorly calibrated nuisance parameters, not
  just its absolute sensitivity.
- For expert tasks with many independent candidate parameter combinations or
  fitting schemes, define the variants explicitly, run minimal boundary-case
  validation first, then run the full sweep or delegated exploration.
- For design-space exploration, test a sufficiently broad physically allowed
  parameter range before recommending an optimum. Do not conclude from a narrow
  local scan unless the user explicitly restricts the range.
- For offset phase sensitivity, do not rely only on full-range average
  sensitivity. Check the useful nonzero-offset regime, especially
  `offset > 2 * spot_size`.
- If available data can support spot calibration, evaluate spotfit before
  fixing spot size from file headers or treating it as known.

### Strategy entry criteria

| Strategy    | Use when                                                                                                                                                                |
| ----------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `freqfit`   | frequency sweep data are available and the target affects frequency-dependent phase/amplitude; cross-plane transport or interface resistance is important               |
| `offsetfit` | lateral heat spreading or in-plane conductivity is important, or spatial information helps decouple parameters                                                          |
| `spotfit`   | spot size is uncertain and offset/amplitude or another measurement dimension provides strong spot sensitivity                                                           |
| `iterfit`   | different measurement dimensions constrain different unresolved parameters, one step's fitted result is needed by another step, and repeating the sequence is necessary |

**Do not** jump directly to `iterfit`; first evaluate single-strategy
schemes such as `freqfit`, `offsetfit`, or `spotfit`.

For `iterfit`, each step must have a clear target supported by sensitivity or
uncertainty.

For design-only mode, design sensitivity sweeps over candidate setups and
prepare configs that explore which configuration best identifies the target
parameters.

### Expert experience

- Two-parameter fitting is usually more reliable than three-parameter fitting.
- Frequency sweeps often provide stronger evidence for cross-plane transport
  and interface resistance than for lateral transport.
- Offset phase in the useful nonzero-offset regime often carries more
  in-plane/lateral information.
- High-frequency offset amplitude is often useful for spot-size calibration when
  offset data quality is sufficient.
- Interface conductance and thin-film cross-plane conductivity can become
  strongly correlated because both contribute to serial thermal resistance.
- For highly anisotropic materials, a useful iterfit mapping can be high-frequency
  offset amplitude -> `spot_size`, offset phase -> `Sr_N`, and frequency sweep
  -> `Sz_N` plus `TBC_N`.
- For low conductivity substrates, sensitivity to the top transducer layer is usually higher.
- With larger spot size, it is often more sensitive for cross-plane transport while the sensitivity to in-plane transport increases for smaller spot size.
- Heat capacity and thermal conductivity of the same layer is often inseparable for a thick or semi-infinite layer.
- Large offset distance and high offset frequency often have worse noise.
  Higher-conductivity systems can usually support larger offset distance; Refer to
  Au/graphite example, about `15 um` is a common practical upper range.
- Very low frequencies are often weakly sensitive to many parameters.
- For non-separable parameters on one data line, such as serial resistances,
  consider fixing the nuisance-fitted parameter according to sensitivity
  analysis. If its value is unknown, scan a few reasonable values to check its
  influence on fit results.

---

## Execution

**Input:** config files generated in Scheme Design
**Output:** sensitivity, uncertainty, fit results, or design comparison results
**Applies to:** both modes

### Rules

- Do not modify configs during execution. If results indicate a problem,
  backtrack to Scheme Design.
- For expert tasks with ambiguous targets or fitting setups, run
  analysis first to determine viable fitting methods and parameter combinations. If multiple ways exist,
  execute the most viable one and report the alternatives.
- Reject a selected parameter set when validation does not support simultaneous
  identifiability.
- Do not run fitting in design-only mode.
- After data-backed scheme validation passes, run fitting through the existing
  config-driven path and then run post-fit uncertainty when needed.
- For iterfit, compute uncertainty for the final fitted parameter values. If
  uncertainty in one step depends on fitted parameters from other steps,
  uncertainty itself may need to be iterated.

Execution flow:

```text
sensitivity/uncertainty -> Result Review (pre-fit)
  not viable -> backtrack to Scheme Design
  viable -> fit or design comparison
```

### Expert experience

- For design-only mode, sensitivity is often the first step, and uncertainty provides further quantitative validation. Run uncertainty with explicit
  known-parameter errors; use 5% by default unless the user gives another value.
- Standalone uncertainty is local identifiability analysis, not a guarantee of
  global fitting robustness.

---

## Result Review

**Input:** calculation results, fit results, sensitivity/uncertainty outputs,
and diagnostic plots
**Output:** accept, accept with caveats, backtrack, or stop
**Applies to:** both modes

### Rules

Data-backed review checks:

1. **Residual quality** - is the fit curve consistent with data shape?
2. **Physical plausibility** - are fitted values within expected ranges? Compare
   against local material database values first and retrieve literature when
   necessary.
3. **Sensitivity support** - do fitted parameters have adequate sensitivity over
   the used xdata range?
4. **Uncertainty magnitude** - are uncertainties acceptable for the intended use?
5. **Parameter correlation** - are fitted parameters sufficiently decoupled?
6. **Boundary issues** - did any parameter hit its bound?

Design-only review checks:

1. **Parameter identifiability** - does sensitivity show that targets are
   distinguishable in the proposed measurement range?
2. **Uncertainty viability** - can the targets be extracted with acceptable
   uncertainty under the assumed known-parameter errors?
3. **Parameter separability** - are targets sufficiently decoupled from
   nuisance parameters?
4. **Setup robustness** - how would the reasonable change to assumptions (information not explicitly given by user) influence the recommendations?

Acceptance rules:

- If a parameter hits its bound, the fit is constrained by the bound, not by the
  data. Investigate before trusting the result.
- When a possible reason for a bad fit is found, do not stop at one alternative.
  Sweep the suspected dimension over a meaningful range.
- A partial-range fit is acceptable with explanation and supporting
  evidence.
- Diagnostic fits are not primary recommendations unless they pass the same
  acceptance checks as the final result.

Decision options:

```text
accept
accept with caveats
backtrack to the indicated stage
stop because conditions are insufficient
```

### Expert experience

- If offset and frequency-sweep data have incompatible individual optima, a
  compromise parameter set may be more appropriate than choosing one optimum.
- If fitting requires unreasonable thickness or spot-size adjustments, suspect
  data, calibration, or model issues.
- Uncertainty is not only for error bars; it also identifies which known
  parameters need better calibration.
- If one setup gives high target sensitivity but even higher sensitivity to an
  uncalibrated nuisance parameter, do not treat that setup as preferable.
- If low-frequency data fit poorly but higher-frequency data are good, fitting
  only the higher-frequency range can be acceptable with explanation.
- If a fitted interface conductance has low sensitivity, keep it as an internal
  `nuisance-fitted` parameter if needed, but do not overinterpret it as a strong
  physical result.
