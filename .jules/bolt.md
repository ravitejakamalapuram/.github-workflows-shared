## 2024-05-27 - [Optimizing Flutter CLI Invocations]
**Learning:** In GitHub Actions, calling the `flutter` CLI multiple times (like `flutter --version`) is surprisingly slow (2-3 seconds per call) because it initializes the Dart VM, checks lockfiles, and sometimes verifies toolchains.
**Action:** Always cache the output of Flutter CLI commands if the result is needed multiple times or for parsing, rather than invoking the command repeatedly. Remove redundant invocations used purely for logging if the information is captured elsewhere.
