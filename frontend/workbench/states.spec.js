import {test, expect} from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';
import {readFileSync} from 'node:fs';

const index=JSON.parse(readFileSync(new URL('../storybook-static/index.json',import.meta.url),'utf8'));
const stories=Object.values(index.entries).filter(entry=>entry.type==='story');
for (const story of stories) {
  test(story.id, async ({page}, testInfo) => {
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    page.on('request', request => {if (new URL(request.url()).pathname.startsWith('/api/')) errors.push(`Unexpected API request: ${request.url()}`);});
    await page.goto(`/iframe.html?id=${encodeURIComponent(story.id)}&viewMode=story`);
    await expect(page.locator('#storybook-root main')).toBeVisible();
    await expect.poll(() => page.evaluate(() => globalThis.__FAMILYOS_STORY_RESULT__?.status)).toBe('success');
    await expect(page.locator('[data-testid="error-message"]')).toHaveCount(0);
    // Storybook play functions also run in the standalone iframe.
    await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    expect((await new AxeBuilder({page}).analyze()).violations).toEqual([]);
    expect(await page.evaluate(() => navigator.serviceWorker.getRegistrations().then(items => items.length))).toBe(0);
    expect(errors).toEqual([]);
    await testInfo.attach(story.id, {body: await page.screenshot({fullPage: true}), contentType: 'image/png'});
  });
}
