## 2024-06-05 - Replacing blocking alerts with inline feedback for better UX
**Learning:** Found a pattern of using `alert()` for simple interaction feedback (like copying text), which blocks the UI thread and provides a jarring user experience.
**Action:** Replace `alert()` dialogs with temporary inline text/state changes and ensure `aria-live="polite"` is used so screen readers announce the state change without losing focus or blocking.
