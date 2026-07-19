const { chromium } = require('playwright');
(async () => {
  const browser = await chromium.launch();
  const context = await browser.newContext({ recordVideo: { dir: './videos' } });
  const page = await context.newPage();
  await page.goto('http://localhost:3005');
  // Force display the target tab content since direct click through UI can be brittle
  await page.evaluate(() => {
    const tabs = document.querySelectorAll('.tab-content');
    tabs.forEach(t => { t.style.display = 'none'; t.classList.remove('active'); });
    const targetTab = document.getElementById('tab-content-builds');
    if(targetTab) { targetTab.style.display = 'flex'; targetTab.classList.add('active'); }
  });
  await page.waitForTimeout(500); // Wait for transition

  const btn = await page.locator('#btn-run-build');
  await btn.hover();
  await page.waitForTimeout(1000); // Wait for tooltip to appear

  await page.screenshot({ path: 'test_screenshot.png' });
  await context.close();
  await browser.close();
})();
