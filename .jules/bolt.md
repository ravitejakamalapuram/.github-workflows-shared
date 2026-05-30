## 2026-05-27 - Replace python3 with jq for JSON parsing
**Learning:** In GitHub Actions runners, using python3 to extract simple values from JSON files is significantly slower (~45x slower in synthetic benchmark: 3.8s vs 0.08s for 10 iterations) than using jq, due to Python startup time overhead.
**Action:** Replaced python3 JSON parsing with jq in composite-actions/chrome-extension/validate/action.yml and package/action.yml to improve action execution speed.
## 2026-05-27 - Never overwrite $PATH in bash scripts
**Learning:** When iterating over shell output in a while loop (e.g. `while read -r KEY PATH`), using PATH as a loop variable overwrites the system's execution path. This will cause subsequent external commands to fail.
**Action:** Always use alternative variable names like FILE_PATH or ITEM_PATH in read loops.
