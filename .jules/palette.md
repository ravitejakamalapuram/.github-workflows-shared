## 2024-06-04 - Missing Focus States in Embedded HTML
**Learning:** Python scripts containing large embedded HTML strings for UI often miss core keyboard accessibility requirements like `:focus-visible` because they aren't part of the standard CSS compilation/linting pipeline.
**Action:** When inspecting embedded web views or local admin panels in scripts, explicitly verify keyboard focus indicators.

## 2026-06-04 - Keyboard Accessibility for Dynamically Generated Interactive Elements
**Learning:** Dynamically generated interactive elements acting as buttons (like `div` elements) in Python-served HTML are not inherently accessible. They require explicit `tabindex=0`, `role="button"`, and keyboard event listeners (Enter and Space) to ensure they can be used by keyboard-only users.
**Action:** When dynamically generating non-standard interactive UI elements, always inject semantic `role`, `tabindex`, ARIA attributes (e.g. `aria-pressed`), and attach explicit `keydown` listeners mirroring `click` behavior.

## 2024-06-05 - Inline Feedback over Blocking Dialogs for Copy Actions
**Learning:** Using blocking browser `alert()` dialogues for common micro-interactions like "copy to clipboard" interrupts user flow and creates a poor experience in embedded/local HTML views. Furthermore, missing ARIA labels and focus states on small utilitarian buttons hinder accessibility.
**Action:** When implementing copy buttons or similar micro-actions, use contextual inline feedback (e.g., temporarily changing the button text to "✓ Copied!" and updating colors) instead of blocking alerts. Always ensure utilitarian buttons have descriptive `aria-label` attributes and explicit `:focus-visible` keyboard states.
