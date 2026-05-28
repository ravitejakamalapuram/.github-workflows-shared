## 2025-05-28 - Optimize Changelog Git Log Fetching
**Learning:** In composite-actions/common/changelog/action.yml, running `git log` multiple times to grep for different commit types is redundant and causes O(N) operations to run N times. Since `git log` can be slow on repositories with long histories, fetching the commits once and grepping the output file is more efficient.
**Action:** When performing multiple grep operations on the same command output, fetch the output once into a file or variable, then run grep on the cached output to improve performance.
