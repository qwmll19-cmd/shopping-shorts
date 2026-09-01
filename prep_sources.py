#!/usr/bin/env python3
"""소재를 1080x1920 로 미리 구워둔다 (REMIX 2단계).

브라우저(Remotion)가 확대하게 두면 흐려진다. 9:16 이 아닌 소재는 여기서
lanczos 로 확대하고 언샤프로 윤곽을 살려 네이티브 해상도로 만든다.
원본에 박힌 자막도 여기서 잘라낸다.

  python prep_sources.py --dir raw                     # 전부 9:16 으로
  python prep_sources.py raw/<파일>.mp4 --keep-top 1070  # 하단 자막 제거하며
"""
import argparse, json, subprocess, sys
from pathlib import Path

ROOT = Path(__file__).parent
W, H = 1080, 1920


def _font():
    """자막·시트용 한글 폰트. 없으면 프로젝트 public/fonts 로 폴백."""
    from pathlib import Path as _P
    for c in ("C:/Windows/Fonts/malgunbd.ttf", "C:/Windows/Fonts/malgun.ttf",
              str(_P(__file__).parent / "public/fonts/Jua.ttf")):
        if _P(c).exists():
            return c
    raise SystemExit("한글 폰트를 찾지 못했습니다.")


def probe(p):
    r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0",
                        "-show_entries", "stream=width,height",
                        "-show_entries", "format=duration",
                        "-of", "json", str(p)], capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    d = json.loads(r.stdout)
    s = d["streams"][0]
    return int(s["width"]), int(s["height"]), float(d["format"]["duration"])


def build(src, dst, keep_top=None, sharpen=0.9):
    w, h, dur = probe(src)
    use_h = keep_top or h
    # 잘라낸 영역을 9:16 에 꽉 채우려면 얼마나 키워야 하는지
    scale = max(W / w, H / use_h)
    sw, sh = round(w * scale), round(H if scale * use_h >= H else scale * use_h)
    sw = sw + (sw % 2)          # libx264 는 짝수 필요
    off = max(0, (sw - W) // 2)

    vf = []
    if keep_top and keep_top < h:
        vf.append(f"crop={w}:{keep_top}:0:0")
    vf.append(f"scale={sw}:{H}:flags=lanczos")
    vf.append(f"crop={W}:{H}:{off}:0")
    if sharpen > 0:
        vf.append(f"unsharp=5:5:{sharpen}:5:5:0.0")

    dst.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(src),
                    "-vf", ",".join(vf), "-c:v", "libx264", "-preset", "slow",
                    "-crf", "15", "-pix_fmt", "yuv420p", "-an", str(dst)], check=True)
    nw, nh, ndur = probe(dst)
    note = f"확대 {scale:.2f}배" + (f" / 하단 {h-keep_top}px 잘라냄" if keep_top and keep_top < h else "")
    print(f"  {src.name:<16} {w}x{h} → {nw}x{nh}  {ndur:.1f}초   {note}")

    if keep_top and keep_top < h:
        # 자막을 제대로 걷어냈는지 눈으로 확인할 시트를 강제로 뽑는다.
        # keep_top 은 손으로 넣는 값이라 실측이 빗나가면 잔상이 남는다.
        chk = ROOT / "out" / "prep_check"
        chk.mkdir(parents=True, exist_ok=True)
        for i in range(6):
            t = ndur * (i + 0.5) / 6
            subprocess.run(["ffmpeg", "-y", "-v", "error", "-ss", f"{t:.2f}", "-i", str(dst),
                            "-frames:v", "1", "-vf", "crop=1080:300:0:1620,scale=360:-1",
                            str(chk / f"{dst.stem}_{i+1}.jpg")], check=True)
        sheet = chk / f"{dst.stem}_sheet.png"
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-framerate", "1",
                        "-i", str(chk / f"{dst.stem}_%d.jpg"),
                        "-vf", "tile=1x6:padding=3:color=0x444444",
                        "-frames:v", "1", str(sheet)], check=True)
        print(f"      ⚠️ 자막 제거 확인 필수 → {sheet}")
        print(f"         잔상이 보이면 --keep-top 을 더 줄여서 다시 돌려라")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("files", nargs="*")
    ap.add_argument("--dir", help="폴더 전체 처리")
    ap.add_argument("--out", default="sources", help="출력 폴더")
    ap.add_argument("--keep-top", type=int,
                    help="원본에서 위쪽 몇 px 만 남길지 (하단 자막 제거용)")
    ap.add_argument("--sharpen", type=float, default=0.9)
    a = ap.parse_args()

    srcs = [Path(f) for f in a.files]
    if a.dir:
        srcs += sorted(p for p in Path(a.dir).iterdir()
                       if p.suffix.lower() in (".mp4", ".mov", ".mkv", ".webm", ".avi"))
    srcs = [p for p in srcs if p.exists()]
    if not srcs:
        sys.exit("처리할 영상이 없습니다.")

    print(f"소재 전처리 → {W}x{H}")
    for s in srcs:
        build(s, ROOT / a.out / f"{s.stem}.mp4", a.keep_top, a.sharpen)
    print(f"\n완료. 다음: python index_sources.py --dir {a.out}")


if __name__ == "__main__":
    main()
