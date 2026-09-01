#!/usr/bin/env python3
"""이전 제품을 통째로 보관하고 새 제품용으로 초기화한다.

손으로 폴더를 옮기면 반드시 빠뜨린다. 실제로 `public/narration.mp3` 를 안 옮겨서
**자막은 새 제품, 음성은 이전 제품**인 상태가 나온 적이 있다.
더 나쁜 건 검수를 통과했다는 점이다 — 음성과 영상 길이는 서로 맞았으니까.

  python new_project.py --archive <이전제품> --name "<새 제품>"
  python new_project.py --archive <이전제품> --keep         # 보관만
  python new_project.py --restore <이전제품>                # 보관한 걸 되돌린다
"""
import argparse, json, shutil, sys
from pathlib import Path

ROOT = Path(__file__).parent
# 제품마다 달라지는 것 전부. 하나라도 빠지면 이전 제품이 새 작업에 섞인다.
PRODUCT_STATE = [
    "raw", "sources", "out", "output",
    "public/sources", "public/narration.mp3",
    "remix.json",
]

TEMPLATE = {
    "title": "", "product": "", "keySelling": "",
    "fps": 30, "width": 1080, "height": 1920,
    "voice": "여자",
    "voiceSettings": {"stability": 0.35, "similarity": 0.75, "style": 0.5},
    "speed": 1.2, "maxGap": 0.32, "gap": 0.12, "tail": 0.35,
    "font": "Jua",
    "caption": {"size": 94, "bottom": 330, "stroke": 17, "punch": 1.12},
    "sceneIndex": "out/scene_index.json", "targetCutSec": 1.45,
    "blockedMargin": 0.5,
    "headline": {"text": "", "cut": 1, "coverSec": 0.7, "inVideo": False, "style": "box", "boxColor": "#0D0D0D",
                 "accent": "#FFD84D", "size": 118, "top": 330, "stroke": 22},
    "adBadge": {"text": "광고", "position": "topRight", "size": 34,
                "margin": 44, "bgOpacity": 0.45, "textOpacity": 0.95},
    "narration": [], "beats": [],
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--archive", help="이전 제품을 담을 projects/<이름>")
    ap.add_argument("--name", default="", help="새 제품명 (remix.json 의 product)")
    ap.add_argument("--keep", action="store_true", help="보관만 하고 초기화는 안 함")
    ap.add_argument("--restore", help="projects/<이름> 을 작업 폴더로 되돌린다")
    a = ap.parse_args()

    # 되돌리기 — 지금 작업 중인 상태가 있으면 덮어쓰지 않는다.
    if a.restore:
        src_dir = ROOT / "projects" / a.restore
        if not src_dir.exists():
            have = sorted(d.name for d in (ROOT / "projects").glob("*") if d.is_dir())
            sys.exit(f"{src_dir} 가 없습니다. 보관된 것: {', '.join(have) or '없음'}")
        busy = [r for r in PRODUCT_STATE if (ROOT / r).exists()]
        if busy and not a.archive:
            sys.exit(f"작업 폴더에 {', '.join(busy)} 이(가) 남아 있습니다. "
                     f"--archive <이름> 을 함께 줘서 먼저 보관하세요.")

    if a.archive:
        dest = ROOT / "projects" / a.archive
        if dest.exists():
            sys.exit(f"{dest} 가 이미 있습니다. 다른 이름을 쓰세요.")
        dest.mkdir(parents=True)
        moved = []
        for rel in PRODUCT_STATE:
            src = ROOT / rel
            if not src.exists():
                continue
            tgt = dest / rel
            tgt.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(src), str(tgt))
            moved.append(rel)
        print(f"보관 → {dest}")
        for m in moved:
            print(f"  {m}")
        missing = [r for r in PRODUCT_STATE if r not in moved]
        if missing:
            print(f"  (없어서 건너뜀: {', '.join(missing)})")
    # 보관을 마쳤으니 이제 되돌린다. 되돌릴 때는 초기화하지 않는다.
    if a.restore:
        src_dir = ROOT / "projects" / a.restore
        back = []
        for rel in PRODUCT_STATE:
            src = src_dir / rel
            if not src.exists():
                continue
            tgt = ROOT / rel
            tgt.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(src), str(tgt))
            back.append(rel)
        for d in sorted(src_dir.glob("**/*"), reverse=True):
            if d.is_dir() and not any(d.iterdir()):
                d.rmdir()
        if not any(src_dir.iterdir()):
            src_dir.rmdir()
        print(f"복구 ← projects/{a.restore}")
        for b in back:
            print(f"  {b}")
        print()
        print("7단계부터 이어가면 됩니다: python make_remix.py")
        return

    if a.keep:
        return

    for rel in ("raw", "sources", "out", "output", "public/sources"):
        (ROOT / rel).mkdir(parents=True, exist_ok=True)
    nar = ROOT / "public" / "narration.mp3"
    if nar.exists():
        nar.unlink()

    plan = dict(TEMPLATE)
    if a.name:
        plan["title"] = f"{a.name} 쇼핑쇼츠 REMIX"
        plan["product"] = a.name
    (ROOT / "remix.json").write_text(
        json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")

    print("\n초기화 완료. 다음 순서로 진행한다:")
    print("  1) raw/ 에 소재를 넣는다")
    print("  2) python prep_sources.py --dir raw --out sources")
    print("  3) python index_sources.py --dir sources --cuts 20")
    print("  4) 🚧 out/storyboard.png 을 보고 라벨을 전부 채운다")
    print("  5) remix.json 의 product·keySelling·narration·beats 를 채운다")
    print("  6) python make_remix.py")
    print("  7) npx remotion render src/index.jsx Remix output/완성본.mp4 --crf 18")
    print("  8) python check_render.py")


if __name__ == "__main__":
    main()
