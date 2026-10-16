import {test, expect} from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';

const stories = ['forms--fields', 'forms--validation', 'forms--picker', 'forms--empty-picker', 'forms--disabled', 'forms--loading', 'forms--offline-stale', 'forms--unavailable', 'feedback--confirmation', 'feedback--toast', 'feedback--quick-create'];
for (const story of stories) {
  test(story, async ({page}, testInfo) => {
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    page.on('request', request => {if (new URL(request.url()).pathname.startsWith('/api/')) errors.push(`Unexpected API request: ${request.url()}`);});
    await page.goto(`/iframe.html?id=familyos-${story}&viewMode=story`);
    await expect(page.locator('#storybook-root main')).toBeVisible();
    await expect(page.locator('[data-testid="error-message"]')).toHaveCount(0);
    // Storybook play functions also run in the standalone iframe.
    await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    expect((await new AxeBuilder({page}).analyze()).violations).toEqual([]);
    expect(await page.evaluate(() => navigator.serviceWorker.getRegistrations().then(items => items.length))).toBe(0);
    expect(errors).toEqual([]);
    await testInfo.attach(story, {body: await page.screenshot({fullPage: true}), contentType: 'image/png'});
  });
}
