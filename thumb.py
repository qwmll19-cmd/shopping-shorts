#!/usr/bin/env python3
"""썸네일 이미지를 뽑는다 (REMIX 8단계).

썸네일은 **영상을 누르기 전에** 보이는 그림이다. 영상 본편에 문구를 얹으면
재생 내내 남아 자막과 겹친다. 그래서 문구는 여기서만 쓰고 본편에는 넣지 않는다.

  python thumb.py            # 첫 컷 + headline 문구 → output/썸네일.png
  python thumb.py --cut 5    # 5번 컷으로
  python thumb.py --at 12.3  # 특정 시각의 컷으로
"""
import argparse, json, subprocess, sys
from pathlib import Path

ROOT = Path(__file__).parent
OUT = ROOT / "out"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cut", type=int, help="몇 번 컷을 쓸지 (기본: remix.json 의 headline.cut)")
    ap.add_argument("--out", default="output/썸네일.png")
    a = ap.parse_args()

    plan = json.loads((ROOT / "remix.json").read_text(encoding="utf-8"))
    props_p = OUT / "remotion-props.json"
    if not props_p.exists():
        sys.exit("out/remotion-props.json 이 없습니다. 먼저 make_remix.py 를 도세요.")
    props = json.loads(props_p.read_text(encoding="utf-8"))

    head = dict(plan.get("headline") or {})
    if not head.get("text"):
        sys.exit("remix.json 의 headline.text 가 비어 있습니다. 썸네일 문구를 적으세요.")

    fps = props["fps"]
    cover = int(round(head.get("coverSec", 0) * fps))

    if cover > 0 and a.cut is None:
        # 커버 = 썸네일. 영상 맨 앞 프레임을 그대로 뽑으면 시청자가 보는 것과 같다.
        frame, shot = cover // 2, props
        note = f"커버 {head.get('coverSec')}초 구간 (영상 맨 앞과 같은 그림)"
    else:
        # 커버를 안 쓰거나 다른 컷으로 뽑고 싶을 때 — 그 컷 위에 문구를 얹는다.
        cuts = props["cuts"]
        n = a.cut if a.cut is not None else int(head.get("cut", 1))
        cut = cuts[max(0, min(n - 1, len(cuts) - 1))]
        frame = cover + int(round((cut["start"] + cut["dur"] / 2) * fps))
        shot = dict(props)
        shot["headline"] = {**head, "inVideo": True, "sec": 9999}
        shot["captions"] = []
        note = f"컷 {cut['id']} ({cut['shot']})"

    tmp = OUT / "thumb-props.json"
    tmp.write_text(json.dumps({"data": shot}, ensure_ascii=False), encoding="utf-8")

    dst = ROOT / a.out
    dst.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["npx", "remotion", "still", "src/index.jsx", "Remix", str(dst),
                    f"--props={tmp}", f"--frame={frame}", "--log=error"],
                   check=True, cwd=ROOT, shell=(sys.platform == "win32"))
    tmp.unlink(missing_ok=True)
    print(f"썸네일: {dst}")
    print(f"  {note} / 프레임 {frame}")
    print(f"  문구: {head['text'].replace('|', ' / ')}")


if __name__ == "__main__":
    main()
