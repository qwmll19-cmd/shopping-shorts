#!/usr/bin/env python3
"""watch 가 뽑아둔 레퍼런스 프레임을 번호 박힌 컷 시트로 합친다 (REMIX 1단계).

watch 는 프레임을 폴더에 흩뿌려 놓기만 한다. 낱장으로 읽으면 토큰이 터지고,
그래서 실제로 '자막만 읽고 화면은 안 보는' 사고가 났다. 이 도구로 한 장에 모아 강제로 보게 한다.

  python ref_sheet.py --dir <watch_out_dir>            # 폴더 하나
  python ref_sheet.py --parent <scratch>/dr --glob "r*"  # 여러 개 한꺼번에
"""
import argparse, shutil, subprocess, sys
from pathlib import Path

ROOT = Path(__file__).parent


def _font():
    """자막·시트용 한글 폰트. 없으면 프로젝트 public/fonts 로 폴백."""
    from pathlib import Path as _P
    for c in ("C:/Windows/Fonts/malgunbd.ttf", "C:/Windows/Fonts/malgun.ttf",
              str(_P(__file__).parent / "public/fonts/Jua.ttf")):
        if _P(c).exists():
            return c
    raise SystemExit("한글 폰트를 찾지 못했습니다.")


def sheet(frames_dir: Path, out_png: Path, cols=5, width=200):
    jpgs = sorted(frames_dir.glob("*.jpg"))
    if not jpgs:
        return 0
    tmp = out_png.parent / f"_{out_png.stem}"
    if tmp.exists():
        shutil.rmtree(tmp)
    tmp.mkdir(parents=True)
    for i, f in enumerate(jpgs, 1):
        shutil.copy(f, tmp / f"{i:03d}.jpg")
    shutil.copy(_font(), tmp / "f.ttf")
    rows = -(-len(jpgs) // cols)
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-framerate", "1",
                    "-i", "%03d.jpg", "-vf",
                    (rf"scale={width}:-1,drawtext=fontfile=f.ttf:text='%{{eif\:n+1\:d}}':"
                     "fontcolor=yellow:fontsize=34:box=1:boxcolor=black@0.8:boxborderw=4:x=6:y=6,"
                     f"tile={cols}x{rows}:padding=3:color=0x333333"),
                    "-frames:v", "1", str(out_png.resolve())], check=True, cwd=tmp)
    shutil.rmtree(tmp)
    return len(jpgs)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", help="watch 출력 폴더 하나 (frames/ 를 포함)")
    ap.add_argument("--parent", help="여러 watch 출력이 들어있는 상위 폴더")
    ap.add_argument("--glob", default="*", help="--parent 안에서 고를 패턴")
    ap.add_argument("--out", default="out/refs", help="시트 저장 폴더")
    ap.add_argument("--cols", type=int, default=5)
    a = ap.parse_args()

    targets = []
    if a.dir:
        targets.append(Path(a.dir))
    if a.parent:
        targets += sorted(p for p in Path(a.parent).glob(a.glob) if (p / "frames").is_dir())
    targets = [t for t in targets if (t / "frames").is_dir()]
    if not targets:
        sys.exit("frames/ 를 가진 폴더를 찾지 못했습니다.")

    outdir = ROOT / a.out
    outdir.mkdir(parents=True, exist_ok=True)
    for t in targets:
        png = outdir / f"{t.name}.png"
        n = sheet(t / "frames", png, a.cols)
        print(f"  {t.name:<8} {n:>3}프레임 → {png}")

    print("\n⚠️ 시트를 **전부 열어서 보고** 아래를 표로 적어야 2단계로 넘어간다:")
    print("   컷 순서 · 컷 길이 · 앵글 · 제품 등장 시점 · 사용/결과 장면 · 줌·크롭")
    print("   그리고 **'우리 소재에 없는 컷' 목록**을 뽑아라. 여기서 소재 부족을 잡아야")
    print("   4단계까지 헛돌지 않는다.")


if __name__ == "__main__":
    main()
