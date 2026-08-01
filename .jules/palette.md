## 2026-06-07 - Replaced blocking alert with accessible inline feedback
**Learning:** Thread-blocking alerts for simple UI feedback disrupt the user experience and are inaccessible. Using temporary inline text changes with `aria-live="polite"` provides a seamless and accessible state change for screen readers.
**Action:** Always avoid `alert()` for simple interactive feedback like copy buttons, and opt for inline state changes with ARIA support.

## 2026-06-07 - Implement aria-disabled for disabled button tooltips
**Learning:** Replacing native `disabled` with `aria-disabled="true"` to allow tooltips for screen readers and hovers natively exposes elements to click events. Thus, you must implement javascript event guards on the handler directly.
**Action:** When replacing `disabled` with `aria-disabled='true'`, always ensure click events are blocked using `if(this.getAttribute('aria-disabled') === 'true') return;` or equivalent guard logic to prevent functional regressions.

## 2026-06-07 - Replace blocking alerts with accessible toast notifications
**Learning:** Thread-blocking alerts for simple UI feedback disrupt the user experience and are inaccessible. Using temporary inline text changes with `aria-live="polite"` provides a seamless and accessible state change for screen readers.
**Action:** Always avoid `alert()` for simple interactive feedback, and opt for inline state changes with ARIA support.
## 2024-08-01 - Immediate validation on UI forms
**Learning:** Added `oninput` validation to text inputs that control disabled states of submit buttons to prevent users from having to blur the field to see the state change. This significantly reduces cognitive load and confusion when filling out form configurations by providing an immediate, real-time feedback loop.
**Action:** When making form fields that determine button enabled/disabled states, prioritize immediate visual feedback by firing the validation logic `oninput` rather than relying strictly on blur or onchange events, unless doing so degrades performance noticeably.
