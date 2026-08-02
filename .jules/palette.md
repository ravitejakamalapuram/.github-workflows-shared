## 2026-06-07 - Replaced blocking alert with accessible inline feedback
**Learning:** Thread-blocking alerts for simple UI feedback disrupt the user experience and are inaccessible. Using temporary inline text changes with `aria-live="polite"` provides a seamless and accessible state change for screen readers.
**Action:** Always avoid `alert()` for simple interactive feedback like copy buttons, and opt for inline state changes with ARIA support.

## 2026-06-07 - Implement aria-disabled for disabled button tooltips
**Learning:** Replacing native `disabled` with `aria-disabled="true"` to allow tooltips for screen readers and hovers natively exposes elements to click events. Thus, you must implement javascript event guards on the handler directly.
**Action:** When replacing `disabled` with `aria-disabled='true'`, always ensure click events are blocked using `if(this.getAttribute('aria-disabled') === 'true') return;` or equivalent guard logic to prevent functional regressions.

## 2026-06-07 - Replace blocking alerts with accessible toast notifications
**Learning:** Thread-blocking alerts for simple UI feedback disrupt the user experience and are inaccessible. Using temporary inline text changes with `aria-live="polite"` provides a seamless and accessible state change for screen readers.
**Action:** Always avoid `alert()` for simple interactive feedback, and opt for inline state changes with ARIA support.
## 2026-08-02 - Add real-time validation and tooltip to disabled build button
**Learning:** Replaced native `disabled` with `aria-disabled="true"` on a dynamically disabled button to allow screen reader focus and tooltip hovering, bound validation to `oninput` for immediate visual feedback, and implemented a context-aware event guard using an active loading CSS class to preserve expected UI feedback on invalid inputs while blocking overlapping rapid clicks.
**Action:** Always favor `aria-disabled` over native `disabled` for buttons requiring context, attach validation to `oninput` for real-time responsiveness, and guard `aria-disabled` click events with specific UI state checks to avoid regressing explicit error feedback.
