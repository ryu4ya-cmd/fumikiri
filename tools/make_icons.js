// icons/icon.svg から、ホーム画面用のアイコン（png）を作る。
// Playwright（Chromium）を使う。使い方: node tools/make_icons.js
// Playwright がこのフォルダに入っていないときは、NODE_PATH で入っている場所を教える
const fs = require('fs');
const path = require('path');
const { chromium } = require('playwright');

const ROOT = path.resolve(__dirname, '..');
const svg = fs.readFileSync(path.join(ROOT, 'icons', 'icon.svg'), 'utf8');
(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage();
  for (const size of [32, 180, 192, 512]) {
    await page.setViewportSize({ width: size, height: size });
    await page.setContent(`<style>html,body{margin:0}svg{display:block;width:${size}px;height:${size}px}</style>${svg}`);
    await page.screenshot({ path: path.join(ROOT, 'icons', `icon-${size}.png`) });
  }
  await browser.close();
  console.log('icons/icon-*.png を作りました');
})();
