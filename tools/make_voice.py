"""ゲームの声（voice/*.mp3 と voice/index.json）を作る。

Style-Bert-VITS2 の「小春音アミ」モデル（あみたろの声素材工房の声をもとにしたモデル）で、
tools/voice_lines.js が出す声の部品をひとつずつ mp3 にする。前に作った部品は作り直さない。

準備（はじめの1回だけ。Hugging Face からモデルを取ってくるので、ネットにつながっていること）:
    python3 -m venv .venv-voice
    CMAKE_POLICY_VERSION_MINIMUM=3.5 .venv-voice/bin/pip install style-bert-vits2==2.5.0 soundfile "setuptools<81"
使い方:
    npm install
    .venv-voice/bin/python tools/make_voice.py [--workers 4] [--pick 4]
ffmpeg が必要（mp3 にするため）。

--pick N をつけると、1つのセリフにつき N とおりの声を作り、音声認識（faster-whisper）で聞きとって、
セリフどおりに いちばん はっきり聞こえた声を選ぶ（.venv-voice/bin/pip install faster-whisper が必要）。

モデルの利用規約: https://huggingface.co/litagin/sbv2_koharune_ami
（生成した声を公開するときは、あみたろの声素材工房 https://amitaro.net/ のクレジットを書くこと）
"""
import argparse
import hashlib
import json
import multiprocessing as mp
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / 'voice'
INDEX = OUT / 'index.json'
CAND = ROOT / 'voice-candidates'
MODEL_REPO = 'litagin/sbv2_koharune_ami'
BERT = 'ku-nlp/deberta-v2-large-japanese-char-wwm'
# 声のつくり方を変えたら、この番号を上げると全部作り直す
RECIPE = 'koharune-ami/2'

_model = None


def file_name(item):
    h = hashlib.sha1(f"{RECIPE}|{item['style']}|{item['text']}".encode('utf-8')).hexdigest()[:12]
    return f'{h}.mp3'


def init_worker():
    global _model
    import torch
    torch.set_num_threads(1)
    from huggingface_hub import hf_hub_download
    from style_bert_vits2.constants import Languages
    from style_bert_vits2.nlp import bert_models
    from style_bert_vits2.tts_model import TTSModel
    files = {k: hf_hub_download(MODEL_REPO, f'koharune-ami/{k}') for k in ['config.json', 'koharune-ami.safetensors', 'style_vectors.npy']}
    # 新しい transformers は半精度で読みこむことがあり、そのままだと型が合わずに止まるので float32 にする
    bert_models.load_model(Languages.JP, BERT).float()
    bert_models.load_tokenizer(Languages.JP, BERT)
    _model = TTSModel(model_path=files['koharune-ami.safetensors'], config_path=files['config.json'],
                      style_vec_path=files['style_vectors.npy'], device='cpu')
    _model.load()


def to_mp3(audio, sr, path):
    import numpy as np
    import soundfile as sf
    import io
    a = audio.astype(np.float32)
    if audio.dtype.kind == 'i':
        a = a / 32768.0
    # 前後の無音を切る（つなげて流したときに間があきすぎないように）
    thr = 0.02 * np.abs(a).max()
    idx = np.where(np.abs(a) > thr)[0]
    if len(idx):
        pad = int(sr * .04)
        a = a[max(0, idx[0] - pad): idx[-1] + pad]
    # 音量をそろえる
    a = a / max(np.abs(a).max(), 1e-6) * 0.89
    buf = io.BytesIO()
    sf.write(buf, a, sr, format='WAV', subtype='PCM_16')
    subprocess.run(['ffmpeg', '-loglevel', 'error', '-y', '-i', 'pipe:0', '-ac', '1', '-ar', '24000', '-b:a', '48k', str(path)],
                   input=buf.getvalue(), check=True)


# 声の作りかたの候補（スタイル、ゆっくりさ、抑揚、乱数）。--pick のときは前から N とおり作る
VARIANTS = [
    dict(style='るんるん', length=1.08, intonation=1.0, seed=1),
    dict(style='ノーマル', length=1.08, intonation=1.1, seed=2),
    dict(style='るんるん', length=1.15, intonation=1.1, seed=3),
    dict(style='Neutral', length=1.1, intonation=1.15, seed=4),
    dict(style='るんるん', length=1.0, intonation=1.0, seed=5),
    dict(style='ノーマル', length=1.15, intonation=1.0, seed=6),
]


