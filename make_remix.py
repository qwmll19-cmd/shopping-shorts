#!/usr/bin/env python3
"""remix.json → 나레이션 트랙 + 나레이션과 일치하는 자막 + Remotion props.

자막은 컷이 아니라 **나레이션 문장에서 잘라내** 음성 길이에 비례해 배치한다.
따라서 들리는 말과 보이는 글자가 항상 일치한다.
"""
import json, re, shutil, subprocess, sys
from pathlib import Path
import tts
import tts_whole

ROOT = Path(__file__).parent
OUT = ROOT / "out"
VO = OUT / "vo_remix"
MAXCHARS = 12          # 자막 한 조각 최대 글자수
MINCHARS = 5           # 이보다 짧은 꼬리는 앞 조각에 붙임


def probe(p):
    r = subprocess.run(["ffprobe", "-v", "quiet", "-show_entries", "format=duration",
                        "-of", "csv=p=0", str(p)], capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    return float(r.stdout.strip())


def srt_time(t):
    h, r = divmod(t, 3600); m, s = divmod(r, 60)
    return f"{int(h):02d}:{int(m):02d}:{int(s):02d},{int(round((s%1)*1000)):03d}"


def _wrap_balanced(words, cap):
    """어절을 cap 글자 이내로 나누되, 조각 길이를 최대한 고르게 만든다.

    앞에서부터 꽉 채우면 마지막에 '번만' 같은 토막이 남는다.
    필요한 최소 조각 수를 먼저 구하고, 그 조각 수를 유지하는 가장 작은
    용량을 이분탐색으로 찾아 배치한다.
    """
    def groups_needed(c):
        n, cur = 1, 0
        for w in words:
            if len(w) > c:
                return 10 ** 9
            add = len(w) + (1 if cur else 0)
            if cur + add > c:
                n, cur = n + 1, len(w)
            else:
                cur += add
        return n

    n = groups_needed(cap)
    if n >= 10 ** 9:
        return [" ".join(words)]

    lo, hi, best = max(len(w) for w in words), cap, cap
    while lo <= hi:
        mid = (lo + hi) // 2
        if groups_needed(mid) <= n:
            best, hi = mid, mid - 1
        else:
            lo = mid + 1

    out, cur = [], ""
    for w in words:
        cand = f"{cur} {w}".strip()
        if cur and len(cand) > best:
            out.append(cur); cur = w
        else:
            cur = cand
    if cur:
        out.append(cur)
    return out


def chunk(text):
    """문장을 자막 조각으로 나눈다. 쉼표·마침표를 1차 경계로 쓴다."""
    out = []
    for part in [x.strip().rstrip(",.") for x in re.split(r"(?<=[,.!?])\s*", text) if x.strip()]:
        out.extend(_wrap_balanced(part.split(), MAXCHARS) if len(part) > MAXCHARS else [part])
    return out


def audit_script(plan, lines, problems):
    """대본이 광고문이 아니라 1인칭 후기로 읽히는지, 훅이 제 일을 하는지 본다."""
    texts = [l["text"] for l in lines]
    hook = texts[0] if texts else ""

    # ① 훅이 지시대명사로 시작하면 무엇을 가리키는지 알 수 없다
    for bad in ("이렇게", "이거", "이게", "요게", "그렇게"):
        if hook.startswith(bad):
            problems.append(f"  훅이 '{bad}' 로 시작합니다 — 첫 3초에 뭘 가리키는지 알 수 없습니다.")
            break

    # ② 훅에 제품이 뭔지 나와야 한다
    prod = plan.get("product", "")
    if prod:
        key = [w for w in prod.split() if len(w) > 1]
        if key and not any(k in hook for k in key):
            problems.append(f"  훅에 제품({prod})이 안 나옵니다 — 뭘 파는지 첫 3초에 알려야 합니다.")

    # ③ 핵심 소구점이 뒤로 밀리지 않았는지
    sell = plan.get("keySelling", "")
    if sell:
        where = next((i for i, t in enumerate(texts) if sell in t), None)
        if where is None:
            problems.append(f"  핵심 소구점('{sell}')이 대본에 없습니다.")
        elif where > 1:
            problems.append(f"  핵심 소구점('{sell}')이 {where+1}번째 문장입니다 — 훅이나 두 번째로 올리세요.")

    # ④ 판매원 톤 vs 1인칭 후기 톤
    #    후기 표지: 저는·제가·우리 집 / ~더라고요 ~했어요 ~봤어요 ~거든요 ~는데 ~됐어요
    #    '~는데,' 와 '~됐어요/~졌어요' 도 후기 말투인데 빠져 있어서, 문장을 제대로 고쳐도
    #    비율이 떨어지는 오탐이 났다. 축약형(됐 = 되+었)을 빠뜨린 탓이다.
    import re
    first = sum(1 for t in texts if re.search(
        r"(저는|제가|내가|우리 집|더라고요|더라구요|거든요|는데|았어요|었어요|했어요|했는데"
        r"|됐어요|졌어요|봤어요|잖아요|네요|고요)", t))
    ratio = first / len(texts) if texts else 0
    if ratio < 0.5:
        problems.append(f"  1인칭 후기 표현이 {first}/{len(texts)}문장 ({ratio*100:.0f}%) 뿐입니다 — "
                        f"절반 이상이어야 광고 티가 안 납니다. '~예요/~할 수 있어요' 같은 "
                        f"설명체를 '~하더라고요/~해봤어요' 로 바꾸세요.")

    # ⑤ 끝맺음이 합쇼체(~니다/~니까)면 상세페이지 문장이다
    #    SKILL.md §1 의 끝맺음 금지어를 도구가 직접 막는다.
    #    "~입니다 / ~합니다 / ~할 수 있습니다 / ~가 가능합니다 / ~추천드립니다" 가 모두 여기 걸린다.
    hard = [t for t in texts if re.search(r"(니다|니까)\s*[.!?]?$", t.strip())]
    if hard:
        problems.append(f"  합쇼체로 끝나는 문장 {len(hard)}개 — 상세페이지 말투입니다. "
                        f"해요체 후기로 바꾸세요: {hard[0]}")

    # ⑥ 중간 문장을 '~거든요'로 닫으면 흐름이 끊긴다
    #    '~거든요'는 말을 닫는 종결어미다. 다음 문장이 전환·해결이면 거기서 뚝 끊긴다.
    #    "물 튈까 봐 계속 신경 쓰였거든요." → "…쓰였는데," 로 이어야 다음으로 흘러간다.
    #    첫 문장(도입)과 끝 두 문장(마무리 상승)에서는 써도 된다 — §2-J 참조.
    #    첫 문장도 예외가 아니다. 훅 다음에도 이야기가 이어지므로 똑같이 끊긴다.
    #    쓸 수 있는 자리는 끝 두 문장뿐이다 (마무리 억양을 받쳐주는 자리).
    mid = [(i, t) for i, t in enumerate(texts)
           if i <= len(texts) - 3 and re.search(r"거든요\s*[.!?]?$", t.strip())]
    for i, t in mid:
        problems.append(f"  {i+1}번째 문장이 '~거든요'로 닫힙니다 — 다음 문장으로 안 이어집니다. "
                        f"'~는데요/~는데,' 로 바꾸세요: {t}")

    # ⑦ 같은 어미가 이어지면 단조롭게 들린다
    #    "~더라고요"만 세 번 이어지면 읽는 사람이 리듬을 못 느낀다.
    BUCKET = [("더라고요", "더라고요|더라구요"), ("거든요", "거든요"), ("는데요", "는데요"),
              ("~고요", "고요"), ("~게요", "게요"), ("~세요", "세요"),
              ("~어요", "어요|에요|예요|아요|해요|돼요|났어요|됐어요")]
    def _bucket(t):
        t = t.strip().rstrip(".!?,")
        for name, pat in BUCKET:
            if re.search(f"({pat})$", t):
                return name
        return "기타"
    buckets = [_bucket(t) for t in texts]
    run = 1
    for i in range(1, len(buckets)):
        if buckets[i] == buckets[i - 1] and buckets[i] != "기타":
            run += 1
            if run == 3:
                problems.append(f"  {i-1}~{i+1}번째 문장이 모두 '{buckets[i]}'로 끝납니다 — "
                                f"단조롭게 들립니다. 하나를 다른 어미로 바꾸세요.")
        else:
            run = 1

    # ⑨ 지난 제품 문구를 그대로 가져다 쓰면 채널이 템플릿처럼 보인다.
    #    문서에 예시를 적어두면 복사하게 되므로 도구가 대조한다.
    hl = (plan.get("headline") or {}).get("text", "").strip()
    if hl:
        import json as _j
        for old in sorted((ROOT / "projects").glob("*/remix.json")):
            try:
                o = _j.loads(old.read_text(encoding="utf-8"))
            except Exception:
                continue
            ot = (o.get("headline") or {}).get("text", "").strip()
            if ot and ot == hl:
                problems.append(f"  썸네일 문구가 '{old.parent.name}' 와 똑같습니다 — "
                                f"제품마다 새로 뽑으세요: {hl.replace('|', ' / ')}")
                break

    # ⑧ 마지막 문장이 뚝 떨어지지 않게 (§2-J 실측)
    #    "…걸어둘게요."로 끝내면 끝 하강 -8.8 반음. 앞을 '~거든요'로 받치면 -0.5.
    if texts:
        last = texts[-1].strip()
        if re.search(r"(게요|세요)\s*[.!?]?$", last) and "거든요" not in last:
            problems.append(f"  마지막 문장이 '~게요/~세요'로 뚝 끝납니다 (실측 끝 하강 -8.8 반음). "
                            f"앞에 '~거든요' 절을 붙여 받치세요: {last}")


def main():
    no_tts = "--no-tts" in sys.argv
    # 0-A 게이트는 prep_sources.py 한 곳에만 둔다.
    #   여기(7단계)에도 두면 같은 검사가 두 벌이 되고, --skip-ref 로 2단계를 통과해도
    #   여기서 다시 막혀 해제 플래그가 일관되지 않는다. 소재를 만지는 첫 도구에서 막는 게 맞다.
    plan = json.loads((ROOT / "remix.json").read_text(encoding="utf-8"))
    VO.mkdir(parents=True, exist_ok=True)

    # 소재를 public/ 으로 동기화한다. Remotion 은 public/ 만 읽으므로
    # 손으로 복사하게 두면 전처리를 다시 해도 옛 화면이 렌더된다.
    src_dir, pub_dir = ROOT / "sources", ROOT / "public" / "sources"
    pub_dir.mkdir(parents=True, exist_ok=True)
    synced = []
    for f in sorted(src_dir.glob("*.mp4")):
        dst = pub_dir / f.name
        if not dst.exists() or dst.stat().st_size != f.stat().st_size:
            shutil.copy(f, dst); synced.append(f.name)
    for f in sorted(pub_dir.glob("*.mp4")):        # sources 에서 지운 건 public 에서도 제거
        if not (src_dir / f.name).exists():
            f.unlink(); synced.append(f"{f.name} (삭제)")
    if synced:
        print(f"소재 동기화: {', '.join(synced)}")
    speed, gap = plan.get("speed", 1.0), plan.get("gap", 0.12)

    problems = []

    # ── 1. 대본 전체를 한 번에 읽힌다 ──
    #
    # 문장마다 따로 TTS 를 부르면 ElevenLabs 가 각각을 독립된 발화로 처리한다.
    # 문장마다 억양이 처음부터 시작해 끝에서 떨어지고, 이어붙이면
    # "영혼 없는 토막"으로 들린다. 한 번에 읽혀야 억양이 문장을 넘어 이어진다.
    # 문장 경계는 with-timestamps 가 주는 문자 단위 시각으로 잘라낸다.
    # 자막 강조 표기 `*단어*` 는 화면에만 쓴다. TTS 에는 별표를 넘기지 않는다.
    marks = [re.findall(r"\*([^*]+)\*", n["text"]) for n in plan["narration"]]
    texts = [n["text"].replace("*", "") for n in plan["narration"]]
    track = ROOT / "public" / "narration.mp3"
    track.parent.mkdir(parents=True, exist_ok=True)
    extra = speed / min(speed, 1.2)          # 1.2 초과분은 ffmpeg 로

    # 대본·목소리 설정이 지난번과 같으면 API 를 다시 부르지 않는다.
    # ElevenLabs 무료 크레딧은 유한하고, 검증하느라 스크립트를 여러 번 돌리는
    # 동안 같은 음성을 반복 결제할 이유가 없다. --force-tts 로 무시할 수 있다.
    stamp = OUT / "tts_stamp.json"
    key = json.dumps([texts, plan.get("voice"), speed,
                      plan.get("voiceSettings", {}), plan.get("maxGap", 0.32)],
                     ensure_ascii=False, sort_keys=True)
    fresh = (track.exists() and track.stat().st_size > 0
             and (OUT / "spans.json").exists() and (OUT / "chars.json").exists()
             and stamp.exists() and stamp.read_text(encoding="utf-8") == key)
    if fresh and "--force-tts" not in sys.argv:
        if not no_tts:
            print("나레이션 재사용 — 대본과 목소리 설정이 지난번과 같다 (--force-tts 로 재생성)")
        no_tts = True

    if not no_tts:
        raw = OUT / "_narration_raw.mp3"
        vs = plan.get("voiceSettings", {})
        _, spans_raw, chars_raw = tts_whole.synth_whole(
            texts, tts.VOICES.get(plan.get("voice", "Sarah"), plan.get("voice", "Sarah")),
            raw, speed=speed,
            stability=vs.get("stability", 0.5), similarity=vs.get("similarity", 0.75),
            style=vs.get("style", 0.0))
        stretched = OUT / "_narration_fast.mp3"
        tts_whole.stretch(raw, stretched, extra)
        sp = [[a / extra, b / extra] for a, b in spans_raw]
        # 문장 사이 긴 침묵은 잘라낸다. 레퍼런스 실측 쉼은 평균 0.30초 · 최대 0.60초인데
        # TTS 는 1초를 넘기기도 하고, 그러면 문장이 끊긴 것처럼 들린다.
        sp, shift = tts_whole.compress_silence(stretched, track, sp,
                                               max_gap=plan.get("maxGap", 0.32))
        stretched.unlink(missing_ok=True)
        ch = [[c, round(shift(a / extra), 3), round(shift(b / extra), 3)]
              for c, a, b in chars_raw]
        (OUT / "spans.json").write_text(json.dumps(sp), encoding="utf-8")
        (OUT / "chars.json").write_text(json.dumps(ch, ensure_ascii=False), encoding="utf-8")
        stamp.write_text(key, encoding="utf-8")
    if not track.exists() or track.stat().st_size == 0:
        sys.exit("TTS 실패. 음성 없이 렌더하지 않습니다.")
    spans_s = json.loads((OUT / "spans.json").read_text(encoding="utf-8"))

    # 캐시된 타임스탬프도 고친다. ElevenLabs 가 거꾸로 가는 값을 준 적이 있고,
    # 그 탓에 문장이 1초 일찍 끝난 것으로 계산돼 자막이 음성보다 먼저 넘어갔다.
    _ch = json.loads((OUT / "chars.json").read_text(encoding="utf-8"))
    _st, _en = tts_whole.repair_times([c[1] for c in _ch], [c[2] for c in _ch])
    if any(abs(a - c[1]) > 1e-6 or abs(b - c[2]) > 1e-6
           for c, a, b in zip(_ch, _st, _en)):
        _ch = [[c[0], round(a, 3), round(b, 3)] for c, a, b in zip(_ch, _st, _en)]
        (OUT / "chars.json").write_text(json.dumps(_ch, ensure_ascii=False), encoding="utf-8")
        full = "".join(c[0] for c in _ch)
        spans_s, pos = [], 0
        for t in texts:
            a = full.index(t, pos); b = a + len(t); pos = b
            spans_s.append([round(_ch[a][1], 3), round(_ch[b - 1][2], 3)])
        (OUT / "spans.json").write_text(json.dumps(spans_s), encoding="utf-8")
        print("타임스탬프 복구: 거꾸로 가는 값을 고치고 문장 구간을 다시 계산했습니다")

    # 문장이 글자 수에 비해 터무니없이 짧으면 타임스탬프가 깨진 것이다.
    for _i, (t, (a, b)) in enumerate(zip(texts, spans_s)):
        if len(t) and (b - a) / len(t) < 0.05:
            problems.append(f"  {_i+1}번째 문장 구간이 {b-a:.2f}초뿐입니다 ({len(t)}자) — "
                            f"타임스탬프가 깨졌습니다. --force-tts 로 다시 받으세요.")

    lines = [{"text": t, "at": round(a, 2), "dur": round(b - a, 2)}
             for t, (a, b) in zip(texts, spans_s)]
    shutil.copy(track, OUT / "narration.mp3")

    audit_script(plan, lines, problems)

    vo_end = probe(track)

    # ── 3. 컷 배치 — **장면이 컷 수를 정한다** ──
    #
    # 우리 원칙은 "화면을 먼저 보고 대본을 쓴다" 인데, 예전 구현은 거꾸로였다:
    #   컷 수 = 나레이션 길이 ÷ 목표 컷길이
    # 그러면 대본을 한 글자만 고쳐도 컷 수가 바뀌고, 어느 비트가 컷 2개를 받는지
    # 재배치된다. 장면이 모자란 비트는 shots 를 돌려쓰게 되고, 결국
    # 화면과 다른 얘기를 하는 문장 위에 엉뚱한 컷이 붙는 사고가 났다.
    #
    # 그래서 뒤집었다:
    #   컷 수      = Σ(비트별 장면 수)        ← 화면이 정한다
    #   컷 길이    = 문장 길이 ÷ 그 비트 장면 수
    #   장면 ↔ 컷  = 1:1 (순환 없음 → 채우기용 장면이 필요 없다)
    #
    # 대본을 고쳐도 **장면 순서는 그대로**고 길이만 늘고 준다.
    tail = plan.get("tail", 0.6)
    target = vo_end + tail
    want_sec = plan.get("targetCutSec", 1.45)

    beats = plan.get("beats")
    if beats:
        if len(beats) != len(lines):
            sys.exit(f"비트 {len(beats)}개 ≠ 나레이션 {len(lines)}문장. "
                     f"1:1 로 맞춰야 말과 화면이 붙습니다.")

        idx = json.loads((ROOT / plan.get("sceneIndex", "out/scene_index.json"))
                         .read_text(encoding="utf-8"))
        scene = {sc["n"]: (fn, sc["start"], sc["end"], sc.get("label", ""))
                 for fn, v in idx.items() for sc in v["scenes"]}
        # 소재별 총 길이 — 컷이 파일 끝을 넘어가면 그 구간이 검게 렌더된다.
        srcdur = {fn: float(v["duration"]) for fn, v in idx.items()}
        # 라벨이 '['로 시작하는 장면은 못 쓰는 구간이다 (원본 자막·다른 색 제품 등).
        # 컷은 장면보다 길 수 있어 옆 장면으로 넘어가는데, 넘어간 곳이 이 구간이면
        # 화면에 중국어 자막이 딸려 나온다. 실제로 그렇게 나왔다.
        # 장면 경계와 자막이 사라지는 시점은 다르다. 실측하니 자막이 경계보다
        # 0.42초 더 남았고, 그 0.42초가 완성본에 중국어로 떴다. 여유를 둔다.
        margin = plan.get("blockedMargin", 0.5)
        blocked = {}
        for fn, v in idx.items():
            blocked[fn] = [(sc["start"] - margin, sc["end"] + margin, sc.get("label", ""))
                           for sc in v["scenes"] if sc.get("label", "").startswith("[")]

        # 문장별 구간 — 마지막 문장은 tail 까지
        seg = []
        for i, l in enumerate(lines):
            end = lines[i + 1]["at"] if i + 1 < len(lines) else target
            seg.append((l["at"], end))

        cuts, t = [], 0.0
        for j, (b, (s0, s1)) in enumerate(zip(beats, seg)):
            shots = b["shots"]
            span = s1 - s0
            dur = span / len(shots)
            # 레퍼런스 실측은 **컷 중앙값** 1.24~1.77초였다. 개별 컷은 0.83초부터
            # 4초까지 넓게 퍼져 있다. 그러니 모든 컷을 대역에 가둘 이유가 없다.
            # 잡아야 할 건 두 극단뿐이다 — 너무 짧아 인지가 안 되거나, 너무 길어 늘어지거나.
            if dur < 0.6 or dur > 2.5:
                want = max(1, round(span / want_sec))
                fix = (f"장면을 {want}개로 맞추세요" if want != len(shots)
                       else "문장 길이를 조정하세요")
                problems.append(
                    f"  [{j+1}] '{b['name']}' — 컷 {dur:.2f}초. "
                    f"문장 {span:.1f}초 / 장면 {len(shots)}개 → {fix}. "
                    f"문장: {lines[j]['text'][:32]}")
            for k, n in enumerate(shots):
                if n not in scene:
                    sys.exit(f"장면 #{n} 이 인덱스에 없습니다. 3단계를 다시 도세요.")
                fn, st, en, label = scene[n]
                start = min(st + 0.1, max(st, en - dur - 0.05))
                # 파일 끝을 넘지 않게 당긴다. 넘으면 마지막 프레임이 검게 나온다.
                start = round(max(0.0, min(start, srcdur[fn] - dur)), 2)
                # 못 쓰는 구간에 걸리면 뒤로 밀고, 안 되면 앞으로 당긴다.
                # 같은 장면 안에서 옮기지 못할 때만 경고한다.
                def _hit(x):
                    return next((b2 for b2 in blocked.get(fn, [])
                                 if x < b2[1] and x + dur > b2[0]), None)
                for _ in range(len(blocked.get(fn, [])) + 1):
                    h = _hit(start)
                    if not h:
                        break
                    cand = h[1]                              # 구간 뒤로
                    if cand + dur > srcdur[fn]:
                        cand = h[0] - dur                    # 안 되면 구간 앞으로
                    if cand < 0 or cand + dur > srcdur[fn]:
                        break
                    start = round(cand, 2)
                hit = [b2 for b2 in blocked.get(fn, [])
                       if start < b2[1] and start + dur > b2[0]]
                if hit:
                    problems.append(
                        f"  [{j+1}] '{b['name']}' #{n} — 컷 {start:.2f}~{start+dur:.2f}초가 "
                        f"{fn} 의 못 쓰는 구간 {hit[0][0]:.2f}~{hit[0][1]:.2f}초"
                        f"('{hit[0][2]}')를 지나갑니다. 이 비트에 장면을 더 넣어 컷을 줄이거나 "
                        f"다른 장면을 쓰세요.")
                if dur > srcdur[fn]:
                    problems.append(f"  [{j+1}] '{b['name']}' — 컷 {dur:.2f}초가 "
                                    f"{fn} 전체 길이({srcdur[fn]:.2f}초)보다 깁니다. "
                                    f"이 비트에 장면을 더 넣으세요.")
                cuts.append({"id": len(cuts) + 1, "dur": round(dur, 2),
                             "start": round(t, 2), "src": fn, "in": start,
                             "beat": b["name"], "shot": f"#{n} {label}",
                             "fx": "punch-in" if k == 0 else "none"})
                t += dur
        plan["cuts"] = cuts
        total = round(t, 2)
        ds = [c["dur"] for c in cuts]
        print(f"컷 {len(cuts)}개 (= 장면 수) / 길이 {min(ds):.2f}~{max(ds):.2f}초 "
              f"— 장면과 컷이 1:1")

    # ── 4. 나레이션에서 자막 생성 (글자수 비례 배치) ──
    chars = json.loads((OUT / "chars.json").read_text(encoding="utf-8"))
    used = set()          # 자막에 실제로 칠해진 강조 단어
    full = " ".join(l["text"] for l in lines)
    caps, cursor = [], 0
    for l in lines:
        pieces = chunk(l["text"])
        base = full.index(l["text"], cursor); cursor = base + len(l["text"])
        off = 0
        for p in pieces:
            # 조각이 원문에서 시작하는 글자 위치를 찾아 그 글자의 실제 시각을 쓴다.
            # 글자수 비례로 추정하면 문장 뒤쪽 조각이 밀린다.
            k = l["text"].find(p, off)
            if k < 0: k = off
            i0 = min(base + k, len(chars) - 1)
            i1 = min(base + k + len(p) - 1, len(chars) - 1)
            off = k + len(p)
            # 이 문장의 강조 단어가 조각에 들어 있으면 별표를 다시 씌운다.
            shown = p
            # 한 조각에 강조가 여러 개 있을 수 있다. 하나만 칠하고 멈추지 않는다.
            # 원문에서 그 단어가 있던 자리만 칠한다. 단순 치환하면
            # '차' 가 '차지하고요' 의 '차' 까지 칠해 엉뚱한 글자가 노래진다.
            li = lines.index(l)
            spans = []
            for w in marks[li]:
                at = l["text"].find(w, k)
                if 0 <= at < k + len(p):
                    spans.append((at - k, at - k + len(w), w))
            shown = ""
            prev = 0
            for a_, b_, w in sorted(spans):
                if a_ < prev or b_ > len(p):
                    continue
                shown += p[prev:a_] + f"*{w}*"
                prev = b_
                used.add(w)
            shown += p[prev:]
            caps.append({"start": round(chars[i0][1], 2),
                         "end": round(chars[i1][2], 2), "text": shown})

    # 강조 단어가 자막 조각 경계에 걸쳐 잘리면 색이 안 칠해진다.
    # 조용히 넘어가면 어떤 문장만 노랗고 어떤 문장은 안 노란 상태가 된다.
    short = sorted({w for ws in marks for w in ws if len(w.strip()) < 2})
    if short:
        problems.append(f"  한 글자 강조는 다른 단어 속에서도 칠해집니다: {', '.join(short)} — "
                        f"두 글자 이상으로 쓰세요 (예: '차' → '차에')")
    lost = [w for ws in marks for w in ws if w not in used]
    if lost:
        problems.append(f"  강조 단어가 자막 조각에 걸쳐 잘렸습니다: {', '.join(lost)} — "
                        f"두세 글자로 줄이세요 (예: '자리가 남' → '자리')")

    # ── 6. 산출물 ──
    # 자막이 끊기지 않게 다음 조각 직전까지 늘린다.
    # 음성은 이어지는데 자막만 사라졌다 뜨면 어긋난 것처럼 보인다.
    for a_, b_ in zip(caps, caps[1:]):
        a_["end"] = round(min(b_["start"] - 0.02, a_["end"] + 0.9), 2)
        if a_["end"] <= a_["start"]:
            a_["end"] = round(a_["start"] + 0.2, 2)
    if caps:
        caps[-1]["end"] = round(min(total, caps[-1]["end"] + 0.6), 2)

    (OUT / "subtitles.srt").write_text("\n".join(
        f"{i}\n{srt_time(c['start'])} --> {srt_time(c['end'])}\n{c['text']}\n"
        for i, c in enumerate(caps, 1)), encoding="utf-8")
    # 썸네일 = 커버. 영상 맨 앞에 coverSec 만큼 두면 플랫폼이 그 프레임을 잡고,
    # 본편이 시작되면 사라진다. 자막과 겹치지 않는다 (본편은 커버 뒤로 밀린다).
    headline = dict(plan.get("headline") or {})
    if not headline.get("text"):
        headline = None
    else:
        headline.setdefault("coverSec", 0.7)
        if headline.get("inVideo"):   # 본편에도 얹고 싶을 때만
            headline.setdefault("sec", round(spans_s[1][0] if len(spans_s) > 1 else total, 2))

    (OUT / "remotion-props.json").write_text(json.dumps({
        "fps": plan["fps"], "width": plan["width"], "height": plan["height"],
        "durationInFrames": int(round(total * plan["fps"]))
        + (int(round((headline or {}).get("coverSec", 0) * plan["fps"]))),
        "narration": "narration.mp3", "cuts": plan["cuts"], "captions": caps,
        "font": plan.get("font", "Jua"),
        "caption": plan.get("caption", {}),
        "adBadge": plan.get("adBadge", {}),
        "headline": headline,
    }, ensure_ascii=False, indent=2), encoding="utf-8")

    if problems:
        print()
        print("[경고]")
        for msg in problems:
            print(msg)
        print()
    print(f"배속 {speed}x / 나레이션 {vo_end:.2f}초 → 영상 {total:.2f}초")
    print(f"컷 {len(plan['cuts'])}개 / 평균 {total/len(plan['cuts']):.2f}초")
    print(f"자막 {len(caps)}조각 — 전부 나레이션 문장에서 잘라냄")
    for c in caps[:6]:
        print(f"  {c['start']:>5.2f}~{c['end']:>5.2f}  {c['text']}")
    print("  ...")


if __name__ == "__main__":
    main()
