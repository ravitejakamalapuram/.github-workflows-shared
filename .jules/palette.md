## 2026-06-07 - Replaced blocking alert with accessible inline feedback
**Learning:** Thread-blocking alerts for simple UI feedback disrupt the user experience and are inaccessible. Using temporary inline text changes with `aria-live="polite"` provides a seamless and accessible state change for screen readers.
**Action:** Always avoid `alert()` for simple interactive feedback like copy buttons, and opt for inline state changes with ARIA support.

## 2026-06-07 - Implement aria-disabled for disabled button tooltips
**Learning:** Replacing native `disabled` with `aria-disabled="true"` to allow tooltips for screen readers and hovers natively exposes elements to click events. Thus, you must implement javascript event guards on the handler directly.
**Action:** When replacing `disabled` with `aria-disabled='true'`, always ensure click events are blocked using `if(this.getAttribute('aria-disabled') === 'true') return;` or equivalent guard logic to prevent functional regressions.

## 2026-06-08 - Add explicit required indicators and aria-live properties
**Learning:** Missing visual required indicators cause user friction because users may not realize some fields are required before triggering actions (like authorizing with Google). Also, dynamically updated feedback boxes need `aria-live` to be read correctly by screen readers.
**Action:** Explicitly mark required form fields with `*` and `aria-required="true"` to improve both visual UX and screen reader support. Apply `aria-live="assertive"` or `"polite"` on dynamically updated message and alert boxes.
