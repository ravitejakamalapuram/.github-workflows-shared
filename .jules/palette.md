## 2026-06-07 - Replaced blocking alert with accessible inline feedback
**Learning:** Thread-blocking alerts for simple UI feedback disrupt the user experience and are inaccessible. Using temporary inline text changes with `aria-live="polite"` provides a seamless and accessible state change for screen readers.
**Action:** Always avoid `alert()` for simple interactive feedback like copy buttons, and opt for inline state changes with ARIA support.

## 2026-06-07 - Implement aria-disabled for disabled button tooltips
**Learning:** Replacing native `disabled` with `aria-disabled="true"` to allow tooltips for screen readers and hovers natively exposes elements to click events. Thus, you must implement javascript event guards on the handler directly.
**Action:** When replacing `disabled` with `aria-disabled='true'`, always ensure click events are blocked using `if(this.getAttribute('aria-disabled') === 'true') return;` or equivalent guard logic to prevent functional regressions.

## 2026-06-07 - Replace blocking alerts with accessible toast notifications
**Learning:** Thread-blocking alerts for simple UI feedback disrupt the user experience and are inaccessible. Using temporary inline text changes with `aria-live="polite"` provides a seamless and accessible state change for screen readers.
**Action:** Always avoid `alert()` for simple interactive feedback, and opt for inline state changes with ARIA support.
## 2024-08-01 - Accessible Disabled State for Build Button
**Learning:** Native `disabled` attributes completely swallow pointer events, rendering interactive feedback mechanisms (like toast notifications on click) unreachable. By replacing `disabled` with `aria-disabled="true"`, screen readers still announce the state correctly while allowing pointer interactions, enabling us to display contextual error toasts to users who try to click a disabled action.
**Action:** Always prefer `aria-disabled` combined with event guards when disabled buttons need to provide inline feedback on click, but ensure you differentiate between 'invalid input' states (where we want to show feedback) and 'loading' states (where we want to silently block clicks).
