#!/usr/bin/env python3
"""ElevenLabs TTS - 텍스트를 mp3로 변환한다. 외부 패키지 불필요(표준 라이브러리만)."""
import argparse, json, os, sys, urllib.error, urllib.request
from pathlib import Path

API = "https://api.elevenlabs.io/v1/text-to-speech"

# ★ 한국어 원어민 보이스 (유료 플랜 필요 — 무료면 402).
#   영어권 보이스가 한국어를 읽으면 어미·받침이 뭉개진다. 한국어 쇼츠는 이 둘만 쓴다.
KR = {
    "여자": "QPFsEL6IBxlT15xfiD6C",
    "남자": "m3gJBS8OofDJfycyA2Ip",
}

# 무료 플랜에서 쓸 수 있는 영어권 보이스 (2026-09-01 실측). 한국어 발음은 어색하다.
VOICES = {
    **KR,
    "Sarah": "EXAVITQu4vr4xnSDxMaL", "Laura": "FGY2WhTYpPnrIDTdsKH5",
    "Alice": "Xb7hH8MSUJpSbSDYk0k2", "Matilda": "XrExE9yKIg1WjnnlVkGX",
    "Jessica": "cgSgspJ2msm6clMCkdW9", "Lily": "pFZP5JQG7iQjIQuC4Bku",
    "River": "SAz9YHcvj6GT2YYXdXww", "George": "JBFqnCBsd6RMkjVDRZzb",
    "Charlie": "IKne3meq5aSn9XLyUdCD", "Callum": "N2lVS1w4EtoT3dr4eOWO",
    "Will": "bIHbv24MWmeRgasZH58o", "Eric": "cjVigY5qzO86Huf0OWal",
    "Chris": "iP95p4xoKVk53GoZ742B", "Brian": "nPczCjzI2devNBz1zQrb",
    "Daniel": "onwK4e9ZLuTAKqWW03F9", "Bill": "pqHfZKP75CvOlQylNhV4",
}


def load_key():
    """.env 를 먼저 읽고, 없으면 환경변수를 쓴다."""
    env = Path(__file__).with_name(".env")
    if env.exists():
        for line in env.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())
    key = os.environ.get("ELEVENLABS_API_KEY")
    if not key:
        sys.exit("ELEVENLABS_API_KEY 가 없습니다. .env 파일을 확인하세요.")
    return key


def synth(text, voice, out, model, stability, similarity, speed):
    vid = VOICES.get(voice, voice)  # 이름이면 변환, 아니면 ID로 취급
    body = json.dumps({
        "text": text,
        "model_id": model,
        "voice_settings": {
            "stability": stability,
            "similarity_boost": similarity,
            "speed": speed,
        },
    }).encode("utf-8")
    req = urllib.request.Request(
        f"{API}/{vid}",
        data=body,
        headers={
            "xi-api-key": load_key(),
            "Content-Type": "application/json; charset=utf-8",
            "Accept": "audio/mpeg",
        },
    )
    try:
        with urllib.request.urlopen(req) as r:
            audio = r.read()
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "replace")
        try:
            detail = json.loads(detail)["detail"]["message"]
        except Exception:
            pass
        sys.exit(f"실패 (HTTP {e.code}): {detail}")

    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(audio)
    print(f"생성 완료: {out}  ({len(audio):,} bytes, {len(text)} chars 소모)")


def main():
    p = argparse.ArgumentParser(description="ElevenLabs 텍스트 → mp3")
    p.add_argument("text", nargs="?", help="읽을 텍스트")
    p.add_argument("-f", "--file", help="텍스트 파일 경로 (UTF-8)")
    p.add_argument("-v", "--voice", default="Sarah", help="보이스 이름 또는 ID")
    p.add_argument("-o", "--out", default="out/narration.mp3", help="저장 경로")
    p.add_argument("-m", "--model", default="eleven_multilingual_v2",
                   help="모델 ID (한국어는 multilingual 계열)")
    p.add_argument("--stability", type=float, default=0.5)
    p.add_argument("--similarity", type=float, default=0.75)
    p.add_argument("--speed", type=float, default=1.0, help="0.7~1.2")
    p.add_argument("--list", action="store_true", help="사용 가능한 보이스 출력")
    a = p.parse_args()

    if a.list:
        for n, i in VOICES.items():
            print(f"{n:<9} {i}")
        return

    text = Path(a.file).read_text(encoding="utf-8") if a.file else a.text
    if not text:
        p.error("텍스트나 --file 중 하나는 필요합니다.")
    synth(text.strip(), a.voice, a.out, a.model, a.stability, a.similarity, a.speed)


if __name__ == "__main__":
    main()
