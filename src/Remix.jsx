import {
  AbsoluteFill, Audio, OffthreadVideo, Sequence,
  continueRender, delayRender,
  interpolate, spring, staticFile, useCurrentFrame, useVideoConfig,
} from "remotion";

// 자막 폰트는 remix.json 의 "font" 로 정한다. 기본은 캡컷 감성의 배민 주아체.
// public/fonts/ 에 있는 후보: Jua · BlackHanSans · Dongle · Gaegu · GamjaFlower · HiMelody
const FONT = window.__SHORTS_FONT__ ?? "Jua";
const fontHandle = delayRender(`${FONT} 폰트 로딩`);
new FontFace(FONT, `url(${staticFile(`fonts/${FONT}.ttf`)}) format("truetype")`)
  .load()
  .then((f) => { document.fonts.add(f); continueRender(fontHandle); })
  .catch(() => continueRender(fontHandle));   // 실패해도 렌더는 진행(기본 폰트로 대체)

const KR = `"${FONT}","Malgun Gothic","맑은 고딕",system-ui,sans-serif`;
const LEGAL = '"Malgun Gothic","맑은 고딕",system-ui,sans-serif';   // 고지 문구는 가독성 우선

/** 실제 영상 컷 — 세로 채우기 + 하단 크롭(원본 자막 제거) + punch-in */
const Shot = ({ cut, durInFrames }) => {
  const frame = useCurrentFrame();
  const crop = cut.cropBottom ?? 0;          // 아래 몇 %를 프레임 밖으로 밀어낼지
  const grow = 1 / (1 - crop);               // 그만큼 키워야 위쪽이 화면을 채움
  const zoom = cut.fx === "punch-in"
    ? interpolate(frame, [0, durInFrames], [1.0, PUNCH], { extrapolateRight: "clamp" })
    : 1.02;
  return (
    <AbsoluteFill style={{ overflow: "hidden", background: "#000" }}>
      <div style={{
        position: "absolute", top: 0, left: 0,
        width: "100%", height: `${grow * 100}%`,
        transform: `scale(${zoom})`, transformOrigin: "center top",
      }}>
        <OffthreadVideo
          src={staticFile(`sources/${cut.src}`)}
          startFrom={Math.round((cut.in ?? 0) * 30)}
          style={{ width: "100%", height: "100%", objectFit: "cover" }}
          muted
        />
      </div>
    </AbsoluteFill>
  );
};

/** 쇼츠 자막 — 크기 고정, 진짜 외곽선(그림자 겹치기 아님) */
// 자막 설정은 remix.json 의 caption 에서 온다 (코드를 고치지 않는다)
const CAP = (typeof window !== "undefined" && window.__SHORTS_CAPTION__) || {};
const CAPTION_SIZE = CAP.size ?? 94;
const CAPTION_BOTTOM = CAP.bottom ?? 330;
const CAPTION_STROKE = CAP.stroke ?? 17;
const PUNCH = CAP.punch ?? 1.12;

const Caption = ({ text }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const s = spring({ frame, fps, config: { damping: 200, mass: 0.5 } });

  // 두 겹을 정확히 겹쳐 그린다: 뒤는 굵은 검정 외곽선, 앞은 흰 글자.
  // text-shadow 를 여러 개 겹치면 모서리가 계단처럼 깨져 보인다.
  const base = {
    fontFamily: KR,
    fontSize: CAPTION_SIZE,
    fontWeight: 400,          // 주아체는 단일 굵기라 bold 를 주면 합성되어 뭉갠다
    lineHeight: 1.3,
    textAlign: "center",
    wordBreak: "keep-all",
    margin: 0,
    whiteSpace: "pre-wrap",
  };

  return (
    <AbsoluteFill style={{ justifyContent: "flex-end", alignItems: "center", paddingBottom: CAPTION_BOTTOM }}>
      <div style={{
        position: "relative",
        maxWidth: 1010,
        transform: `translateY(${interpolate(s, [0, 1], [24, 0])}px)`,
        opacity: interpolate(s, [0, 1], [0, 1]),
      }}>
        <div style={{
          ...base,
          color: "#000",
          WebkitTextStroke: `${CAPTION_STROKE}px #000`,
          filter: "drop-shadow(0 6px 14px rgba(0,0,0,.55))",
        }}>{text}</div>
        <div style={{ ...base, position: "absolute", left: 0, top: 0, right: 0, color: "#fff" }}>{text}</div>
      </div>
    </AbsoluteFill>
  );
};

