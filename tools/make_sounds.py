"""ゲームの効果音（sounds/*.mp3）を作る。

踏切・電車・駅の音を、録音を使わずに数式で作る（ブラウザでその場で作るより、音を重ねたり
響きをつけたりして、ていねいに作れる）。作り直すたびに同じ音になる。
使い方（numpy と soundfile が入っている Python で。声を作る .venv-voice でよい）:
    .venv-voice/bin/python tools/make_sounds.py
ffmpeg が必要（mp3 にするため）。
"""
import io
import subprocess
from pathlib import Path

import numpy as np
import soundfile as sf

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / 'sounds'
SR = 44100
rng = np.random.default_rng(7)


def t_axis(dur):
    return np.arange(int(SR * dur)) / SR


def env_exp(t, tau, attack=.002):
    """すっと立ち上がって、指数で消える"""
    a = np.clip(t / attack, 0, 1) if attack > 0 else 1
    return a * np.exp(-t / tau)


def noise(n):
    return rng.standard_normal(n)


def bandpass(x, lo, hi):
    """FFT で、lo〜hi Hz だけを通す（はしは なだらかに）"""
    n = len(x)
    X = np.fft.rfft(x)
    f = np.fft.rfftfreq(n, 1 / SR)
    w = np.ones_like(f)
    if lo > 0:
        w *= 1 / (1 + (lo / np.maximum(f, 1)) ** 4)
    if hi:
        w *= 1 / (1 + (f / hi) ** 4)
    return np.fft.irfft(X * w, n)


def lowpass(x, hi):
    return bandpass(x, 0, hi)


def reverb(x, size=.35, mix=.18, pre=.012):
    """外の、すこしひらけた場所のひびき（ノイズの残響をたたみこむ）"""
    x = fade_tail(x, 60)  # 元の音の終わりで ぷつっと切れないように
    n = int(SR * size)
    t = np.arange(n) / SR
    ir = noise(n) * np.exp(-t / (size / 5))
    ir = lowpass(ir, 6000)
    ir[: int(SR * pre)] = 0
    ir /= np.sqrt(np.sum(ir ** 2))
    wet = np.fft.irfft(np.fft.rfft(x, len(x) + n) * np.fft.rfft(ir, len(x) + n), len(x) + n)
    out = np.concatenate([x, np.zeros(n)]) * (1 - mix) + wet * mix
    return out


def fade_tail(x, ms=30):
    n = int(SR * ms / 1000)
    x = x.copy()
    x[-n:] *= np.linspace(1, 0, n)
    return x


def save(name, x, peak=.89):
    x = np.asarray(x, dtype=np.float64)
    x = x / max(np.abs(x).max(), 1e-9) * peak
    x = fade_tail(x)
    buf = io.BytesIO()
    sf.write(buf, x.astype(np.float32), SR, format='WAV', subtype='PCM_16')
    OUT.mkdir(exist_ok=True)
    subprocess.run(['ffmpeg', '-loglevel', 'error', '-y', '-i', 'pipe:0', '-ac', '1', '-ar', '44100', '-b:a', '96k',
                    str(OUT / f'{name}.mp3')], input=buf.getvalue(), check=True)
    return len(x) / SR


# ---------- 踏切の「カーン」 ----------
def bell():
    """電子音の踏切警報機。金属っぽい倍音を重ねて、高い音から先に消える"""
    t = t_axis(1.0)
    f0 = 760.0
    parts = [(1.0, 1.0, .22), (2.0, .32, .12), (2.76, .5, .10), (3.0, .25, .09), (4.07, .22, .07), (5.4, .14, .05), (6.8, .08, .035)]
    x = np.zeros_like(t)
    for ratio, amp, tau in parts:
        ph = rng.uniform(0, 2 * np.pi)
        x += amp * np.sin(2 * np.pi * f0 * ratio * t + ph) * env_exp(t, tau, .0015)
    # 電子音らしい、すこし角ばった音（基音の奇数倍音）
    for k in (3, 5, 7):
        x += .2 / k * np.sin(2 * np.pi * f0 * k * t) * env_exp(t, .06, .001)
    # たたいた瞬間の「カッ」
    click = bandpass(noise(len(t)), 2000, 8000) * env_exp(t, .004, .0003) * .5
    x += click
    return reverb(x, .5, .16)


# ---------- 警笛「ファーン」 ----------
def horn(dur=1.05):
    t = t_axis(dur)
    x = np.zeros_like(t)
    for f, amp in ((370.0, 1.0), (466.2, .85)):
        # 鳴りはじめは すこし低くて、すぐ正しい高さになる。かすかに ゆれる
        bend = 1 - .035 * np.exp(-t / .03)
        vib = 1 + .003 * np.sin(2 * np.pi * 5.3 * t)
        ph = 2 * np.pi * np.cumsum(f * bend * vib) / SR
        for k in range(1, 14):
            x += amp * (1 / k ** 1.1) * np.sin(k * ph)
    x = lowpass(x, 2600)
    x += bandpass(noise(len(t)), 800, 3000) * .05
    a = np.clip(t / .05, 0, 1) * np.clip((dur - t) / .14, 0, 1)
    x *= a
    return reverb(x, .9, .22, .03)


