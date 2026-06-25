## 2024-05-27 - [Optimizing Flutter CLI Invocations]
**Learning:** In GitHub Actions, calling the `flutter` CLI multiple times (like `flutter --version`) is surprisingly slow (2-3 seconds per call) because it initializes the Dart VM, checks lockfiles, and sometimes verifies toolchains.
**Action:** Always cache the output of Flutter CLI commands if the result is needed multiple times or for parsing, rather than invoking the command repeatedly. Remove redundant invocations used purely for logging if the information is captured elsewhere.

## 2025-05-28 - Optimize Changelog Git Log Fetching
**Learning:** In composite-actions/common/changelog/action.yml, running `git log` multiple times to grep for different commit types is redundant and causes O(N) operations to run N times. Since `git log` can be slow on repositories with long histories, fetching the commits once and grepping the output file is more efficient.
**Action:** When performing multiple grep operations on the same command output, fetch the output once into a file or variable, then run grep on the cached output to improve performance.

## 2024-06-03 - Avoid High Python Startup Overhead in GitHub Actions Bash Scripts
**Learning:** Using `python3 -c` or `python3 -m json.tool` for simple JSON parsing or validation inside GitHub Actions bash scripts introduces high overhead due to Python interpreter startup time. This is especially impactful in composite actions executed multiple times.
**Action:** Always prefer using `jq` for inline JSON operations within bash scripts. Use `jq empty` for fast validation and `jq -r '.key // "default"'` for retrieving properties safely and efficiently.

## 2024-05-30 - Python interpreter startup overhead in bash loops
**Learning:** Invoking Python (`python3 -c`) inside bash loops (e.g., `while read` or `for file in ...`) for CI scripts causes massive performance overhead due to the repeated initialization of the Python runtime for every single file.
**Action:** Use `xargs` to batch files into a single Python execution (e.g., `find ... | xargs python3 -c 'import sys; [process(f) for f in sys.argv[1:]]'`) or use tools natively designed for streams like `jq` to process data significantly faster.

## 2024-06-05 - Safe Bash JQ Loops for Object Literals
**Learning:** When fetching JSON object keys via `jq` to loop in bash (e.g. `jq -r '.icons | select(type == "object") | values[]' "$MANIFEST"`), suppressing all stderr with `2>/dev/null || true` introduces a critical regression where bad files or absent objects silently result in no processing.
**Action:** Let jq throw valid errors. Use safe `select()` inside jq so legitimate null values are handled properly without suppressing real syntax or missing file errors.

## 2024-06-05 - Batching JQ Queries to Avoid Redundant Process Overhead
**Learning:** When needing multiple fields from a JSON file using `jq` in bash, invoking `jq` multiple times (e.g. `EXT_NAME=$(jq ...)`, `EXT_VERSION=$(jq ...)`) adds redundant process startup overhead.
**Action:** Always batch `jq` operations when extracting multiple properties from the same file. Use `jq -r '[.prop1, .prop2] | @tsv'` and read the values simultaneously using `IFS=$'\t' read -r var1 var2 < <(jq ...)`.

## 2025-10-25 - Avoid Process Spawning Overhead in CI Scripts
**Learning:** Using `find ... -exec ... {} \;` in GitHub Actions for checking multiple files creates massive overhead because it spawns a new process (e.g., Python runtime, Bash invocation) for every single matched file.
**Action:** Always use `find ... -print0 | xargs -0 -r ...` to batch operations. For commands like `bash -n` that don't natively process subsequent files properly, wrap them in a short loop via `sh -c 'for script; do bash -n "$script" || exit 255; done' sh`.

## 2024-06-06 - Batching jq empty validation
**Learning:** `jq empty` can natively validate multiple JSON files at once and will return a non-zero exit code if any file is invalid. Wrapping it in a shell loop via `xargs` and `sh -c` introduces unnecessary process overhead per file.
**Action:** Pass multiple files directly to `jq empty` via `xargs -0 jq empty` instead of wrapping it in a shell `for` loop to avoid subshell overhead.

## 2024-06-06 - [Batching Node.js Validations Across CPU Cores]
**Learning:** Using `while read f; do node -c "$f"; done` to validate JavaScript syntax sequentially introduces massive performance overhead due to the V8 engine's startup time per file. Attempting to optimize this by running a single `node -e` script that parses all files via `vm.Script` fails to support ES modules natively, causing functional regressions in modern environments.
**Action:** Always optimize large sets of slow shell commands by parallelizing across multiple CPU cores using `xargs -P <cores>` instead of sequential loops or complex runtime emulation. Example: `find ... -print0 | xargs -0 -P 8 sh -c 'for f; do node -c "$f"; done' sh`. Ensure `xargs` options are POSIX-compliant (e.g., omitting the GNU-only `-r` flag) for broader cross-platform runner compatibility.

## 2026-06-22 - Native base64 decoding instead of Python

**Learning:** Shell scripts using inline Python (`python3 - << 'EOF'`) to decode base64 strings incur a high startup cost, especially in CI.
**Action:** Replace inline Python base64 decoding with native `base64 --decode` (with a `-D` fallback for macOS compatibility) inside a standard bash loop.

## 2026-06-24 - [Optimize YAML Validation in CI Scripts]

**Learning:** Using inline Python (`python3 -c`) with the `yaml` module to validate YAML files inside bash scripts introduces unnecessary interpreter startup latency overhead.
**Action:** Replace inline Python YAML validation with `yq empty`, which is a faster natively compiled processor, to eliminate the startup overhead and speed up CI workflows.

## 2024-06-07 - Replace Python JSON parsing with jq in workflows

**Learning:** Using inline Python (`python3 -c`) for JSON file updates in GitHub Actions introduces unnecessary interpreter startup overhead.
**Action:** Replace inline Python scripts with `jq` for JSON manipulation (e.g. updating app-metadata.json) to eliminate python interpreter startup time, keeping workflows fast and lightweight.
