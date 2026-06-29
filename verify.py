from playwright.sync_api import sync_playwright

def run_cuj(page):
    page.goto("http://localhost:3005")
    page.wait_for_timeout(1000)

    # We want to check the dashboard tab controls which should be visible immediately
    # specifically the input field which we added an aria-label to
    # and the module select which should be in the DOM

    # Let's take a screenshot of the main dashboard UI
    page.screenshot(path="dashboard_controls.png", full_page=True)

if __name__ == "__main__":
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()
        page = context.new_page()
        try:
            run_cuj(page)
        finally:
            context.close()
            browser.close()