/** 마지막 컷 — CTA 배지 + 쿠팡 파트너스 광고표시 (법적 고지) */
const CTA = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const s = spring({ frame, fps, config: { damping: 180, mass: 0.6 } });
  return (
    <AbsoluteFill style={{ justifyContent: "flex-end", alignItems: "center", paddingBottom: 210 }}>
      <div style={{
        fontFamily: LEGAL, fontSize: 30, fontWeight: 500, color: "rgba(255,255,255,.92)",
        background: "rgba(0,0,0,.62)", padding: "14px 26px", borderRadius: 10,
        textAlign: "center", lineHeight: 1.5, maxWidth: 880,
        transform: `scale(${interpolate(s, [0, 1], [0.94, 1])})`,
        opacity: interpolate(s, [0, 1], [0, 1]),
      }}>
        [광고] 쿠팡 파트너스 활동의 일환으로,<br />이에 따른 일정액의 수수료를 제공받습니다.
      </div>
    </AbsoluteFill>
  );
};

/** 상시 광고 표시 — 공정위 추천·보증 심사지침. 영상 내내 보여야 한다.
 *  위치·크기는 remix.json 의 adBadge 로 조절한다(코드를 고치지 않는다). */
const AdBadge = ({ cfg }) => {
  const pos = cfg.position ?? "topRight";
  const m = cfg.margin ?? 44;
  const side = pos.toLowerCase().includes("left")
    ? { left: m } : { right: m };
  const vert = pos.toLowerCase().includes("bottom")
    ? { bottom: m } : { top: m };
  return (
    <div style={{
      position: "absolute", ...side, ...vert,
      fontFamily: LEGAL,
      fontSize: cfg.size ?? 34,
      fontWeight: 600,
      color: `rgba(255,255,255,${cfg.textOpacity ?? 0.95})`,
      background: `rgba(0,0,0,${cfg.bgOpacity ?? 0.45})`,
      padding: "8px 16px",
      borderRadius: 8,
      letterSpacing: 1,
      lineHeight: 1,
      pointerEvents: "none",
    }}>
      {cfg.text ?? "광고"}
    </div>
  );
};

/** 오프닝 헤드라인 — 쇼핑 쇼츠가 앞부분에 크게 박는 문구.
 *  플랫폼이 영상 앞 프레임을 썸네일로 쓰므로 이게 곧 썸네일 문구다.
 *  따로 썸네일 이미지를 만들지 않는다.
 *  `|` 로 줄바꿈, `*강조*` 로 그 단어만 색을 준다.
 *  설정은 remix.json 의 headline (코드를 고치지 않는다). */
const Headline = ({ cfg }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const hold = Math.max(1, Math.round((cfg.sec ?? 3) * fps));
  const s = spring({ frame, fps, config: { damping: 200, mass: 0.6 } });
  const fade = interpolate(frame, [hold - 9, hold], [1, 0], {
    extrapolateLeft: "clamp", extrapolateRight: "clamp",
  });
  const style = cfg.style ?? "plain";
  const size = cfg.size ?? 118;
  const accent = cfg.accent ?? "#FFD84D";
  const boxColor = cfg.boxColor ?? "#16255C";
  const lines = String(cfg.text ?? "").split("|").map((l) => l.trim()).filter(Boolean);

  const base = {
    fontFamily: KR, fontSize: size, fontWeight: 400,
    lineHeight: 1.2, textAlign: "center", wordBreak: "keep-all", margin: 0,
  };
  const parts = (l) => l.split(/(\*[^*]+\*)/).filter(Boolean);
  const draw = (front, plainColor) =>
    lines.map((l, i) => (
      <div key={i}>
        {parts(l).map((part, j) =>
          part.startsWith("*") && part.endsWith("*") ? (
            <span key={j} style={front ? { color: accent } : undefined}>{part.slice(1, -1)}</span>
          ) : (
            <span key={j} style={front ? { color: plainColor } : undefined}>{part}</span>
          )
        )}
      </div>
    ));

  // 겹쳐 그리는 외곽선 방식 — 자막과 같은 기법
  const stroked = (plainColor, strokeW) => (
    <div style={{ position: "relative" }}>
      <div style={{
        ...base, color: "#000",
        WebkitTextStroke: `${strokeW}px #000`,
        filter: "drop-shadow(0 8px 18px rgba(0,0,0,.6))",
      }}>{draw(false)}</div>
      <div style={{ ...base, position: "absolute", left: 0, top: 0, right: 0 }}>
        {draw(true, plainColor)}
      </div>
    </div>
  );

  let body;
  if (style === "box") {
    body = (
      <div style={{
        background: boxColor, borderRadius: 22, padding: "26px 40px",
        boxShadow: "0 10px 30px rgba(0,0,0,.45)",
      }}>
        <div style={{ ...base, color: "#fff" }}>{draw(true, "#fff")}</div>
      </div>
    );
  } else if (style === "bar") {
    body = (
      <div style={{
        background: boxColor, width: 1080, padding: "30px 0",
        boxShadow: "0 8px 24px rgba(0,0,0,.4)",
      }}>
        <div style={{ ...base, color: "#fff" }}>{draw(true, "#fff")}</div>
      </div>
    );
  } else if (style === "fill") {
    body = stroked(accent, cfg.stroke ?? 22);
  } else {
    body = stroked("#fff", cfg.stroke ?? 22);
  }

  return (
    <AbsoluteFill style={{
      justifyContent: "flex-start", alignItems: "center",
      paddingTop: cfg.top ?? 330, opacity: fade,
    }}>
      <div style={{
        maxWidth: style === "bar" ? 1080 : 980,
        transform: `translateY(${interpolate(s, [0, 1], [-26, 0])}px) scale(${interpolate(s, [0, 1], [0.92, 1])})`,
      }}>
        {body}
      </div>
    </AbsoluteFill>
  );
};

