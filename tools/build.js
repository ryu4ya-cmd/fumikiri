// src/game.html から、GitHub Pages で配る index.html を作る。
//
// src/game.html は claude.ai のアーティファクトと同じ「中身だけ」の形式なので、
// ここで <head>（アイコン・ホーム画面用の設定）を足して、ふつうのページにする。
// あわせてスクリプトを Babel で古い書き方に変換し、古い Android タブレット
// （Android 5 の Chrome など）でも動くようにする。
// 使い方: npm install（はじめの1回だけ）→ npm run build
const fs = require('fs');
const path = require('path');
const babel = require('@babel/core');

const ROOT = path.resolve(__dirname, '..');
// CSS の変数が使える Chrome 49 を下限にする
const TARGETS = 'chrome 49, safari 10, firefox 52';

let src = fs.readFileSync(path.join(ROOT, 'src', 'game.html'), 'utf8');
src = src.split('\n').filter(line => !line.includes('claude:viewport-fit-sides')).join('\n');

src = src.replace(/<script>([\s\S]*?)<\/script>/g, (_, code) => {
  const out = babel.transformSync(code, {
    babelrc: false,
    configFile: false,
    sourceType: 'script',
    compact: false,
    comments: true,
    presets: [['@babel/preset-env', { targets: TARGETS, bugfixes: true, modules: false }]],
  });
  return `<script>\n${out.code}\n</script>`;
});

// 最初の </style> までを <head> に、残りを <body> に入れる
const cut = src.indexOf('</style>') + '</style>'.length;
const headPart = src.slice(0, cut).trim();
const bodyPart = src.slice(cut).trim();

const HEAD = `<!doctype html>
<html lang="ja">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<meta name="description" content="ふみきりをカンカン鳴らして、マルーン色の電車を通す、幼児向けの電車あそび">
<meta name="theme-color" content="#8fd0ff">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-title" content="ふみきり">
<link rel="icon" type="image/png" sizes="32x32" href="icons/icon-32.png">
<link rel="apple-touch-icon" sizes="180x180" href="icons/icon-180.png">
<link rel="manifest" href="manifest.webmanifest">
<style>:root{box-sizing:border-box;padding-top:env(safe-area-inset-top,0px);padding-bottom:env(safe-area-inset-bottom,0px)}body{margin:0;font:14px -apple-system,BlinkMacSystemFont,sans-serif}[hidden]{display:none!important}</style>
`;

fs.writeFileSync(path.join(ROOT, 'index.html'), `${HEAD}${headPart}\n</head>\n<body>\n${bodyPart}\n</body>\n</html>\n`);
console.log('index.html を作りました');
