## 2024-06-04 - Missing Focus States in Embedded HTML
**Learning:** Python scripts containing large embedded HTML strings for UI often miss core keyboard accessibility requirements like `:focus-visible` because they aren't part of the standard CSS compilation/linting pipeline.
**Action:** When inspecting embedded web views or local admin panels in scripts, explicitly verify keyboard focus indicators.

## 2026-06-04 - Keyboard Accessibility for Dynamically Generated Interactive Elements
**Learning:** Dynamically generated interactive elements acting as buttons (like `div` elements) in Python-served HTML are not inherently accessible. They require explicit `tabindex=0`, `role="button"`, and keyboard event listeners (Enter and Space) to ensure they can be used by keyboard-only users.
**Action:** When dynamically generating non-standard interactive UI elements, always inject semantic `role`, `tabindex`, ARIA attributes (e.g. `aria-pressed`), and attach explicit `keydown` listeners mirroring `click` behavior.

## 2024-06-07 - Accessible Inline Feedback over Native Alerts
**Learning:** For interactive UI feedback (like a "Copy" button) in this codebase, thread-blocking `alert()` dialogs disrupt the user flow and provide poor UX.
**Action:** Instead of `alert()`, use temporary inline text changes (e.g., changing button text to "Copied!") coupled with `aria-live="polite"` to ensure seamless and accessible state changes that are properly announced to screen readers.
