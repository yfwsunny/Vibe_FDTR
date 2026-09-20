# FDTR Data File Formats

## Offset Scan

- **Columns**: 13 (offset, R1, theta1, R2, theta2, ..., R6, theta6)
- **Header**: date line at top, second line contains frequency metadata as `(NNNN Hz)` patterns
- **Filename direction**: files are commonly labeled `XScan` or `YScan`, but config patterns map them into logical fit axes.
- **Probe/pump radii**: extracted from file metadata if present
- **Units**: offset in um, R in arbitrary units, theta in degrees

### File Naming Patterns

- `*XScan*.txt` — X-direction offset scans
- `*YScan*.txt` — Y-direction offset scans

In iterfit, `offset_pattern` selects the logical X dataset and
`offset_pattern_y` selects the logical Y dataset. Swapping these patterns
allows YScan data to be fit as logical X without creating a custom pipeline.

### Frequency Discovery

Modulation frequencies are embedded in the second header line as `(NNNN Hz)`. Each column pair (R, theta) maps to one frequency.

## Freq Sweep

- **Columns**: 3 (frequency, amplitude, phase)
- **Header**: date line at top
- **Units**: frequency in Hz, amplitude in arbitrary units, phase in degrees

### File Naming Patterns

- `image_point*.txt` — valid freq-sweep data points (used for fitting)
- `Pump_Phase*.txt` — pump phase reference (skipped automatically)

## Multi-File Averaging

When multiple data files exist for the same experimental condition:

- Set `average = true` in config `[fit]` section
- PCHIP interpolation averages files onto a common grid
- Standard deviations computed for uncertainty estimation
- Always average — never pick only one file when multiple exist
