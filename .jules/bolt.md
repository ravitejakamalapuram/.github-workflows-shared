## 2024-05-27 - [Optimizing Flutter CLI Invocations]
**Learning:** In GitHub Actions, calling the `flutter` CLI multiple times (like `flutter --version`) is surprisingly slow (2-3 seconds per call) because it initializes the Dart VM, checks lockfiles, and sometimes verifies toolchains.
**Action:** Always cache the output of Flutter CLI commands if the result is needed multiple times or for parsing, rather than invoking the command repeatedly. Remove redundant invocations used purely for logging if the information is captured elsewhere.

## 2025-05-28 - Optimize Changelog Git Log Fetching
**Learning:** In composite-actions/common/changelog/action.yml, running `git log` multiple times to grep for different commit types is redundant and causes O(N) operations to run N times. Since `git log` can be slow on repositories with long histories, fetching the commits once and grepping the output file is more efficient.
**Action:** When performing multiple grep operations on the same command output, fetch the output once into a file or variable, then run grep on the cached output to improve performance.

## 2024-06-03 - Avoid High Python Startup Overhead in GitHub Actions Bash Scripts
**Learning:** Using `python3 -c` or `python3 -m json.tool` for simple JSON parsing or validation inside GitHub Actions bash scripts introduces high overhead due to Python interpreter startup time. This is especially impactful in composite actions executed multiple times.
**Action:** Always prefer using `jq` for inline JSON operations within bash scripts. Use `jq empty` for fast validation and `jq -r '.key // "default"'` for retrieving properties safely and efficiently.

## 2024-06-05 - Safe Bash JQ Loops for Object Literals
**Learning:** When fetching JSON object keys via `jq` to loop in bash (e.g. `jq -r '.icons | select(type == "object") | values[]' "$MANIFEST"`), suppressing all stderr with `2>/dev/null || true` introduces a critical regression where bad files or absent objects silently result in no processing.
**Action:** Let jq throw valid errors. Use safe `select()` inside jq so legitimate null values are handled properly without suppressing real syntax or missing file errors.

## 2024-06-05 - Batching JQ Queries to Avoid Redundant Process Overhead
**Learning:** When needing multiple fields from a JSON file using `jq` in bash, invoking `jq` multiple times (e.g. `EXT_NAME=$(jq ...)`, `EXT_VERSION=$(jq ...)`) adds redundant process startup overhead.
**Action:** Always batch `jq` operations when extracting multiple properties from the same file. Use `jq -r '[.prop1, .prop2] | @tsv'` and read the values simultaneously using `IFS=$'\t' read -r var1 var2 < <(jq ...)`.
