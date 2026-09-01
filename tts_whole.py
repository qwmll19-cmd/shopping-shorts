#!/usr/bin/env python3
"""대본 전체를 **한 번의 호출로** 읽히고, 문자 타임스탬프로 문장 경계를 뽑는다.

문장마다 따로 TTS 를 부르면 ElevenLabs 가 각각을 독립된 발화로 처리한다.
그래서 문장마다 억양이 처음부터 시작해 끝에서 떨어지고, 이어붙이면
"영혼 없는 토막"처럼 들린다. 한 번에 읽히면 억양이 문장을 넘어 이어진다.
"""
import base64, json, subprocess, sys, urllib.error, urllib.request
from pathlib import Path

ROOT = Path(__file__).parent
API = "https://api.elevenlabs.io/v1/text-to-speech"


def _key():
    env = ROOT / ".env"
    for line in env.read_text(encoding="utf-8").splitlines():
        if line.startswith("ELEVENLABS_API_KEY="):
            return line.split("=", 1)[1].strip()
    sys.exit(".env 에 ELEVENLABS_API_KEY 가 없습니다.")


def repair_times(st, en):
    """ElevenLabs 가 가끔 거꾸로 가는 타임스탬프를 돌려준다.

    실제로 '요' 의 끝이 시작보다 0.9초 앞이라, 문장이 1초 일찍 끝난 것으로
    계산돼 자막이 음성보다 먼저 넘어갔다. 단조 증가하도록 고친다.
    깨진 구간은 앞뒤의 성한 값 사이에 균등 분배한다.
    """
    st, en = list(st), list(en)
    n = len(st)
    good, prev = [False] * n, 0.0
    for i in range(n):
        if st[i] >= prev - 1e-6 and en[i] >= st[i] - 1e-6:
            good[i], prev = True, en[i]
    i = 0
    while i < n:
        if good[i]:
            i += 1
            continue
        j = i
        while j < n and not good[j]:
            j += 1
        lo = en[i - 1] if i > 0 else 0.0
        hi = st[j] if j < n else lo + (j - i) * 0.06
        step = (hi - lo) / (j - i)
        for k in range(i, j):
            st[k], en[k] = lo + step * (k - i), lo + step * (k - i + 1)
        i = j
    return st, en


def synth_whole(texts, voice_id, out_mp3, model="eleven_multilingual_v2",
                speed=1.0, stability=0.5, similarity=0.75, style=0.0, joiner=" "):
    """문장 리스트를 한 번에 읽히고 (mp3 경로, 문장별 [시작,끝]) 을 돌려준다."""
    full = joiner.join(texts)
    body = json.dumps({
        "text": full, "model_id": model,
        "voice_settings": {"stability": stability, "similarity_boost": similarity,
                           "style": style, "speed": min(speed, 1.2)},
    }).encode("utf-8")
    req = urllib.request.Request(f"{API}/{voice_id}/with-timestamps", data=body,
                                 headers={"xi-api-key": _key(),
                                          "Content-Type": "application/json; charset=utf-8"})
    try:
        with urllib.request.urlopen(req) as r:
            d = json.loads(r.read())
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "replace")
        try:
            detail = json.loads(detail)["detail"]["message"]
        except Exception:
            pass
        sys.exit(f"TTS 실패 (HTTP {e.code}): {detail}")

    out_mp3 = Path(out_mp3)
    out_mp3.parent.mkdir(parents=True, exist_ok=True)
    out_mp3.write_bytes(base64.b64decode(d["audio_base64"]))

    al = d.get("alignment") or d["normalized_alignment"]
    chars = al["characters"]
    st = al["character_start_times_seconds"]
    en = al["character_end_times_seconds"]
    st, en = repair_times(st, en)          # 거꾸로 가는 값을 먼저 고친다

    # 원문에서 각 문장이 차지하는 문자 구간 → 시간 구간
    spans, pos = [], 0
    for t in texts:
        i = full.index(t, pos)
        j = i + len(t)
        pos = j
        i = min(i, len(st) - 1); j = min(j, len(en))
        spans.append((round(st[i], 3), round(en[j - 1], 3)))
    # 글자 단위 시각도 함께 돌려준다. 자막 조각을 글자수 비례로 추정하면
    # 문장 뒤쪽 조각이 밀린다 — 실제 글자 시각으로 찍어야 정확하다.
    chars = [(c, round(a, 3), round(b, 3)) for c, a, b in zip(chars, st, en)]
    return out_mp3, spans, chars


def stretch(src, dst, factor):
    """ElevenLabs 는 speed 1.2 가 상한이라 그 이상은 ffmpeg 로 더 올린다(음정 유지)."""
    if factor <= 1.001:
        Path(src).replace(dst); return
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(src),
                    "-filter:a", f"atempo={factor:.4f}",
                    "-c:a", "libmp3lame", "-q:a", "3", str(dst)], check=True)
    Path(src).unlink()


def compress_silence(src, dst, spans, max_gap=0.32, thresh_db=-42, sr=16000):
    """문장 사이 긴 침묵을 잘라내고, 문장 타임스탬프를 그만큼 보정한다.

    한국어 나레이션의 쉼은 레퍼런스 실측 기준 평균 0.30초·최대 0.60초다.
    TTS 는 1초가 넘는 침묵을 만들기도 하는데, 그러면 문장이 끊긴 것처럼 들린다.
    무음만 줄이므로 억양·발음에는 영향이 없다.
    """
    import wave, struct, math, subprocess, tempfile, os
    tmp = Path(tempfile.gettempdir()) / "_sil.wav"
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(src),
                    "-ac", "1", "-ar", str(sr), str(tmp)], check=True)
    with wave.open(str(tmp), "rb") as f:
        n = f.getnframes()
        a = list(struct.unpack(f"<{n}h", f.readframes(n)))

    H = int(sr * 0.01)                       # 10ms 단위로 판정
    lvl = []
    for s in range(0, len(a) - H, H):
        fr = a[s:s+H]
        r = math.sqrt(sum(x*x for x in fr)/H) + 1e-9
        lvl.append(20*math.log10(r/32768))

    keep, cuts, i = [], [], 0                # cuts: (샘플위치, 잘라낸 샘플수)
    while i < len(lvl):
        if lvl[i] < thresh_db:
            j = i
            while j < len(lvl) and lvl[j] < thresh_db:
                j += 1
            gap = (j - i) * 0.01
            if gap > max_gap:
                keep_n = int(max_gap * sr)
                keep.append((i*H, i*H + keep_n))
                cuts.append((i*H, (j-i)*H - keep_n))
            else:
                keep.append((i*H, j*H))
            i = j
        else:
            j = i
            while j < len(lvl) and lvl[j] >= thresh_db:
                j += 1
            keep.append((i*H, j*H))
            i = j

    out = []
    for s, e in keep:
        out.extend(a[s:e])
    with wave.open(str(tmp), "wb") as f:
        f.setnchannels(1); f.setsampwidth(2); f.setframerate(sr)
        f.writeframes(struct.pack(f"<{len(out)}h", *out))
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(tmp),
                    "-c:a", "libmp3lame", "-q:a", "3", str(dst)], check=True)
    os.remove(tmp)

    def shift(t):
        removed = sum(c for pos, c in cuts if pos < t*sr)
        return max(0.0, t - removed/sr)
    return ([[round(shift(a0), 3), round(shift(b0), 3)] for a0, b0 in spans],
            shift)
