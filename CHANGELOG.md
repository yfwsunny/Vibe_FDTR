# Changelog

## 0.1.1 - 2026-06-03

- Added shared offset-center preprocessing in `fdtr.fit.offsetcenter_cal`.
- Updated standalone `offsetfit` to use same-frequency amplitude data for center estimation.
- Updated `iterfit` offset steps to load and use same-direction, same-frequency center amplitude data.
- Aligned fit preprocessing, output CSV, and plot generation so they use the same center reference.
- Improved symmetric ideal offset scans by handling tied amplitude maxima before local Gaussian center fitting.
- Updated FDTR agent skill guidance for iterfit pipeline behavior.