# ---------- 線路のつなぎめ「ガタン」（車輪ひとつぶん） ----------
def joint():
    t = t_axis(.45)
    thump = np.sin(2 * np.pi * (62 + 30 * np.exp(-t / .02)) * t) * env_exp(t, .07, .002)
    knock = np.sin(2 * np.pi * 260 * t) * env_exp(t, .035, .001) * .45
    ring = bandpass(noise(len(t)), 1800, 5200) * env_exp(t, .012, .0005) * .35
    rattle = bandpass(noise(len(t)), 300, 1200) * env_exp(t, .05, .002) * .25
    return reverb(thump + knock + ring + rattle, .3, .1)


# ---------- ブレーキの空気「ぷしゅー」と、止まる直前の「キーッ」 ----------
def air():
    t = t_axis(1.3)
    x = bandpass(noise(len(t)), 2500, 7500) * np.clip(t / .03, 0, 1) * np.exp(-t / .38)
    x += bandpass(noise(len(t)), 600, 1500) * np.clip(t / .02, 0, 1) * np.exp(-t / .12) * .4
    return reverb(x, .4, .12)


def squeal():
    t = t_axis(.7)
    f = 3150 + 40 * np.sin(2 * np.pi * 9 * t) + rng.normal(0, 8, len(t)).cumsum() * .02
    x = np.sin(2 * np.pi * np.cumsum(f) / SR) + .3 * np.sin(2 * np.pi * np.cumsum(f * 2.01) / SR)
    x *= np.clip(t / .08, 0, 1) * np.clip((.7 - t) / .25, 0, 1) * .5
    return reverb(x, .4, .15)


# ---------- ドア ----------
def door(close):
    dur = 1.1
    t = t_axis(dur)
    hiss = bandpass(noise(len(t)), 1800, 6000) * np.clip(t / .02, 0, 1) * np.exp(-t / .16) * .6
    run = bandpass(noise(len(t)), 120, 500) * np.clip(t / .05, 0, 1) * np.clip((.75 - t) / .1, 0, 1) * .5
    x = hiss + run
    if close:
        # しまったときの「とん」
        k = int(SR * .72)
        tt = t[: len(t) - k]
        x[k:] += (np.sin(2 * np.pi * 95 * tt) * env_exp(tt, .06, .001) * 1.2 + bandpass(noise(len(tt)), 400, 2500) * env_exp(tt, .02, .0005) * .5)
    return reverb(x, .35, .12)


def chime():
    """ドアの「ピンポーン」"""
    t = t_axis(1.2)
    x = np.zeros_like(t)
    for start, f in ((0, 1318.5), (.24, 1046.5)):
        tt = np.clip(t - start, 0, None)
        on = t >= start
        for ratio, amp, tau in ((1, 1, .5), (2, .2, .2), (3.01, .08, .1)):
            x += on * amp * np.sin(2 * np.pi * f * ratio * tt) * env_exp(tt, tau, .003)
    return reverb(x, .6, .2)


# ---------- 発車ベル（オリジナルの短いメロディ）と、車掌さんの笛 ----------
def depart():
    notes = [784, 1047, 1319, 1568, 1319, 1047, 1175, 784, 1047, 1319, 1568, 2093]
    step = .19
    t = t_axis(step * len(notes) + 2.6)
    x = np.zeros_like(t)
    for i, f in enumerate(notes):
        st = i * step
        tt = np.clip(t - st, 0, None)
        on = t >= st
        last = i == len(notes) - 1
        for ratio, amp, tau in ((1, 1, .6 if last else .3), (2.0, .25, .15), (3.98, .12, .05)):
            x += on * amp * np.sin(2 * np.pi * f * ratio * tt) * env_exp(tt, tau, .002)
    return reverb(x, 1.0, .25)


def whistle():
    t = t_axis(.95)
    trill = 1 + .5 * (np.sin(2 * np.pi * 26 * t) > 0)
    f = 2850 * (1 + .012 * np.sin(2 * np.pi * 26 * t))
    x = np.sin(2 * np.pi * np.cumsum(f) / SR) * (.6 + .4 * (trill - 1))
    x += bandpass(noise(len(t)), 2000, 5000) * .25
    x *= np.clip(t / .03, 0, 1) * np.clip((.9 - t) / .06, 0, 1)
    return reverb(x, .6, .2)


# ---------- くるまの「ぷっぷー」 ----------
def carhorn():
    t = t_axis(.75)
    gate = ((t > 0) & (t < .13)) | ((t > .22) & (t < .62))
    g = np.convolve(gate.astype(float), np.ones(220) / 220, mode='same')
    x = np.zeros_like(t)
    for f in (415.0, 523.0):
        for k in range(1, 10):
            x += (1 / k) * np.sin(2 * np.pi * f * k * t)
    return reverb(lowpass(x, 2200) * g, .35, .12)


# ---------- 遮断機の「ういーん」 ----------
def gate():
    t = t_axis(2.0)
    f = 110 + 25 * t
    x = sum((1 / k) * np.sin(2 * np.pi * np.cumsum(f * k) / SR) for k in range(1, 8))
    x = lowpass(x, 900) * np.clip(t / .2, 0, 1) * np.clip((2 - t) / .3, 0, 1)
    return x


SOUNDS = {
    'bell': bell, 'horn': horn, 'joint': joint, 'air': air, 'squeal': squeal,
    'door_open': lambda: door(False), 'door_close': lambda: door(True), 'chime': chime,
    'depart': depart, 'whistle': whistle, 'carhorn': carhorn, 'gate': gate,
}

if __name__ == '__main__':
    for name, fn in SOUNDS.items():
        d = save(name, fn())
        print(f'sounds/{name}.mp3  {d:.2f}秒')
