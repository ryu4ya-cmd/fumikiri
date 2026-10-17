// ゲームで使う声の部品（セリフのかけら）をぜんぶ JSON で出す。tools/make_voice.py が使う。
// src/game.html をそのまま jsdom で読みこんで、ゲームの中の voiceLines() をよぶ。
// 使い方: node tools/voice_lines.js > 一覧.json
const fs = require('fs');
const path = require('path');
const { JSDOM, VirtualConsole } = require('jsdom');

const html = fs.readFileSync(path.join(__dirname, '..', 'src', 'game.html'), 'utf8');
const dom = new JSDOM(`<!doctype html><html><head></head><body>${html}</body></html>`, {
  runScripts: 'dangerously',
  url: 'https://example.com/',
  pretendToBeVisual: true,
  virtualConsole: new VirtualConsole(),
});
const lines = dom.window.voiceLines();
process.stdout.write(JSON.stringify(lines));
dom.window.close();
