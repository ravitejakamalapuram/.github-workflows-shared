## 2024-06-04 - Missing Focus States in Embedded HTML
**Learning:** Python scripts containing large embedded HTML strings for UI often miss core keyboard accessibility requirements like `:focus-visible` because they aren't part of the standard CSS compilation/linting pipeline.
**Action:** When inspecting embedded web views or local admin panels in scripts, explicitly verify keyboard focus indicators.

## 2026-06-04 - Keyboard Accessibility for Dynamically Generated Interactive Elements
**Learning:** Dynamically generated interactive elements acting as buttons (like `div` elements) in Python-served HTML are not inherently accessible. They require explicit `tabindex=0`, `role="button"`, and keyboard event listeners (Enter and Space) to ensure they can be used by keyboard-only users.
**Action:** When dynamically generating non-standard interactive UI elements, always inject semantic `role`, `tabindex`, ARIA attributes (e.g. `aria-pressed`), and attach explicit `keydown` listeners mirroring `click` behavior.
## 2026-06-08 - Accessible Inline Validation Feedback
**Learning:** The onboard wizard was using thread-blocking `alert()` dialogues for form validation, which is a poor UX pattern and disrupts screen readers. Replacing these with inline error messages using `aria-live="polite"` provides non-intrusive feedback and ensures screen readers announce errors smoothly without losing context.
**Action:** Always prefer inline feedback with `aria-live` over blocking `alert()` for form validation across the UI.
