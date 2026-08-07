## 2026-06-07 - Replaced blocking alert with accessible inline feedback
**Learning:** Thread-blocking alerts for simple UI feedback disrupt the user experience and are inaccessible. Using temporary inline text changes with `aria-live="polite"` provides a seamless and accessible state change for screen readers.
**Action:** Always avoid `alert()` for simple interactive feedback like copy buttons, and opt for inline state changes with ARIA support.

## 2026-06-07 - Implement aria-disabled for disabled button tooltips
**Learning:** Replacing native `disabled` with `aria-disabled="true"` to allow tooltips for screen readers and hovers natively exposes elements to click events. Thus, you must implement javascript event guards on the handler directly.
**Action:** When replacing `disabled` with `aria-disabled='true'`, always ensure click events are blocked using `if(this.getAttribute('aria-disabled') === 'true') return;` or equivalent guard logic to prevent functional regressions.

## 2026-06-07 - Replace blocking alerts with accessible toast notifications
**Learning:** Thread-blocking alerts for simple UI feedback disrupt the user experience and are inaccessible. Using temporary inline text changes with `aria-live="polite"` provides a seamless and accessible state change for screen readers.
**Action:** Always avoid `alert()` for simple interactive feedback, and opt for inline state changes with ARIA support.

## 2024-05-14 - Migrate Build Button to aria-disabled
**Learning:** In the `scripts/onboard-wizard.py` dashboard UI, replacing native `disabled` attributes with `aria-disabled="true"` correctly exposes the button's disabled state to screen readers and allows hover tooltips to render. However, because `aria-disabled` does not block pointer events natively, JavaScript event guards must be added to the button's click handler to prevent execution. Additionally, when using interval pollers (like `state.activeBuildInterval`) as boolean state flags for these guards, they must be explicitly reset to `null` after calling `clearInterval` to avoid state locking bugs.
**Action:** Always complement `aria-disabled` conversions with strict JavaScript event guards, ensure interval variables are nulled out when cleared, and trigger validation checks on `oninput` rather than `onchange` or `onblur` for immediate visual feedback.
