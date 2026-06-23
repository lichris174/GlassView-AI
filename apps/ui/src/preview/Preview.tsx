import { useEffect, useRef, useState, type ReactNode } from "react";
import { GlassSurface } from "../glass/GlassSurface";
import "./preview.css";

/** Drag handle: lets a panel be moved across the backdrop with the mouse. */
function useDrag(initial: { x: number; y: number }) {
  const [pos, setPos] = useState(initial);
  const dragging = useRef<{ dx: number; dy: number } | null>(null);

  const onPointerDown = (e: React.PointerEvent) => {
    dragging.current = { dx: e.clientX - pos.x, dy: e.clientY - pos.y };
    (e.target as HTMLElement).setPointerCapture(e.pointerId);
  };
  useEffect(() => {
    const move = (e: PointerEvent) => {
      if (!dragging.current) return;
      setPos({ x: e.clientX - dragging.current.dx, y: e.clientY - dragging.current.dy });
    };
    const up = () => (dragging.current = null);
    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", up);
    return () => {
      window.removeEventListener("pointermove", move);
      window.removeEventListener("pointerup", up);
    };
  }, []);
  return { pos, onPointerDown };
}

function Slider({
  label,
  value,
  min,
  max,
  step,
  unit,
  onChange,
}: {
  label: string;
  value: number;
  min: number;
  max: number;
  step: number;
  unit?: string;
  onChange: (v: number) => void;
}) {
  return (
    <label className="ctrl">
      <span className="ctrl__label">{label}</span>
      <input
        type="range"
        min={min}
        max={max}
        step={step}
        value={value}
        onChange={(e) => onChange(Number(e.target.value))}
      />
      <span className="ctrl__value">
        {value}
        {unit}
      </span>
    </label>
  );
}

const WALLPAPERS = ["wp-aurora", "wp-sunset", "wp-mono"];

export default function Preview() {
  const [blur, setBlur] = useState(22);
  const [saturate, setSaturate] = useState(175);
  const [tint, setTint] = useState(45);
  const [grain, setGrain] = useState(3.5);
  const [wp, setWp] = useState(0);

  // Push the live values onto the same CSS variables the real app uses.
  useEffect(() => {
    const root = document.documentElement.style;
    root.setProperty("--glass-blur", `${blur}px`);
    root.setProperty("--glass-saturate", `${saturate}%`);
    root.setProperty("--glass-tint", `rgba(20, 22, 30, ${tint / 100})`);
    root.setProperty("--glass-tint-strong", `rgba(24, 26, 36, ${Math.min(tint / 100 + 0.18, 1)})`);
    root.setProperty("--glass-grain", `${grain / 100}`);
  }, [blur, saturate, tint, grain]);

  const panel = useDrag({ x: 220, y: 150 });
  const capsule = useDrag({ x: 360, y: 470 });

  return (
    <div className={`preview ${WALLPAPERS[wp]}`}>
      <DesktopBackdrop />

      <div
        className="floating"
        style={{ left: panel.pos.x, top: panel.pos.y }}
        onPointerDown={panel.onPointerDown}
      >
        <GlassSurface style={{ width: 420 }}>
          <div className="demo-panel">
            <div className="demo-panel__bar">
              <span>GlassView</span>
              <span className="demo-panel__model">qwen3-vl:8b</span>
            </div>
            <p className="demo-panel__msg demo-panel__msg--in">
              What is on my screen right now?
            </p>
            <p className="demo-panel__msg demo-panel__msg--out">
              A code editor with a Rust file open and a terminal running the dev server.
              Drag this panel over the wallpaper to see the glass refract the content behind it.
            </p>
            <div className="demo-panel__composer">Ask about your screen...</div>
          </div>
        </GlassSurface>
      </div>

      <div
        className="floating"
        style={{ left: capsule.pos.x, top: capsule.pos.y }}
        onPointerDown={capsule.onPointerDown}
      >
        <GlassSurface variant="capsule" style={{ width: 320 }}>
          <div className="demo-capsule">
            <span className="demo-capsule__dot" />
            <span>Ask GlassView...</span>
            <kbd>Ctrl Alt M</kbd>
          </div>
        </GlassSurface>
      </div>

      <GlassSurface className="controls" style={{ width: 260 }}>
        <div className="controls__inner">
          <div className="controls__title">Glass tuning</div>
          <Slider label="Blur" value={blur} min={0} max={48} step={1} unit="px" onChange={setBlur} />
          <Slider label="Saturate" value={saturate} min={100} max={240} step={5} unit="%" onChange={setSaturate} />
          <Slider label="Tint" value={tint} min={0} max={90} step={1} unit="%" onChange={setTint} />
          <Slider label="Grain" value={grain} min={0} max={10} step={0.5} unit="%" onChange={setGrain} />
          <button className="controls__wp" onClick={() => setWp((w) => (w + 1) % WALLPAPERS.length)}>
            Change wallpaper
          </button>
          <p className="controls__note">
            Real desktop see-through is Tauri-only. This preview fakes the backdrop so the
            material can be judged against content.
          </p>
        </div>
      </GlassSurface>
    </div>
  );
}

/** Fake desktop content so the glass has something detailed to blur over. */
function DesktopBackdrop() {
  const cards: ReactNode[] = [
    <BackdropCard key="a" cls="card--editor" title="main.rs">
      <pre>{`fn main() {\n  let app = tauri::Builder\n    ::default()\n    .run(ctx);\n}`}</pre>
    </BackdropCard>,
    <BackdropCard key="b" cls="card--photo" title="Photos" />,
    <BackdropCard key="c" cls="card--term" title="Terminal">
      <pre>{`> cargo tauri dev\n  Compiling glassview\n  Running on :1420`}</pre>
    </BackdropCard>,
  ];
  return <div className="backdrop">{cards}</div>;
}

function BackdropCard({
  cls,
  title,
  children,
}: {
  cls: string;
  title: string;
  children?: ReactNode;
}) {
  return (
    <div className={`card ${cls}`}>
      <div className="card__bar">{title}</div>
      <div className="card__body">{children}</div>
    </div>
  );
}