def work(job):
    import torch
    item, k, path = job
    v = VARIANTS[k]
    torch.manual_seed(v['seed'])
    sr, audio = _model.infer(text=item['text'], style=v['style'], style_weight=1.0, length=v['length'], intonation_scale=v['intonation'])
    to_mp3(audio, sr, path)
    return item['key']


def yomi(s):
    """くらべるための読み（カタカナ）"""
    import re
    import pyopenjtalk
    s = re.sub(r'[、。！？!?・\s　「」]', '', s)
    return pyopenjtalk.g2p(s, kana=True).replace('ヲ', 'オ').replace('、', '').replace('ー', '')


def pick_best(todo, n):
    """候補を音声認識で聞きとって、セリフに いちばん近いものを選ぶ"""
    import difflib
    import shutil
    import numpy as np
    from faster_whisper import WhisperModel
    model = WhisperModel('small', device='cpu', compute_type='int8')
    report = []
    for item in todo:
        want = yomi(item['text'])
        best = None
        for k in range(n):
            path = CAND / f"{item['file']}.{k}.mp3"
            pcm = subprocess.run(['ffmpeg', '-loglevel', 'error', '-i', str(path), '-f', 'f32le', '-ac', '1', '-ar', '16000', '-'], capture_output=True).stdout
            segs, _ = model.transcribe(np.frombuffer(pcm, dtype=np.float32), language='ja', beam_size=5)
            heard = ''.join(sg.text for sg in segs)
            score = difflib.SequenceMatcher(None, want, yomi(heard)).ratio()
            if best is None or score > best[0] + 1e-9:
                best = (score, k, heard)
        shutil.copy(CAND / f"{item['file']}.{best[1]}.mp3", OUT / item['file'])
        report.append((best[0], item['key'], best[2], best[1]))
    for score, key, heard, k in sorted(report):
        print(f"  {'△' if score < .8 else '○'} {score:.2f}  {key}  →  {heard}（候補{k + 1}）")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--workers', type=int, default=max(1, (os.cpu_count() or 2)))
    ap.add_argument('--limit', type=int, default=0, help='試しに作る数（0 ならぜんぶ）')
    ap.add_argument('--pick', type=int, default=1, help='1つのセリフにつき何とおり作って選ぶか（2 以上は faster-whisper が必要）')
    args = ap.parse_args()

    lines = json.loads(subprocess.run(['node', str(ROOT / 'tools' / 'voice_lines.js')], check=True, capture_output=True).stdout)
    OUT.mkdir(exist_ok=True)
    for item in lines:
        item['file'] = file_name(item)
    todo = [it for it in lines if not (OUT / it['file']).exists()]
    if args.limit:
        todo = todo[:args.limit]
    print(f'部品 {len(lines)} 個のうち、これから {len(todo)} 個つくります', flush=True)

    t0 = time.time()
    n = max(1, min(args.pick, len(VARIANTS)))
    if todo:
        CAND.mkdir(exist_ok=True)
        jobs = [(it, k, (CAND / f"{it['file']}.{k}.mp3") if n > 1 else OUT / it['file']) for it in todo for k in range(n)]
        with mp.get_context('spawn').Pool(args.workers, initializer=init_worker) as pool:
            for i, _ in enumerate(pool.imap_unordered(work, jobs, chunksize=2), 1):
                if i % 50 == 0 or i == len(jobs):
                    el = time.time() - t0
                    print(f'  {i}/{len(jobs)}  {el:.0f}秒（のこり およそ {el / i * (len(jobs) - i) / 60:.1f}分）', flush=True)
        if n > 1:
            print('音声認識で、いちばん はっきり聞こえる声を選びます', flush=True)
            pick_best(todo, n)
        import shutil
        shutil.rmtree(CAND, ignore_errors=True)

    # 使っている部品だけを表にのせ、使わなくなったファイルは消す
    clips = {it['key']: it['file'] for it in lines if (OUT / it['file']).exists()}
    used = set(clips.values())
    for f in OUT.glob('*.mp3'):
        if f.name not in used:
            f.unlink()
    INDEX.write_text(json.dumps({
        'credit': 'Style-Bert-VITS2 モデル「小春音アミ」、あみたろの声素材工房 (https://amitaro.net/)',
        'recipe': RECIPE,
        'clips': dict(sorted(clips.items())),
    }, ensure_ascii=False, indent=0), encoding='utf-8')
    size = sum(f.stat().st_size for f in OUT.glob('*.mp3'))
    print(f'voice/index.json に {len(clips)} 個をのせました（mp3 ぜんぶで {size / 1e6:.1f} MB）')


if __name__ == '__main__':
    sys.exit(main())
