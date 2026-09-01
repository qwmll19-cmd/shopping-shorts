#!/usr/bin/env python3
"""완성본을 검수한다 (REMIX 8단계). 눈으로 확인할 프레임 시트까지 뽑는다.

  python check_render.py output/완성본.mp4
"""
import argparse, re, json, shutil, subprocess, sys
from pathlib import Path

ROOT = Path(__file__).parent
OUT = ROOT / "out" / "check"


def _font():
    """자막·시트용 한글 폰트. 없으면 프로젝트 public/fonts 로 폴백."""
    from pathlib import Path as _P
    for c in ("C:/Windows/Fonts/malgunbd.ttf", "C:/Windows/Fonts/malgun.ttf",
              str(_P(__file__).parent / "public/fonts/Jua.ttf")):
        if _P(c).exists():
            return c
    raise SystemExit("한글 폰트를 찾지 못했습니다.")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("video", nargs="?", default="output/shopping_shorts_remix.mp4")
    ap.add_argument("--shots", type=int, default=8)
    a = ap.parse_args()
    v = ROOT / a.video
    if not v.exists():
        sys.exit(f"{v} 가 없습니다.")

    info = json.loads(subprocess.run(
        ["ffprobe", "-v", "error", "-show_format", "-show_streams", "-of", "json", str(v)],
        capture_output=True, text=True, encoding="utf-8", errors="replace").stdout)
    vs = next((s for s in info["streams"] if s["codec_type"] == "video"), None)
    as_ = next((s for s in info["streams"] if s["codec_type"] == "audio"), None)
    dur = float(info["format"]["duration"])
    size = int(info["format"]["size"]) / 1048576

    ok = []
    ok.append(("길이 15~30초", 15 <= dur <= 30.5, f"{dur:.1f}초"))
    ok.append(("해상도 1080x1920", vs and (vs["width"], vs["height"]) == (1080, 1920),
               f"{vs['width']}x{vs['height']}" if vs else "없음"))
    ok.append(("오디오 트랙 존재", as_ is not None, as_["codec_name"] if as_ else "없음"))
    if as_:
        adur = float(as_.get("duration", dur))
        ok.append(("오디오 길이 일치", abs(adur - dur) < 0.5, f"{adur:.1f}초"))
    ok.append(("용량 10~50MB", 10 <= size <= 50, f"{size:.1f}MB"))

    props = ROOT / "out" / "remotion-props.json"
    if props.exists():
        pr = json.loads(props.read_text(encoding="utf-8"))
        cuts = pr.get("cuts", [])
        if cuts:
            ds = [c["dur"] for c in cuts]
            # 레퍼런스는 **중앙값** 1.24~1.77초였다. 개별 컷은 0.83초부터 넓게 퍼진다.
            sd = sorted(ds); mid = sd[len(sd)//2]
            ok.append(("컷 중앙값 1.2~1.8초", 1.2 <= mid <= 1.8,
                       f"중앙 {mid:.2f} / 범위 {min(ds):.2f}~{max(ds):.2f} / {len(cuts)}컷"))
            ok.append(("너무 짧거나 긴 컷 없음", all(0.6 <= d <= 2.5 for d in ds),
                       "없음" if all(0.6 <= d <= 2.5 for d in ds)
                       else f"{sum(1 for d in ds if d<0.6 or d>2.5)}개"))
            # 같은 장면이 연달아 나오면 정지화면처럼 보인다
            # 같은 장면이라도 시작 시점이 충분히 다르면 다른 그림이다
            dup = [c["id"] for a, c in zip(cuts, cuts[1:])
                   if a.get("shot") and a.get("shot") == c.get("shot")
                   and abs(a.get("in", 0) - c.get("in", 0)) < 0.4]
            ok.append(("연속 중복 장면 없음", not dup,
                       "없음" if not dup else f"컷 {dup} 가 앞 컷과 동일"))
            # 한 소재가 너무 많으면 리믹스가 아니라 그 영상을 그대로 튼 것처럼 보인다
            from collections import Counter
            cnt = Counter(c.get("src", "?") for c in cuts)
            if len(cnt) > 1:
                top, n_top = cnt.most_common(1)[0]
                share = n_top / len(cuts)
                ok.append(("소재 편중 75% 이하", share <= 0.75,
                           " / ".join(f"{k} {v}컷 {v/len(cuts)*100:.0f}%"
                                      for k, v in cnt.most_common())))
                # 한 소재가 길게 이어지면 "그 영상을 그대로 튼 것" 처럼 보인다
                run = best = 1
                for c1, c2 in zip(cuts, cuts[1:]):
                    run = run + 1 if c1.get("src") == c2.get("src") else 1
                    best = max(best, run)
                ok.append(("같은 소재 연속 5컷 이하", best <= 5, f"최대 {best}컷 연속"))

    # spans(자막 기준) 와 실제 음성이 같은 대본에서 나왔는지.
    # 프로젝트를 옮기다 음성만 이전 것이 남은 적이 있는데, 음성과 영상 길이는
    # 서로 맞아서 검수를 통과해버렸다. 어긋난 건 spans 와 음성이었다.
    sp = ROOT / "out" / "spans.json"
    nar = ROOT / "public" / "narration.mp3"
    if sp.exists() and nar.exists():
        spans = json.loads(sp.read_text(encoding="utf-8"))
        nd = float(subprocess.run(["ffprobe", "-v", "quiet", "-show_entries",
                                   "format=duration", "-of", "csv=p=0", str(nar)],
                                  capture_output=True, text=True).stdout.strip())
        ok.append(("자막↔음성 같은 대본", abs(spans[-1][1] - nd) < 1.5,
                   f"자막 끝 {spans[-1][1]:.1f}초 / 음성 {nd:.1f}초"))
        rj = ROOT / "remix.json"
        if rj.exists():
            n = len(json.loads(rj.read_text(encoding="utf-8")).get("narration", []))
            ok.append(("문장 수 일치", n == len(spans),
                       f"remix.json {n}문장 / spans {len(spans)}문장"))

    # 나레이션이 최신인지 (public/ 이 단일 출처인지)
    pub = ROOT / "public" / "narration.mp3"
    if pub.exists():
        nd = float(subprocess.run(["ffprobe", "-v", "quiet", "-show_entries",
                                   "format=duration", "-of", "csv=p=0", str(pub)],
                                  capture_output=True, text=True).stdout.strip())
        ok.append(("나레이션 길이 ≈ 영상", abs(nd - dur) < 1.5, f"{nd:.1f}초"))

    # 썸네일. 재생 전에 보이는 그림이라 영상 본편이 아니라 파일로 확인한다.
    rjp = ROOT / "remix.json"
    if rjp.exists():
        hl = (json.loads(rjp.read_text(encoding="utf-8")).get("headline") or {})
        ht = (hl.get("text") or "").replace("|", " ").replace("*", "").strip()
        ok.append(("썸네일 문구 있음", bool(ht),
                   ht or "없음 — remix.json 의 headline.text 에 넣으세요"))
        thumb = ROOT / "output" / "썸네일.png"
        fresh = thumb.exists() and thumb.stat().st_mtime >= v.stat().st_mtime - 300
        ok.append(("썸네일 이미지 최신", fresh,
                   "output/썸네일.png" if fresh else "없거나 영상보다 오래됨 — python thumb.py"))

    # 문장 사이 "쉼" 구간에 말소리가 남아 있으면 타임스탬프가 어긋난 것이다.
    # 실제로 깨진 타임스탬프 탓에 침묵 압축이 말하던 구간을 잘라내 음성이 뭉갰다.
    sp_p = OUT.parent / "spans.json"
    nar_p = ROOT / "public" / "narration.mp3"
    if sp_p.exists() and nar_p.exists():
        sps = json.loads(sp_p.read_text(encoding="utf-8"))
        loud = []
        for a, b in [(sps[i][1], sps[i + 1][0]) for i in range(len(sps) - 1)]:
            if b - a < 0.04:
                continue
            o = subprocess.run(["ffmpeg", "-v", "info", "-ss", f"{a:.3f}", "-t", f"{b-a:.3f}",
                                "-i", str(nar_p), "-af", "volumedetect", "-f", "null", "-"],
                               capture_output=True, text=True, encoding="utf-8",
                               errors="replace").stderr
            m = re.search(r"mean_volume: (-?[\d.]+) dB", o)
            if m and float(m.group(1)) > -30:
                loud.append(f"{a:.2f}~{b:.2f}({m.group(1)}dB)")
        ok.append(("문장 사이가 조용한가", not loud,
                   "조용함" if not loud else "말소리 남음 — " + ", ".join(loud[:3])))

    # 카피킷: 플랫폼 블록마다 파트너스 고지가 있어야 한다.
    #   유튜브 설명에만 넣고 틱톡·인스타에 빠뜨린 적이 있다.
    #   복사하는 건 블록이지 체크리스트가 아니다.
    kit = ROOT / "output" / "카피킷.md"
    if kit.exists():
        txt = kit.read_text(encoding="utf-8")
        NOTE = "쿠팡 파트너스 활동을 통해 일정액의 수수료를 제공받습니다."
        # 전체 개수만 세면 한 플랫폼에서 빠져도 통과한다. 섹션별로 본다.
        secs = txt.split(chr(10) + "## ")
        miss = [w for w in ("유튜브", "인스타", "틱톡")
                if not any(w in sec.split(chr(10))[0] and NOTE in sec for sec in secs)]
        ok.append(("카피킷 파트너스 고지", not miss,
                   "세 플랫폼 모두 있음" if not miss else "빠진 곳: " + ", ".join(miss)))
        left = txt.count("[쿠팡_링크]")
        ok.append(("카피킷 링크 채움", left == 0,
                   "채워짐" if left == 0 else f"[쿠팡_링크] {left}곳 남음 — 업로드 전에 바꾸세요"))

    # 컷 경계에서 프레임이 비면 그 프레임은 검게 렌더된다. 1프레임(0.03초)이라
    # 눈으로는 놓치기 쉬워 기계로 전수 확인한다.
    bd = subprocess.run(["ffmpeg", "-v", "info", "-i", str(v), "-vf",
                         "blackdetect=d=0.01:pic_th=0.95:pix_th=0.10", "-f", "null", "-"],
                        capture_output=True, text=True, encoding="utf-8",
                        errors="replace").stderr
    blacks = re.findall(r"black_start:([\d.]+)", bd)
    ok.append(("검은 프레임 없음", not blacks,
               "없음" if not blacks else f"{len(blacks)}곳 — {', '.join(b[:5] for b in blacks[:4])}초"))

    print(f"검수: {v.name}")
    for name, passed, val in ok:
        print(f"  {'PASS' if passed else 'FAIL'}  {name:<20} {val}")

    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir(parents=True)
    shutil.copy(_font(), OUT / "f.ttf")
    for i in range(a.shots):
        t = dur * (i + 0.5) / a.shots
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-ss", f"{t:.2f}", "-i", str(v),
                        "-frames:v", "1", "-vf", "scale=240:-1",
                        str(OUT / f"{i+1:02d}.jpg")], check=True)
    cols = 4
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-framerate", "1",
                    "-i", str(OUT / "%02d.jpg"), "-vf",
                    (r"drawtext=fontfile=out/check/f.ttf:text='%{eif\:n+1\:d}':"
                     "fontcolor=yellow:fontsize=36:box=1:boxcolor=black@0.8:"
                     f"boxborderw=5:x=6:y=6,tile={cols}x{-(-a.shots//cols)}:padding=4:color=0x222222"),
                    "-frames:v", "1", str(OUT / "sheet.png")], check=True, cwd=ROOT)
    if not (OUT / "sheet.png").exists():
        sys.exit("검수 시트를 만들지 못했습니다. 8단계는 시트를 봐야 끝납니다.")
    print(f"\n검수 시트: {OUT/'sheet.png'} — 자막 크기·잘림·원본 자막 잔상을 눈으로 확인하라")
    if not all(p for _, p, _ in ok):
        sys.exit(1)


if __name__ == "__main__":
    main()