export const Remix = ({ data }) => {
  const { fps } = useVideoConfig();
  const hl = data.headline ?? {};
  const cover = hl.text ? Math.round((hl.coverSec ?? 0) * fps) : 0;
  const coverCut = data.cuts[Math.max(0, Math.min((hl.cut ?? 1) - 1, data.cuts.length - 1))];
  return (
    <AbsoluteFill style={{ background: "#000" }}>
      {/* 커버 = 썸네일. 맨 앞에 잠깐 두면 플랫폼이 이 프레임을 썸네일로 잡고,
          본편이 시작되면 사라진다. 본편(음성·컷·자막)은 통째로 커버 뒤로 밀린다. */}
      {cover > 0 ? (
        <Sequence from={0} durationInFrames={cover}>
          <Shot cut={coverCut} durInFrames={cover} />
          <Headline cfg={{ ...hl, sec: 9999 }} />
        </Sequence>
      ) : null}

      <Sequence from={cover}>
        <Audio src={staticFile(data.narration)} />

        {data.cuts.map((cut, i) => {
          // from 과 dur 을 따로 반올림하면 서로 안 맞물려 경계에 1프레임 구멍이
          // 생기고, 그 프레임은 검게 렌더된다. 다음 컷의 시작 프레임에서 역산한다.
          const from = Math.round(cut.start * fps);
          const next = data.cuts[i + 1];
          const end = next
            ? Math.round(next.start * fps)
            : Math.round((cut.start + cut.dur) * fps);
          const dur = Math.max(1, end - from);
          return (
            <Sequence key={cut.id} from={from} durationInFrames={dur}>
              <Shot cut={cut} durInFrames={dur} />
              {cut.cta ? <CTA /> : null}
            </Sequence>
          );
        })}

        {/* 자막 — 나레이션 문장에서 잘라낸 조각을 음성 타이밍에 맞춰 표시 */}
        {(data.captions ?? []).map((c, i) => (
          <Sequence
            key={`cap${i}`}
            from={Math.round(c.start * fps)}
            durationInFrames={Math.max(1, Math.round((c.end - c.start) * fps))}
          >
            <Caption text={c.text} />
          </Sequence>
        ))}

        {/* 본편에도 문구를 얹고 싶을 때만. 기본은 커버에만 나온다. */}
        {hl.text && hl.inVideo ? (
          <Sequence from={0} durationInFrames={Math.max(1, Math.round((hl.sec ?? 3) * fps))}>
            <Headline cfg={hl} />
          </Sequence>
        ) : null}
      </Sequence>

      {/* 상시 광고 표시 — 커버 포함 전 구간 */}
      {data.adBadge === false ? null : <AdBadge cfg={data.adBadge ?? {}} />}
    </AbsoluteFill>
  );
};
