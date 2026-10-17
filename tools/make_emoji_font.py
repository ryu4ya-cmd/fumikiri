"""古い端末向けの絵文字フォント fonts/emoji.ttf を作り直す。

src/game.html で使っている絵文字だけを、Noto Color Emoji（CBDT 形式。Chrome 67 などの
古いブラウザでも色つきで出せる）から抜き出す。ゲームに絵文字を足したら実行する。
使い方: pip install fonttools → python3 tools/make_emoji_font.py [Noto Color Emoji の ttf]
（ttf を省くと、Debian/Ubuntu の fonts-noto-color-emoji の場所を使う）
"""
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
NOTO = sys.argv[1] if len(sys.argv) > 1 else '/usr/share/fonts/truetype/noto/NotoColorEmoji.ttf'

src = (ROOT / 'src' / 'game.html').read_text(encoding='utf-8')
emoji_re = re.compile(
    '[\U0001F000-\U0001FAFF☀-➿⬀-⯿⌀-⏿←-⇿㊗㊙©®'
    '‼⁉™ℹⓂ▪-◾⤴⤵〰〽][️⃣‍\U0001F000-\U0001FAFF☀-➿]*'
    '|[0-9#*]️⃣')
found = sorted({m.group(0) for m in emoji_re.finditer(src)} - {'◯', '✦', '・', '→'})
out = ROOT / 'fonts' / 'emoji.ttf'
subprocess.run(['pyftsubset', NOTO, '--text=' + ''.join(found), '--layout-features=*', f'--output-file={out}'], check=True)
print(f'{len(found)} 個の絵文字で {out.relative_to(ROOT)} を作りました（{out.stat().st_size // 1024} KB）')
