## 2024-06-04 - Missing Focus States in Embedded HTML
**Learning:** Python scripts containing large embedded HTML strings for UI often miss core keyboard accessibility requirements like `:focus-visible` because they aren't part of the standard CSS compilation/linting pipeline.
**Action:** When inspecting embedded web views or local admin panels in scripts, explicitly verify keyboard focus indicators.
