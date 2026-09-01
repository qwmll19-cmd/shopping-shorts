#!/usr/bin/env python3
"""소재를 장면 단위로 인덱싱하고 번호 박힌 스토리보드 시트를 만든다 (REMIX 3단계).

장면전환 검출만 쓰면 롱테이크에서 프레임이 한두 장밖에 안 나온다.
컷을 고르려면 **컷 수보다 넉넉한 후보**가 필요하므로 최소 장수를 보장한다.

  기본 규칙: max(소재 총길이 × 1장/초, 목표 컷수 × 1.5)

  python index_sources.py --dir sources --cuts 20
  python index_sources.py --dir sources --min-shots 30
"""
import argparse, json, math, re, shutil, subprocess, sys
from pathlib import Path

ROOT = Path(__file__).parent
OUT = ROOT / "out"


def _font():
    """자막·시트용 한글 폰트. 없으면 프로젝트 public/fonts 로 폴백."""
    from pathlib import Path as _P
    for c in ("C:/Windows/Fonts/malgunbd.ttf", "C:/Windows/Fonts/malgun.ttf",
              str(_P(__file__).parent / "public/fonts/Jua.ttf")):
        if _P(c).exists():
            return c
    raise SystemExit("한글 폰트를 찾지 못했습니다.")


def probe(p):
    r = subprocess.run(["ffprobe", "-v", "quiet", "-show_entries", "format=duration",
                        "-of", "csv=p=0", str(p)], capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    return float(r.stdout.strip())


def cut_points(p, thresh):
    r = subprocess.run(
        ["ffmpeg", "-v", "info", "-i", str(p), "-vf",
         f"select='gt(scene,{thresh})',metadata=print:file=-", "-an", "-f", "null", "-"],
        capture_output=True, text=True, encoding="utf-8", errors="replace")
    return sorted({round(float(m), 2)
                   for m in re.findall(r"pts_time:([0-9.]+)", r.stdout + r.stderr)})


def segments(path, thresh, want):
    """장면전환으로 나누되, want 개에 못 미치면 긴 구간을 반으로 쪼개 채운다."""
    total = probe(path)
    marks = [0.0] + [t for t in cut_points(path, thresh) if 0.3 < t < total - 0.3] + [total]
    segs = [[s, e] for s, e in zip(marks, marks[1:]) if e - s > 0.25]
    while len(segs) < want:
        i = max(range(len(segs)), key=lambda k: segs[k][1] - segs[k][0])
        s, e = segs[i]
        if e - s < 0.7:          # 더 쪼개면 의미 없는 길이
            break
        segs[i:i + 1] = [[s, (s + e) / 2], [(s + e) / 2, e]]
    return total, [{"start": round(s, 2), "end": round(e, 2), "dur": round(e - s, 2),
                    "label": ""} for s, e in segs]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default="sources")
    ap.add_argument("--out", default="out/scene_index.json")
    ap.add_argument("--cuts", type=int, default=20, help="목표 컷 수")
    ap.add_argument("--min-shots", type=int, help="최소 후보 프레임 수 (지정하면 규칙 대신 이 값)")
    ap.add_argument("--thresh", type=float, default=0.25)
    ap.add_argument("--cols", type=int, default=6)
    a = ap.parse_args()

    vids = sorted(p for p in (ROOT / a.dir).iterdir()
                  if p.suffix.lower() in (".mp4", ".mov", ".mkv", ".webm", ".avi"))
    if not vids:
        sys.exit(f"{a.dir} 에 영상이 없습니다. 먼저 prep_sources.py 로 전처리하세요.")

    durs = {p: probe(p) for p in vids}
    total_dur = sum(durs.values())
    want = a.min_shots or max(math.ceil(total_dur), math.ceil(a.cuts * 1.5))
    print(f"소재 {len(vids)}개 / 총 {total_dur:.1f}초 / 목표 컷 {a.cuts}개 "
          f"→ 후보 프레임 {want}장 확보")

    thumbs = OUT / "scene_thumbs"
    if thumbs.exists():
        shutil.rmtree(thumbs)
    thumbs.mkdir(parents=True)
    shutil.copy(_font(), thumbs / "f.ttf")

    index, n = {}, 1
    for p in vids:
        share = max(2, round(want * durs[p] / total_dur))
        total, segs = segments(p, a.thresh, share)
        for s in segs:
            mid = (s["start"] + s["end"]) / 2
            jpg = thumbs / f"{n:03d}.jpg"
            subprocess.run(["ffmpeg", "-y", "-v", "error", "-ss", f"{mid:.2f}",
                            "-i", str(p), "-frames:v", "1", "-vf", "scale=240:-1",
                            str(jpg)], check=True)
            s["n"], s["src"], s["thumb"] = n, p.name, jpg.name
            n += 1
        index[p.name] = {"duration": round(total, 2), "scenes": segs}
        print(f"  {p.name:<16} {total:5.1f}초 → {len(segs):3d}장")

    shots = n - 1
    rows = -(-shots // a.cols)
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-framerate", "1",
                    "-i", str(thumbs / "%03d.jpg"), "-vf",
                    ("drawtext=fontfile=out/scene_thumbs/f.ttf:"
                     r"text='%{eif\:n+1\:d}':fontcolor=yellow:fontsize=40:"
                     "box=1:boxcolor=black@0.8:boxborderw=5:x=6:y=6,"
                     f"tile={a.cols}x{rows}:padding=4:color=0x222222"),
                    "-frames:v", "1", str(OUT / "storyboard.png")],
                   check=True, cwd=ROOT)

    (ROOT / a.out).write_text(json.dumps(index, ensure_ascii=False, indent=2),
                              encoding="utf-8")
    print(f"\n스토리보드: {OUT/'storyboard.png'}  ({shots}장, {a.cols}x{rows})")
    print(f"인덱스    : {ROOT/a.out}")
    print("\n⚠️ 다음 단계는 대본이 아니다. **시트를 보고 모든 scene 의 label 을 먼저 채운다.**")


if __name__ == "__main__":
    main()
