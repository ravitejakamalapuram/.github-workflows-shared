1. **Identify the UX improvement:**
   - Looking at `scripts/onboard-wizard.py`, there are `.copy-btn-inline` buttons that use a thread-blocking `setTimeout` or change the text visually to "Copied!", but there's no screen-reader-friendly way (like `aria-live`) to announce the text has been copied, despite a clear guidance in `.jules/palette.md` to use `aria-live="polite"` for copy button feedback. Wait, the rule says "Using temporary inline text changes with aria-live="polite" provides a seamless and accessible state change for screen readers."

2. **Wait, there is also missing aria-label for copy buttons?** They are not icon-only buttons ("Copy"). But the `nav-tab` buttons have `disabled` states without aria-disabled or tooltips.

Let's check the `.jules/palette.md` again.
"When replacing disabled with aria-disabled='true', always ensure click events are blocked using if(this.getAttribute('aria-disabled') === 'true') return;"

The rule says:
"For interactive UI feedback (e.g., copy buttons) and form validation in this codebase, avoid thread-blocking alert() dialogs. Instead, use temporary inline text or visible state changes (such as displaying .alert-error divs) coupled with aria-live="polite" to ensure seamless and accessible state changes for screen readers."

Wait, the `scripts/onboard-wizard.py` does not use `alert()`, it uses inline text: `btn.innerText = 'Copied!';`. But the button itself does not have `aria-live="polite"`. By adding `aria-live="polite"` to the `.copy-btn-inline` elements, screen readers will announce when the text changes to "Copied!".
Wait, if `aria-live="polite"` is on the button, screen readers will read the button text change.
Alternatively, we can add `aria-live="polite"` to an invisible status region or to the button itself.
Actually, let's just add `aria-live="polite"` to the `copy-btn-inline` HTML directly!

Let's look at `scripts/onboard-wizard.py` lines 1899, 1906, 1913, 1920:
```html
<button class="copy-btn-inline" aria-live="polite" onclick="copyValue('copy-field-short')">Copy</button>
```

Let's check `scripts/onboard-wizard.py` lines 1898-1920:
```html
<button class="copy-btn-inline" aria-live="polite" onclick="copyValue('copy-field-short')">Copy</button>
...
```

Let's do this as the UX enhancement!
