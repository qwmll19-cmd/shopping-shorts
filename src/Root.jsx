import { Composition } from "remotion";
import { Remix } from "./Remix.jsx";
import props from "../out/remotion-props.json";

// Remix.jsx 가 모듈 로딩 시점에 폰트를 읽으므로 그 전에 심어둔다
if (typeof window !== "undefined") {
  window.__SHORTS_FONT__ = props.font ?? "Jua";
  window.__SHORTS_CAPTION__ = props.caption ?? {};
}

export const RemotionRoot = () => (
  <Composition
    id="Remix"
    component={Remix}
    durationInFrames={props.durationInFrames}
    fps={props.fps}
    width={props.width}
    height={props.height}
    defaultProps={{ data: props }}
  />
);
