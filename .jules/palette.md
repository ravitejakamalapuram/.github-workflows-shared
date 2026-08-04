## 2026-06-07 - Replaced blocking alert with accessible inline feedback
**Learning:** Thread-blocking alerts for simple UI feedback disrupt the user experience and are inaccessible. Using temporary inline text changes with `aria-live="polite"` provides a seamless and accessible state change for screen readers.
**Action:** Always avoid `alert()` for simple interactive feedback like copy buttons, and opt for inline state changes with ARIA support.

## 2026-06-07 - Implement aria-disabled for disabled button tooltips
**Learning:** Replacing native `disabled` with `aria-disabled="true"` to allow tooltips for screen readers and hovers natively exposes elements to click events. Thus, you must implement javascript event guards on the handler directly.
**Action:** When replacing `disabled` with `aria-disabled='true'`, always ensure click events are blocked using `if(this.getAttribute('aria-disabled') === 'true') return;` or equivalent guard logic to prevent functional regressions.

## 2026-06-07 - Replace blocking alerts with accessible toast notifications
**Learning:** Thread-blocking alerts for simple UI feedback disrupt the user experience and are inaccessible. Using temporary inline text changes with `aria-live="polite"` provides a seamless and accessible state change for screen readers.
**Action:** Always avoid `alert()` for simple interactive feedback, and opt for inline state changes with ARIA support.
## 2024-05-14 - Aria-Disabled and Event Guards
**Learning:** When dynamically transitioning an element from a native `disabled` state to an `aria-disabled="true"` state via JavaScript to improve accessibility (such as showing tooltips), we must ensure the `aria-disabled` event guard preserves prior UI feedback (like toast notifications) and explicitly re-evaluates the context to handle multiple disabled states correctly (e.g. invalid vs loading). We should also bind validation logic to `oninput` for real-time visual feedback rather than `blur`/`change`.
**Action:** Always replace native `disabled` assignment with `aria-disabled` set to `"true"` or `"false"`, apply `oninput` handlers for realtime feedback, ensure `removeAttribute("disabled")` is explicitly called, and retain event guards inside `onclick` handlers that correctly distinguish between different states to trigger appropriate UI feedback.
