from playwright.sync_api import sync_playwright

def run_cuj(page):
    page.goto("http://localhost:3005")
    page.wait_for_timeout(1000)

    # Let's interact with the sort by select
    page.locator("#sort-select").select_option("build_date")
    page.wait_for_timeout(1000)
    page.locator("#search-input").fill("test")
    page.wait_for_timeout(1000)

    page.screenshot(path="dashboard_interaction.png", full_page=True)

if __name__ == "__main__":
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            record_video_dir="/home/jules/verification/videos"
        )
        page = context.new_page()
        try:
            run_cuj(page)
        finally:
            context.close()
            browser.close()
