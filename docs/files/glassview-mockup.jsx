import { useState, useEffect, useRef, useCallback } from "react";

// ── Icons ──────────────────────────────────────────────────────────────────
const Icon = ({ d, size = 15, stroke = "currentColor", sw = 1.5, fill = "none" }) => (
  <svg width={size} height={size} viewBox="0 0 16 16" fill={fill}>
    <path d={d} stroke={stroke} strokeWidth={sw} strokeLinecap="round" strokeLinejoin="round" fill={fill} />
  </svg>
);
const Icons = {
  chat:     "M2 4.5C2 3.67 2.67 3 3.5 3h9C13.33 3 14 3.67 14 4.5v6c0 .83-.67 1.5-1.5 1.5H9l-3 2v-2H3.5C2.67 14 2 13.33 2 12.5v-8z",
  region:   "M2 5V3.5C2 2.67 2.67 2 3.5 2H5M11 2h1.5C13.33 2 14 2.67 14 3.5V5M14 11v1.5c0 .83-.67 1.5-1.5 1.5H11M5 14H3.5C2.67 14 2 13.33 2 12.5V11M5.5 8h5M8 5.5v5",
  voice:    "M8 2.5a2 2 0 0 1 2 2v3.5a2 2 0 0 1-4 0V4.5a2 2 0 0 1 2-2zM4 8a4 4 0 0 0 8 0M8 12v1.5M6 13.5h4",
  history:  "M8 14A6 6 0 1 0 2.5 8.5M2 5v3.5H5.5M8 5v3.5l2.5 2",
  settings: "M8 10a2 2 0 1 0 0-4 2 2 0 0 0 0 4zM8 1v1.5M8 13.5V15M1 8h1.5M13.5 8H15M2.93 2.93l1.06 1.06M12.01 12.01l1.06 1.06M2.93 13.07l1.06-1.06M12.01 3.99l1.06-1.06",
  close:    "M4 4l8 8M12 4l-8 8",
  send:     "M8 13V3M3 8l5-5 5 5",
  mic:      "M8 2.5a2 2 0 0 1 2 2v3.5a2 2 0 0 1-4 0V4.5a2 2 0 0 1 2-2z",
  attach:   "M13.5 8.5l-6 6a3.5 3.5 0 0 1-4.95-4.95l6.36-6.36a2 2 0 0 1 2.83 2.83L5.88 12.4a.5.5 0 0 1-.71-.71L11 6",
  warning:  "M8 2L1.5 13h13L8 2zM8 6v4M8 11.5v.5",
  search:   "M7 12A5 5 0 1 0 7 2a5 5 0 0 0 0 10zM14 14l-3-3",
  file:     "M4 2h6l4 4v9a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1V3a1 1 0 0 1 1-1zM10 2v4h4",
  chevdown: "M4 6l4 4 4-4",
  key:      "M11.5 2a2.5 2.5 0 1 0 0 5 2.5 2.5 0 0 0 0-5zM6.5 6.5L2 11v2h2v-1.5H5.5V10H7l1-1-1.5-1.5",
  moon:     "M12 12.5A6 6 0 0 1 6.5 3 6 6 0 1 0 12 12.5z",
  sun:      "M8 11a3 3 0 1 0 0-6 3 3 0 0 0 0 6zM8 1v1.5M8 13.5V15M1 8h1.5M13.5 8H15M2.93 2.93l1.06 1.06M12.01 12.01l1.06 1.06M2.93 13.07l1.06-1.06M12.01 3.99l1.06-1.06",
};

const TOOLS = [
  { id: "chat",     label: "Chat",       kbd: "C", icon: "chat"     },
  { id: "region",   label: "Region",     kbd: "R", icon: "region"   },
  { id: "voice",    label: "Voice",      kbd: "V", icon: "voice"    },
  { id: "history",  label: "Past Chats", kbd: "H", icon: "history"  },
  { id: "settings", label: "Settings",   kbd: "S", icon: "settings" },
];

const FAKE_RESPONSE = "The error on line 47 is a null pointer dereference — `config` isn't initialized before `load()` is called. Add `Config.init()` before that call, or guard with a null check on `.settings`.";
const FAKE_CHATS = [
  { id: 1, title: "Debug session — main.py",  time: "2m ago",    preview: "The error on line 47 is a null pointer..." },
  { id: 2, title: "SLAM robot Nav2 config",   time: "1h ago",    preview: "Your costmap params look right but the..." },
  { id: 3, title: "FastAPI endpoint design",  time: "3h ago",    preview: "For streaming you'll want Server-Sent..." },
  { id: 4, title: "GPU fluid sim CUDA",       time: "Yesterday", preview: "The warp divergence is coming from..." },
  { id: 5, title: "Raft KV store — leader",   time: "2d ago",    preview: "The election timeout looks too short..." },
];

// ── Two-tone G logo ────────────────────────────────────────────────────────
function GLogo({ size, animate = false }) {
  const c = size / 2, r = size * 0.315, sw = size * 0.072;
  const openAngle = -0.22, sweep = 1.78 * Math.PI;
  const startA = openAngle, endA = openAngle + sweep;
  const ax1 = c + r * Math.cos(startA), ay1 = c + r * Math.sin(startA);
  const ax2 = c + r * Math.cos(endA),   ay2 = c + r * Math.sin(endA);
  const splitY = c + size * 0.04;
  const uid = `g${size}${animate}`;
  const ghostColor = "rgba(255,255,255,0.13)";
  const dx = size * 0.08, dy = size * 0.07;
  const fgPath  = `M ${ax1.toFixed(2)} ${ay1.toFixed(2)} A ${r} ${r} 0 1 1 ${ax2.toFixed(2)} ${ay2.toFixed(2)} L ${c.toFixed(2)} ${ay2.toFixed(2)}`;
  const gxPath  = `M ${(ax1+dx).toFixed(2)} ${(ay1+dy).toFixed(2)} A ${r} ${r} 0 1 1 ${(ax2+dx).toFixed(2)} ${(ay2+dy).toFixed(2)} L ${(c+dx).toFixed(2)} ${(ay2+dy).toFixed(2)}`;

  return (
    <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} fill="none">
      <defs>
        <clipPath id={`t-${uid}`}><rect x={0} y={0} width={size} height={splitY}/></clipPath>
        <clipPath id={`b-${uid}`}><rect x={0} y={splitY} width={size} height={size}/></clipPath>
      </defs>
      <path d={gxPath} stroke={ghostColor} strokeWidth={sw} strokeLinecap="round"/>
      <path d={fgPath} stroke="#0A84FF" strokeWidth={sw} strokeLinecap="round" clipPath={`url(#t-${uid})`}/>
      <path d={fgPath} stroke="rgba(255,255,255,0.88)" strokeWidth={sw} strokeLinecap="round" clipPath={`url(#b-${uid})`}/>
      {animate && (
        <circle cx={c} cy={c} r={size*0.46} stroke="rgba(10,132,255,0.5)" strokeWidth={size*0.04} fill="none">
          <animate attributeName="r" values={`${size*0.38};${size*0.48};${size*0.38}`} dur="1.6s" repeatCount="indefinite"/>
          <animate attributeName="opacity" values="0.6;0;0.6" dur="1.6s" repeatCount="indefinite"/>
        </circle>
      )}
    </svg>
  );
}

// ── Theme tokens ───────────────────────────────────────────────────────────
const T = {
  dark: {
    bg:           "#0d0d0d",
    winBg:        "rgba(26,26,28,.96)",
    winBar:       "rgba(38,38,40,.95)",
    winBorder:    "rgba(255,255,255,.07)",
    pillBg:       "rgba(20,20,22,.88)",
    pillBorder:   "rgba(255,255,255,.11)",
    panelBg:      "rgba(18,18,20,.92)",
    panelBorder:  "rgba(255,255,255,.09)",
    ctxBg:        "rgba(255,255,255,.04)",
    ctxBorder:    "rgba(255,255,255,.07)",
    inputBg:      "rgba(255,255,255,.06)",
    inputBorder:  "rgba(255,255,255,.09)",
    inputFocus:   "rgba(10,132,255,.4)",
    bubbleAiBg:   "rgba(255,255,255,.07)",
    bubbleAiBorder:"rgba(255,255,255,.08)",
    toolColor:    "rgba(255,255,255,.45)",
    toolHover:    "rgba(255,255,255,.07)",
    titleColor:   "rgba(255,255,255,.3)",
    textPrimary:  "rgba(255,255,255,.85)",
    textSecondary:"rgba(255,255,255,.4)",
    textFaint:    "rgba(255,255,255,.2)",
    sepColor:     "rgba(255,255,255,.09)",
    closeBg:      "rgba(255,255,255,.07)",
    closeHover:   "rgba(255,255,255,.13)",
    histHover:    "rgba(255,255,255,.05)",
    settingRowBg: "rgba(255,255,255,.04)",
    settingRowBorder:"rgba(255,255,255,.07)",
    fakeLine:     "rgba(255,255,255,.05)",
    fakeBar:      "rgba(44,44,46,.9)",
    fakeBarBorder:"rgba(255,255,255,.06)",
    fakeTitleColor:"rgba(255,255,255,.3)",
    errorBg:      "rgba(255,69,58,.08)",
    errorBorder:  "rgba(255,69,58,.2)",
    errorText:    "rgba(255,69,58,.9)",
    errorSub:     "rgba(255,69,58,.5)",
    warnIcon:     "#FF453A",
    bubbleAiText: "rgba(255,255,255,.82)",
    shadow:       "0 24px 64px rgba(0,0,0,.55)",
  },
  light: {
    bg:           "#e8e8ed",
    winBg:        "rgba(252,252,254,.98)",
    winBar:       "rgba(242,242,247,.98)",
    winBorder:    "rgba(0,0,0,.08)",
    pillBg:       "rgba(255,255,255,.82)",
    pillBorder:   "rgba(0,0,0,.1)",
    panelBg:      "rgba(255,255,255,.92)",
    panelBorder:  "rgba(0,0,0,.08)",
    ctxBg:        "rgba(0,0,0,.03)",
    ctxBorder:    "rgba(0,0,0,.07)",
    inputBg:      "rgba(0,0,0,.04)",
    inputBorder:  "rgba(0,0,0,.08)",
    inputFocus:   "rgba(10,132,255,.4)",
    bubbleAiBg:   "rgba(0,0,0,.04)",
    bubbleAiBorder:"rgba(0,0,0,.06)",
    toolColor:    "rgba(0,0,0,.4)",
    toolHover:    "rgba(0,0,0,.05)",
    titleColor:   "rgba(0,0,0,.28)",
    textPrimary:  "rgba(0,0,0,.82)",
    textSecondary:"rgba(0,0,0,.4)",
    textFaint:    "rgba(0,0,0,.22)",
    sepColor:     "rgba(0,0,0,.08)",
    closeBg:      "rgba(0,0,0,.06)",
    closeHover:   "rgba(0,0,0,.1)",
    histHover:    "rgba(0,0,0,.04)",
    settingRowBg: "rgba(0,0,0,.03)",
    settingRowBorder:"rgba(0,0,0,.07)",
    fakeLine:     "rgba(0,0,0,.07)",
    fakeBar:      "rgba(236,236,241,.98)",
    fakeBarBorder:"rgba(0,0,0,.06)",
    fakeTitleColor:"rgba(0,0,0,.3)",
    errorBg:      "rgba(255,69,58,.06)",
    errorBorder:  "rgba(255,69,58,.18)",
    errorText:    "rgba(200,40,30,.9)",
    errorSub:     "rgba(200,40,30,.55)",
    warnIcon:     "#E03025",
    bubbleAiText: "rgba(0,0,0,.78)",
    shadow:       "0 12px 40px rgba(0,0,0,.15)",
  }
};

// ── Styles factory ─────────────────────────────────────────────────────────
const makeCSS = (t) => `
* { box-sizing: border-box; margin: 0; padding: 0; }
body {
  font-family: -apple-system, BlinkMacSystemFont, 'SF Pro Text', 'Helvetica Neue', sans-serif;
  background: ${t.bg};
  min-height: 100vh;
  overflow: hidden;
  user-select: none;
  transition: background .3s;
}

.fake-win {
  position: fixed; top: 50%; left: 50%;
  transform: translate(-50%, -50%);
  width: 600px; height: 360px;
  background: ${t.winBg};
  border-radius: 12px;
  border: 1px solid ${t.winBorder};
  box-shadow: ${t.shadow};
  display: flex; flex-direction: column; overflow: hidden;
}
.fake-bar {
  height: 36px; background: ${t.fakeBar};
  border-bottom: 1px solid ${t.fakeBarBorder};
  display: flex; align-items: center;
  padding: 0 12px; gap: 7px; flex-shrink: 0;
}
.tl { width: 12px; height: 12px; border-radius: 50%; }
.tl-r{background:#FF5F57}.tl-y{background:#FFBD2E}.tl-g{background:#28CA41}
.fake-title { font-size:12px;font-weight:500;color:${t.fakeTitleColor};margin:0 auto;letter-spacing:-.01em; }
.fake-body { flex:1;padding:18px 20px;display:flex;flex-direction:column;gap:7px; }
.fl { height:9px;background:${t.fakeLine};border-radius:3px; }

/* ── Pill ── */
.gv-wrap { position:fixed;z-index:500;display:flex;flex-direction:column;align-items:center;gap:10px; }

.gv-pill {
  display:flex;align-items:center;
  background: ${t.pillBg};
  backdrop-filter: blur(32px) saturate(180%);
  -webkit-backdrop-filter: blur(32px) saturate(180%);
  border: 1px solid ${t.pillBorder};
  border-radius: 100px;
  box-shadow: ${t.shadow}, 0 1px 0 rgba(255,255,255,.06) inset;
  cursor: grab; overflow: hidden;
}
.gv-pill:active { cursor: grabbing; }

.gv-logo-btn {
  width:40px;height:40px;
  display:flex;align-items:center;justify-content:center;
  cursor:pointer;border:none;background:none;flex-shrink:0;
  transition: opacity .15s;
}
.gv-logo-btn:hover { opacity: .75; }

.gv-tools {
  display:flex;align-items:center;
  overflow:hidden;max-width:0;opacity:0;
  transition: max-width .3s cubic-bezier(.34,1.2,.64,1), opacity .2s;
}
.gv-tools.open { max-width:240px;opacity:1; }

.gv-sep { width:1px;height:16px;background:${t.sepColor};flex-shrink:0; }

.gv-tool-btn {
  position:relative;width:36px;height:36px;
  display:flex;align-items:center;justify-content:center;
  border:none;background:none;cursor:pointer;
  color:${t.toolColor};border-radius:100px;
  transition:color .15s,background .15s;flex-shrink:0;
}
.gv-tool-btn:hover { color:${t.textPrimary};background:${t.toolHover}; }
.gv-tool-btn.active { color:#0A84FF; }
.gv-tool-btn.active:hover { color:#3BAAFF;background:rgba(10,132,255,.1); }

.gv-tip {
  position:absolute;bottom:calc(100% + 8px);left:50%;transform:translateX(-50%);
  background:${t.panelBg};border:1px solid ${t.panelBorder};
  border-radius:7px;padding:5px 9px;white-space:nowrap;
  pointer-events:none;opacity:0;transition:opacity .12s;
  display:flex;align-items:center;gap:6px;
  box-shadow:${t.shadow};z-index:10;
}
.gv-tool-btn:hover .gv-tip { opacity:1; }
.gv-tip-label { font-size:11px;font-weight:500;color:${t.textPrimary};letter-spacing:-.01em; }
.gv-tip-kbd {
  font-size:10px;color:${t.textFaint};
  background:${t.toolHover};border:1px solid ${t.sepColor};
  border-radius:4px;padding:1px 5px;
}

/* ── Panel ── */
.gv-panel {
  width:340px;
  background:${t.panelBg};
  backdrop-filter:blur(48px) saturate(200%);
  -webkit-backdrop-filter:blur(48px) saturate(200%);
  border:1px solid ${t.panelBorder};
  border-radius:16px;
  box-shadow:${t.shadow};
  overflow:hidden;
  transform-origin:bottom center;
  animation:panelIn .28s cubic-bezier(.34,1.4,.64,1) forwards;
}
@keyframes panelIn {
  from{opacity:0;transform:scale(.92) translateY(6px)}
  to{opacity:1;transform:scale(1) translateY(0)}
}

.gv-panel-hdr {
  display:flex;align-items:center;justify-content:space-between;
  padding:13px 14px 0;
}
.gv-panel-title {
  font-size:11px;font-weight:600;
  color:${t.titleColor};letter-spacing:.06em;text-transform:uppercase;
}
.gv-close-btn {
  width:20px;height:20px;border-radius:50%;
  background:${t.closeBg};border:none;cursor:pointer;
  display:flex;align-items:center;justify-content:center;
  color:${t.textSecondary};
  transition:background .15s,color .15s;
}
.gv-close-btn:hover { background:${t.closeHover};color:${t.textPrimary}; }

/* Context strip */
.gv-ctx {
  margin:11px 14px 0;padding:8px 10px;
  background:${t.ctxBg};border:1px solid ${t.ctxBorder};
  border-radius:10px;display:flex;align-items:center;gap:8px;
}
.gv-ctx-thumb {
  width:38px;height:24px;background:${t.winBg};
  border-radius:4px;border:1px solid ${t.ctxBorder};
  flex-shrink:0;display:flex;flex-direction:column;gap:2px;padding:3px;
}
.gv-ctx-line { height:2px;background:${t.fakeLine};border-radius:1px; }
.gv-ctx-meta { flex:1;min-width:0; }
.gv-ctx-app { font-size:11px;font-weight:500;color:${t.textSecondary};letter-spacing:-.01em; }
.gv-ctx-sub { font-size:10px;color:${t.textFaint};margin-top:1px; }

/* File drop zone */
.gv-drop {
  margin:10px 14px 0;padding:8px 12px;
  border:1.5px dashed ${t.sepColor};
  border-radius:10px;
  display:flex;align-items:center;gap:8px;
  cursor:pointer;transition:border-color .15s,background .15s;
}
.gv-drop:hover,.gv-drop.over { border-color:#0A84FF;background:rgba(10,132,255,.05); }
.gv-drop-label { font-size:11px;color:${t.textFaint};letter-spacing:-.01em; }
.gv-drop-label span { color:#0A84FF; }
.gv-file-chip {
  display:flex;align-items:center;gap:5px;
  padding:3px 8px;border-radius:6px;
  background:rgba(10,132,255,.1);border:1px solid rgba(10,132,255,.2);
  font-size:10px;color:#3BAAFF;font-weight:500;
}
.gv-file-rm { background:none;border:none;cursor:pointer;color:rgba(10,132,255,.5);font-size:10px;padding:0 0 0 2px; }

/* Messages */
.gv-msgs {
  padding:11px 14px 0;display:flex;flex-direction:column;gap:8px;
  max-height:190px;overflow-y:auto;
}
.gv-msgs::-webkit-scrollbar{width:0}
.gv-msg{display:flex;flex-direction:column;}
.gv-msg-u{align-items:flex-end}.gv-msg-a{align-items:flex-start}
.gv-bubble {
  max-width:90%;padding:8px 11px;border-radius:12px;
  font-size:13px;line-height:1.5;letter-spacing:-.01em;
}
.gv-bubble-u { background:#0A84FF;color:#fff;border-bottom-right-radius:4px; }
.gv-bubble-a {
  background:${t.bubbleAiBg};border:1px solid ${t.bubbleAiBorder};
  color:${t.bubbleAiText};border-bottom-left-radius:4px;
}
.gv-cursor {
  display:inline-block;width:2px;height:13px;
  background:${t.textSecondary};margin-left:2px;vertical-align:middle;
  animation:blink .9s step-end infinite;
}
@keyframes blink{0%,100%{opacity:1}50%{opacity:0}}
.thinking-dots{display:flex;gap:3px;align-items:center;}
.td{width:5px;height:5px;border-radius:50%;background:${t.textFaint};}
.td:nth-child(1){animation:db 1.2s 0s ease-in-out infinite}
.td:nth-child(2){animation:db 1.2s .15s ease-in-out infinite}
.td:nth-child(3){animation:db 1.2s .3s ease-in-out infinite}
@keyframes db{0%,60%,100%{transform:translateY(0);opacity:.3}30%{transform:translateY(-4px);opacity:.9}}

/* Input row */
.gv-input-row {
  display:flex;align-items:center;gap:7px;
  padding:11px 14px 13px;
}
.gv-input {
  flex:1;background:${t.inputBg};border:1px solid ${t.inputBorder};
  border-radius:10px;padding:8px 11px;
  font-size:13px;font-family:inherit;color:${t.textPrimary};
  outline:none;letter-spacing:-.01em;
  transition:border-color .15s,background .15s;
}
.gv-input::placeholder{color:${t.textFaint}}
.gv-input:focus{border-color:${t.inputFocus};background:${t.ctxBg}}
.gv-send {
  width:30px;height:30px;border-radius:8px;
  background:#0A84FF;border:none;cursor:pointer;
  display:flex;align-items:center;justify-content:center;flex-shrink:0;
  transition:background .15s,transform .15s;
  box-shadow:0 2px 8px rgba(10,132,255,.35);
}
.gv-send:hover{background:#2196ff;transform:scale(1.06)}
.gv-send:disabled{opacity:.35;cursor:default;transform:none}

/* Attach btn in input row */
.gv-attach-btn {
  width:30px;height:30px;border-radius:8px;
  background:${t.ctxBg};border:1px solid ${t.ctxBorder};
  cursor:pointer;display:flex;align-items:center;justify-content:center;
  flex-shrink:0;color:${t.textSecondary};
  transition:background .15s,color .15s;
}
.gv-attach-btn:hover{background:${t.toolHover};color:${t.textPrimary}}

/* Error state */
.gv-error {
  margin:14px;padding:14px;
  background:${t.errorBg};border:1px solid ${t.errorBorder};
  border-radius:12px;display:flex;flex-direction:column;gap:8px;
}
.gv-error-hdr{display:flex;align-items:center;gap:8px;}
.gv-error-title{font-size:13px;font-weight:600;color:${t.errorText};letter-spacing:-.01em;}
.gv-error-body{font-size:12px;color:${t.errorSub};line-height:1.5;letter-spacing:-.01em;}
.gv-error-btn {
  align-self:flex-start;padding:6px 12px;
  background:${t.errorBorder};border:1px solid ${t.errorBorder};
  border-radius:8px;font-size:11px;font-weight:500;font-family:inherit;
  color:${t.errorText};cursor:pointer;transition:opacity .15s;
}
.gv-error-btn:hover{opacity:.75}

/* Voice */
.gv-voice{display:flex;flex-direction:column;align-items:center;padding:28px 14px 22px;gap:14px;}
.voice-ring{position:relative;width:72px;height:72px;display:flex;align-items:center;justify-content:center;}
.vring{position:absolute;inset:0;border-radius:50%;border:1.5px solid rgba(10,132,255,.3);}
.vring:nth-child(1){animation:rp 1.8s 0s ease-in-out infinite}
.vring:nth-child(2){animation:rp 1.8s .6s ease-in-out infinite}
.vring:nth-child(3){animation:rp 1.8s 1.2s ease-in-out infinite}
@keyframes rp{0%,100%{transform:scale(1);opacity:.3}50%{transform:scale(1.2);opacity:.7}}
.voice-btn {
  width:52px;height:52px;border-radius:50%;
  background:rgba(10,132,255,.12);border:1.5px solid rgba(10,132,255,.35);
  display:flex;align-items:center;justify-content:center;
  color:#0A84FF;cursor:pointer;z-index:1;
  transition:background .15s,border-color .15s;
}
.voice-btn.rec{background:rgba(255,69,58,.12);border-color:rgba(255,69,58,.4);color:#FF453A;animation:vp .8s ease-in-out infinite}
@keyframes vp{0%,100%{transform:scale(1)}50%{transform:scale(1.06)}}
.voice-transcript{font-size:13px;color:${t.textSecondary};text-align:center;letter-spacing:-.01em;line-height:1.5;min-height:36px;}
.voice-label{font-size:11px;color:${t.textFaint};letter-spacing:-.01em;}

/* History */
.gv-hist-search {
  margin:11px 14px 0;
  background:${t.inputBg};border:1px solid ${t.inputBorder};
  border-radius:9px;padding:7px 11px;
  font-size:12px;font-family:inherit;color:${t.textPrimary};outline:none;
  letter-spacing:-.01em;
  display:block;width:calc(100% - 28px);
}
.gv-hist-search::placeholder{color:${t.textFaint}}
.gv-hist-list{padding:8px;display:flex;flex-direction:column;gap:2px;}
.gv-hist-item{
  padding:8px;border-radius:8px;cursor:pointer;
  transition:background .12s;display:flex;flex-direction:column;gap:2px;
}
.gv-hist-item:hover{background:${t.histHover}}
.gv-hist-row{display:flex;align-items:baseline;justify-content:space-between;gap:8px;}
.gv-hist-title{font-size:12px;font-weight:500;color:${t.textSecondary};letter-spacing:-.01em;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;flex:1;}
.gv-hist-time{font-size:10px;color:${t.textFaint};flex-shrink:0;}
.gv-hist-preview{font-size:11px;color:${t.textFaint};white-space:nowrap;overflow:hidden;text-overflow:ellipsis;}

/* Settings */
.gv-settings{padding:13px;display:flex;flex-direction:column;gap:12px;max-height:360px;overflow-y:auto;}
.gv-settings::-webkit-scrollbar{width:0}
.gv-sg{display:flex;flex-direction:column;gap:6px;}
.gv-sg-label{font-size:10px;font-weight:600;color:${t.textFaint};letter-spacing:.07em;text-transform:uppercase;padding:0 2px;}
.gv-sr{
  display:flex;align-items:center;justify-content:space-between;
  padding:8px 10px;
  background:${t.settingRowBg};border:1px solid ${t.settingRowBorder};
  border-radius:9px;gap:8px;
}
.gv-sr-name{font-size:12px;color:${t.textSecondary};letter-spacing:-.01em;}
.gv-sr-val{font-size:11px;color:${t.textFaint};}
.gv-toggle{
  width:32px;height:18px;border-radius:100px;
  background:${t.sepColor};position:relative;cursor:pointer;
  transition:background .2s;flex-shrink:0;border:none;
}
.gv-toggle.on{background:#0A84FF;}
.gv-toggle::after{
  content:'';position:absolute;top:2px;left:2px;
  width:14px;height:14px;border-radius:50%;background:#fff;
  transition:transform .2s cubic-bezier(.34,1.56,.64,1);
  box-shadow:0 1px 4px rgba(0,0,0,.3);
}
.gv-toggle.on::after{transform:translateX(14px)}
.gv-api-input {
  flex:1;background:${t.inputBg};border:1px solid ${t.inputBorder};
  border-radius:7px;padding:5px 9px;
  font-size:11px;font-family:inherit;color:${t.textPrimary};
  outline:none;letter-spacing:-.01em;min-width:0;
}
.gv-api-input::placeholder{color:${t.textFaint}}
.gv-api-input:focus{border-color:${t.inputFocus}}
.gv-api-badge {
  font-size:9px;font-weight:600;letter-spacing:.05em;text-transform:uppercase;
  padding:2px 6px;border-radius:4px;flex-shrink:0;
}
.gv-api-badge.ollama{background:rgba(52,199,89,.12);color:#34C759;border:1px solid rgba(52,199,89,.2);}
.gv-api-badge.openai{background:rgba(10,132,255,.12);color:#0A84FF;border:1px solid rgba(10,132,255,.2);}
.gv-api-badge.anthropic{background:rgba(242,169,59,.12);color:#F2A93B;border:1px solid rgba(242,169,59,.2);}
.gv-kbd-input {
  width:90px;background:${t.inputBg};border:1px solid ${t.inputBorder};
  border-radius:7px;padding:5px 9px;text-align:center;
  font-size:11px;font-family:inherit;color:${t.textPrimary};
  outline:none;
}
.gv-kbd-input:focus{border-color:${t.inputFocus}}

/* Region overlay */
.region-overlay{position:fixed;inset:0;z-index:600;cursor:crosshair;}
.region-bg{position:absolute;inset:0;background:rgba(0,0,0,.48);}
.region-hint{
  position:absolute;top:50%;left:50%;transform:translate(-50%,-50%);
  background:${t.panelBg};backdrop-filter:blur(24px);
  border:1px solid ${t.panelBorder};border-radius:12px;
  padding:13px 20px;text-align:center;pointer-events:none;
  box-shadow:${t.shadow};
}
.region-hint-t{font-size:14px;font-weight:600;color:${t.textPrimary};letter-spacing:-.02em;}
.region-hint-s{font-size:11px;color:${t.textFaint};margin-top:3px;}
.region-sel{
  position:absolute;border:2px solid #0A84FF;
  background:rgba(10,132,255,.08);border-radius:4px;
  box-shadow:0 0 0 1px rgba(10,132,255,.25);
}
.region-cancel {
  position:absolute;bottom:24px;left:50%;transform:translateX(-50%);
  padding:7px 16px;background:${t.panelBg};backdrop-filter:blur(20px);
  border:1px solid ${t.panelBorder};border-radius:100px;
  font-size:12px;font-weight:500;color:${t.textSecondary};
  cursor:pointer;transition:all .15s;font-family:inherit;
}
.region-cancel:hover{color:${t.textPrimary}}

/* Demo bar */
.demo-bar {
  position:fixed;bottom:18px;left:50%;transform:translateX(-50%);
  display:flex;align-items:center;gap:4px;
  background:${t.panelBg};backdrop-filter:blur(20px);
  border:1px solid ${t.panelBorder};border-radius:100px;
  padding:5px 7px;z-index:1000;
}
.demo-btn {
  padding:4px 11px;border-radius:100px;border:none;
  font-size:11px;font-weight:500;font-family:inherit;
  cursor:pointer;color:${t.textFaint};background:transparent;
  transition:all .15s;letter-spacing:-.01em;
}
.demo-btn:hover{background:${t.toolHover};color:${t.textPrimary}}
.demo-btn.on{background:${t.histHover};color:${t.textPrimary}}
.demo-div{width:1px;height:12px;background:${t.sepColor};}

.divider{height:1px;background:${t.sepColor};margin:0 14px;}
`;

// ── Helpers ────────────────────────────────────────────────────────────────
const STREAM_TEXT = "The error on line 47 is a null pointer dereference — `config` isn't initialized before `load()` is called. Add `Config.init()` before that call, or guard with a null check on `.settings`.";

function detectProvider(key) {
  if (!key) return "ollama";
  if (key.startsWith("sk-ant-")) return "anthropic";
  if (key.startsWith("sk-")) return "openai";
  return "ollama";
}

export default function App() {
  const [theme, setTheme]           = useState("dark");
  const [expanded, setExpanded]     = useState(false);
  const [activeTool, setActiveTool] = useState(null);
  const [messages, setMessages]     = useState([]);
  const [inputVal, setInputVal]     = useState("");
  const [thinking, setThinking]     = useState(false);
  const [streamText, setStreamText] = useState("");
  const [streaming, setStreaming]   = useState(false);
  const [regionMode, setRegionMode] = useState(false);
  const [dragBox, setDragBox]       = useState(null);
  const [isDragging, setIsDragging] = useState(false);
  const [dragStart, setDragStart]   = useState(null);
  const [recording, setRecording]   = useState(false);
  const [transcript, setTranscript] = useState("");
  const [histSearch, setHistSearch] = useState("");
  const [attachedFile, setAttachedFile] = useState(null);
  const [dropOver, setDropOver]     = useState(false);
  const [hasNotif, setHasNotif]     = useState(false);
  const [apiKey, setApiKey]         = useState("");
  const [settings, setSettings]     = useState({
    privacy: true, autoContext: true, streaming: true,
    autoLaunch: false, closeOnBlur: true, theme: "dark",
    shortcut: "Ctrl+Shift+Space",
  });
  const [ollamaError, setOllamaError] = useState(false);

  // Draggable pos
  const [pos, setPos]               = useState({ x: null, y: null });
  const [draggingBar, setDraggingBar] = useState(false);
  const dragBarRef                  = useRef(null);
  const inputRef                    = useRef(null);
  const msgsRef                     = useRef(null);
  const streamRef                   = useRef(null);

  const t = T[theme];

  useEffect(() => {
    setPos({ x: window.innerWidth - 220, y: window.innerHeight - 80 });
  }, []);

  useEffect(() => {
    if (msgsRef.current) msgsRef.current.scrollTop = msgsRef.current.scrollHeight;
  }, [messages, streamText]);

  // Inject styles
  useEffect(() => {
    let el = document.getElementById("gv-styles");
    if (!el) { el = document.createElement("style"); el.id = "gv-styles"; document.head.appendChild(el); }
    el.textContent = makeCSS(t);
  }, [theme, t]);

  // Keyboard shortcuts
  useEffect(() => {
    const handler = (e) => {
      if (!expanded) return;
      if (e.target.tagName === "INPUT") return;
      const key = e.key.toUpperCase();
      const tool = TOOLS.find(t => t.kbd === key);
      if (tool) { e.preventDefault(); toggleTool(tool.id); }
      if (e.key === "Escape") { setActiveTool(null); }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [expanded]);

  // Bar drag
  const onBarMouseDown = useCallback((e) => {
    if (e.button !== 0) return;
    setDraggingBar(true);
    dragBarRef.current = { mx: e.clientX, my: e.clientY, px: pos.x, py: pos.y };
    e.preventDefault();
  }, [pos]);

  useEffect(() => {
    if (!draggingBar) return;
    const move = (e) => {
      const dx = e.clientX - dragBarRef.current.mx;
      const dy = e.clientY - dragBarRef.current.my;
      setPos({ x: dragBarRef.current.px + dx, y: dragBarRef.current.py + dy });
    };
    const up = () => setDraggingBar(false);
    window.addEventListener("mousemove", move);
    window.addEventListener("mouseup", up);
    return () => { window.removeEventListener("mousemove", move); window.removeEventListener("mouseup", up); };
  }, [draggingBar]);

  // Stream
  const simulateResponse = useCallback(() => {
    if (ollamaError) return;
    setThinking(true); setStreamText(""); clearInterval(streamRef.current);
    setTimeout(() => {
      setThinking(false); setStreaming(true);
      let i = 0;
      streamRef.current = setInterval(() => {
        i += Math.floor(Math.random() * 3) + 1;
        if (i >= STREAM_TEXT.length) {
          setStreamText(STREAM_TEXT); setStreaming(false);
          clearInterval(streamRef.current);
          setMessages(prev => [...prev, { role: "ai", text: STREAM_TEXT }]);
          setStreamText("");
          // notify if collapsed
          if (!expanded || !activeTool) setHasNotif(true);
        } else { setStreamText(STREAM_TEXT.slice(0, i)); }
      }, 24);
    }, 700);
  }, [ollamaError, expanded, activeTool]);

  const sendMessage = useCallback(() => {
    const msg = inputVal.trim();
    if (!msg || thinking || streaming) return;
    setInputVal("");
    setAttachedFile(null);
    setMessages(prev => [...prev, { role: "user", text: msg + (attachedFile ? ` [+ ${attachedFile}]` : "") }]);
    simulateResponse();
  }, [inputVal, thinking, streaming, attachedFile, simulateResponse]);

  // Region
  const onRegionDown = (e) => {
    if (e.target.closest(".region-cancel")) return;
    const s = { x: e.clientX, y: e.clientY };
    setDragStart(s); setIsDragging(true); setDragBox({ x: s.x, y: s.y, w: 0, h: 0 });
    e.preventDefault();
  };
  const onRegionMove = (e) => {
    if (!isDragging || !dragStart) return;
    setDragBox({ x: Math.min(e.clientX,dragStart.x), y: Math.min(e.clientY,dragStart.y), w: Math.abs(e.clientX-dragStart.x), h: Math.abs(e.clientY-dragStart.y) });
  };
  const onRegionUp = () => {
    if (!isDragging) return; setIsDragging(false);
    if (dragBox?.w > 10 && dragBox?.h > 10) {
      setTimeout(() => {
        setDragBox(null); setDragStart(null); setRegionMode(false);
        setActiveTool("chat");
        setMessages([{ role: "user", text: "What's in this region?" }]);
        simulateResponse();
      }, 180);
    } else { setDragBox(null); setDragStart(null); }
  };

  // Voice
  const toggleRecording = () => {
    if (!recording) {
      setRecording(true); setTranscript("");
      setTimeout(() => {
        setTranscript("What's the bug on line 47?");
        setTimeout(() => {
          setRecording(false); setActiveTool("chat");
          setMessages([{ role: "user", text: "What's the bug on line 47?" }]);
          simulateResponse();
        }, 1200);
      }, 1800);
    } else { setRecording(false); }
  };

  const toggleTool = (id) => {
    if (id === "region") { setRegionMode(true); setActiveTool(null); return; }
    setActiveTool(prev => prev === id ? null : id);
  };

  const closePanel = () => {
    setActiveTool(null);
    clearInterval(streamRef.current);
    setStreaming(false); setThinking(false); setStreamText("");
  };

  // File attach
  const handleFileDrop = (e) => {
    e.preventDefault(); setDropOver(false);
    const f = e.dataTransfer?.files?.[0];
    if (f) setAttachedFile(f.name);
  };

  // Demo shortcut helpers
  const goDemo = (tool, error = false) => {
    clearInterval(streamRef.current);
    setStreaming(false); setThinking(false); setStreamText("");
    setOllamaError(error);
    setHasNotif(false);
    setExpanded(true);
    setActiveTool(tool);
    if (!tool) setMessages([]);
  };

  const isBusy = thinking || streaming;
  const provider = detectProvider(apiKey);
  const showPanel = activeTool !== null;

  // Panel position: above the pill
  const panelStyle = {
    position: "absolute",
    bottom: "calc(100% + 10px)",
    left: "50%",
    transform: "translateX(-50%)",
  };

  if (pos.x === null) return null;

  return (
    <>
      {/* Fake desktop */}
      <div className="fake-win">
        <div className="fake-bar">
          <div className="tl tl-r"/><div className="tl tl-y"/><div className="tl tl-g"/>
          <span className="fake-title">main.py — glassview_ai</span>
        </div>
        <div className="fake-body">
          {[95,80,60,85,70,40,90,75,55,80,65,50].map((w,i)=>(
            <div key={i} className="fl" style={{width:`${w}%`,opacity:.5+i%3*.1,marginTop:i===4||i===8?6:0}}/>
          ))}
        </div>
      </div>

      {/* Region overlay */}
      {regionMode && (
        <div className="region-overlay" onMouseDown={onRegionDown} onMouseMove={onRegionMove} onMouseUp={onRegionUp}>
          <div className="region-bg"/>
          {!isDragging && <div className="region-hint"><div className="region-hint-t">Select a region</div><div className="region-hint-s">Click and drag to capture</div></div>}
          {dragBox?.w > 2 && <div className="region-sel" style={{left:dragBox.x,top:dragBox.y,width:dragBox.w,height:dragBox.h}}/>}
          <button className="region-cancel" onClick={()=>{setRegionMode(false);setDragBox(null);}}>Cancel — esc</button>
        </div>
      )}

      {/* GlassView */}
      <div className="gv-wrap" style={{left:pos.x,top:pos.y,position:"fixed"}}>

        {/* Panel anchored above pill */}
        {showPanel && (
          <div className="gv-panel" style={panelStyle}>

            {/* Error state */}
            {ollamaError ? (
              <>
                <div className="gv-panel-hdr">
                  <span className="gv-panel-title">GlassView</span>
                  <button className="gv-close-btn" onClick={closePanel}><Icon d={Icons.close} size={10} sw={2}/></button>
                </div>
                <div className="gv-error">
                  <div className="gv-error-hdr">
                    <Icon d={Icons.warning} size={16} stroke={t.warnIcon} sw={1.5}/>
                    <span className="gv-error-title">No model connected</span>
                  </div>
                  <div className="gv-error-body">
                    Ollama isn't running or no model is pulled. Start Ollama and run <code style={{fontFamily:"monospace",fontSize:11}}>ollama pull qwen3-vl:8b</code>, or add an API key in Settings.
                  </div>
                  <button className="gv-error-btn" onClick={()=>{setOllamaError(false);setActiveTool("settings");}}>Open Settings</button>
                </div>
              </>
            ) : (
              <>
                <div className="gv-panel-hdr">
                  <span className="gv-panel-title">{{ chat:"Chat", voice:"Voice", history:"Past Chats", settings:"Settings" }[activeTool]}</span>
                  <button className="gv-close-btn" onClick={closePanel}><Icon d={Icons.close} size={10} sw={2}/></button>
                </div>

                {/* ── Chat ── */}
                {activeTool === "chat" && (
                  <>
                    <div className="gv-ctx">
                      <div className="gv-ctx-thumb">
                        {[90,70,85,60,75].map((w,i)=><div key={i} className="gv-ctx-line" style={{width:`${w}%`}}/>)}
                      </div>
                      <div className="gv-ctx-meta">
                        <div className="gv-ctx-app">main.py — glassview_ai</div>
                        <div className="gv-ctx-sub">VS Code · active window</div>
                      </div>
                    </div>

                    {/* File drop */}
                    <div
                      className={`gv-drop${dropOver?" over":""}`}
                      onDragOver={e=>{e.preventDefault();setDropOver(true)}}
                      onDragLeave={()=>setDropOver(false)}
                      onDrop={handleFileDrop}
                      onClick={()=>setAttachedFile("document.pdf")}
                    >
                      <Icon d={Icons.attach} size={13} stroke={attachedFile?"#3BAAFF":t.textFaint} sw={1.4}/>
                      {attachedFile
                        ? <div className="gv-file-chip">{attachedFile}<button className="gv-file-rm" onClick={e=>{e.stopPropagation();setAttachedFile(null);}}>✕</button></div>
                        : <span className="gv-drop-label">Drop a file or <span>click to attach</span></span>
                      }
                    </div>

                    {(messages.length > 0 || isBusy) && (
                      <div className="gv-msgs" ref={msgsRef}>
                        {messages.map((m,i)=>(
                          <div key={i} className={`gv-msg gv-msg-${m.role==="user"?"u":"a"}`}>
                            <div className={`gv-bubble gv-bubble-${m.role==="user"?"u":"a"}`}>{m.text}</div>
                          </div>
                        ))}
                        {thinking && <div className="gv-msg gv-msg-a"><div className="gv-bubble gv-bubble-a"><div className="thinking-dots"><div className="td"/><div className="td"/><div className="td"/></div></div></div>}
                        {streaming && streamText && <div className="gv-msg gv-msg-a"><div className="gv-bubble gv-bubble-a">{streamText}<span className="gv-cursor"/></div></div>}
                      </div>
                    )}

                    <div className="gv-input-row">
                      <button className="gv-attach-btn" onClick={()=>setAttachedFile("screenshot.png")}>
                        <Icon d={Icons.attach} size={13} sw={1.4}/>
                      </button>
                      <input ref={inputRef} className="gv-input" placeholder="Ask about your screen…"
                        value={inputVal} onChange={e=>setInputVal(e.target.value)}
                        onKeyDown={e=>{if(e.key==="Enter"&&!e.shiftKey){e.preventDefault();sendMessage();}}}
                        disabled={isBusy} autoFocus/>
                      <button className="gv-send" onClick={sendMessage} disabled={!inputVal.trim()||isBusy}>
                        <Icon d={Icons.send} size={13} stroke="white" sw={1.8}/>
                      </button>
                    </div>
                  </>
                )}

                {/* ── Voice ── */}
                {activeTool === "voice" && (
                  <div className="gv-voice">
                    <div className="voice-ring">
                      {recording && <><div className="vring"/><div className="vring"/><div className="vring"/></>}
                      <button className={`voice-btn${recording?" rec":""}`} onClick={toggleRecording}>
                        <Icon d={Icons.mic} size={22} stroke="currentColor" sw={1.5}/>
                      </button>
                    </div>
                    <div className="voice-transcript">{transcript||(recording?"Listening…":"Tap to speak")}</div>
                    <div className="voice-label">{recording?"Recording — tap to stop":"Voice input"}</div>
                  </div>
                )}

                {/* ── History ── */}
                {activeTool === "history" && (
                  <>
                    <input className="gv-hist-search" placeholder="Search past chats…"
                      value={histSearch} onChange={e=>setHistSearch(e.target.value)} autoFocus/>
                    <div className="gv-hist-list">
                      {FAKE_CHATS.filter(c=>c.title.toLowerCase().includes(histSearch.toLowerCase())||c.preview.toLowerCase().includes(histSearch.toLowerCase())).map(c=>(
                        <div key={c.id} className="gv-hist-item" onClick={()=>{setActiveTool("chat");setMessages([{role:"user",text:"Continue"},{role:"ai",text:c.preview}]);}}>
                          <div className="gv-hist-row"><span className="gv-hist-title">{c.title}</span><span className="gv-hist-time">{c.time}</span></div>
                          <div className="gv-hist-preview">{c.preview}</div>
                        </div>
                      ))}
                    </div>
                  </>
                )}

                {/* ── Settings ── */}
                {activeTool === "settings" && (
                  <div className="gv-settings">
                    {/* Appearance */}
                    <div className="gv-sg">
                      <div className="gv-sg-label">Appearance</div>
                      <div className="gv-sr">
                        <span className="gv-sr-name">Theme</span>
                        <div style={{display:"flex",gap:6}}>
                          {["dark","light"].map(th=>(
                            <button key={th} onClick={()=>{setTheme(th);setSettings(s=>({...s,theme:th}));}}
                              style={{padding:"4px 10px",borderRadius:6,border:`1px solid ${theme===th?"#0A84FF":t.sepColor}`,background:theme===th?"rgba(10,132,255,.12)":"transparent",cursor:"pointer",fontSize:11,fontFamily:"inherit",color:theme===th?"#0A84FF":t.textFaint,transition:"all .15s"}}>
                              {th==="dark"?"Dark":"Light"}
                            </button>
                          ))}
                        </div>
                      </div>
                    </div>

                    {/* Model / API */}
                    <div className="gv-sg">
                      <div className="gv-sg-label">Model</div>
                      <div className="gv-sr" style={{flexDirection:"column",alignItems:"stretch",gap:8}}>
                        <div style={{display:"flex",alignItems:"center",justifyContent:"space-between"}}>
                          <span className="gv-sr-name">API Key</span>
                          <span className={`gv-api-badge ${provider}`}>{provider==="ollama"?"Ollama":provider==="openai"?"OpenAI":"Anthropic"}</span>
                        </div>
                        <input className="gv-api-input" type="password"
                          placeholder="sk-… or sk-ant-… or leave blank for Ollama"
                          value={apiKey} onChange={e=>setApiKey(e.target.value)}/>
                      </div>
                      {provider==="ollama" && (
                        <div className="gv-sr">
                          <span className="gv-sr-name">Ollama model</span>
                          <span className="gv-sr-val">qwen3-vl:8b</span>
                        </div>
                      )}
                    </div>

                    {/* Shortcut */}
                    <div className="gv-sg">
                      <div className="gv-sg-label">Shortcut</div>
                      <div className="gv-sr">
                        <span className="gv-sr-name">Global trigger</span>
                        <input className="gv-kbd-input" value={settings.shortcut}
                          onChange={e=>setSettings(s=>({...s,shortcut:e.target.value}))}/>
                      </div>
                    </div>

                    {/* Behavior */}
                    <div className="gv-sg">
                      <div className="gv-sg-label">Behavior</div>
                      {[
                        ["Close on click outside","closeOnBlur"],
                        ["Auto-launch on login","autoLaunch"],
                        ["Stream responses","streaming"],
                      ].map(([label,key])=>(
                        <div key={key} className="gv-sr">
                          <span className="gv-sr-name">{label}</span>
                          <button className={`gv-toggle${settings[key]?" on":""}`}
                            onClick={()=>setSettings(s=>({...s,[key]:!s[key]}))}/>
                        </div>
                      ))}
                    </div>

                    {/* Privacy */}
                    <div className="gv-sg">
                      <div className="gv-sg-label">Privacy</div>
                      {[
                        ["Privacy redaction","privacy"],
                        ["Auto-capture context","autoContext"],
                      ].map(([label,key])=>(
                        <div key={key} className="gv-sr">
                          <span className="gv-sr-name">{label}</span>
                          <button className={`gv-toggle${settings[key]?" on":""}`}
                            onClick={()=>setSettings(s=>({...s,[key]:!s[key]}))}/>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </>
            )}
          </div>
        )}

        {/* Pill */}
        <div className={`gv-pill${draggingBar?" dragging":""}`} onMouseDown={onBarMouseDown}>
          <button className="gv-logo-btn"
            onMouseDown={e=>e.stopPropagation()}
            onClick={()=>{
              setExpanded(e=>!e);
              setHasNotif(false);
              if(expanded) setActiveTool(null);
            }}>
            <GLogo size={22} animate={hasNotif&&!expanded}/>
          </button>

          <div className={`gv-tools${expanded?" open":""}`}>
            <div className="gv-sep"/>
            {TOOLS.map(tool=>(
              <button key={tool.id}
                className={`gv-tool-btn${activeTool===tool.id?" active":""}`}
                onMouseDown={e=>e.stopPropagation()}
                onClick={()=>toggleTool(tool.id)}>
                <Icon d={Icons[tool.icon]} size={15} stroke="currentColor" sw={1.4}/>
                <div className="gv-tip">
                  <span className="gv-tip-label">{tool.label}</span>
                  <span className="gv-tip-kbd">{tool.kbd}</span>
                </div>
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* Demo bar */}
      <div className="demo-bar">
        <button className={`demo-btn${!expanded?"on":""}`} onClick={()=>{setExpanded(false);setActiveTool(null);setHasNotif(false);}}>Collapsed</button>
        <div className="demo-div"/>
        <button className={`demo-btn${expanded&&!activeTool?"on":""}`} onClick={()=>goDemo(null)}>Toolbar</button>
        <div className="demo-div"/>
        <button className={`demo-btn${activeTool==="chat"&&!ollamaError?"on":""}`} onClick={()=>{goDemo("chat");setMessages([]);}}>Chat</button>
        <div className="demo-div"/>
        <button className={`demo-btn${activeTool==="chat"&&!ollamaError&&messages.length>0?"on":""}`} onClick={()=>{goDemo("chat");setMessages([{role:"user",text:"What's the bug on line 47?"}]);simulateResponse();}}>Response</button>
        <div className="demo-div"/>
        <button className="demo-btn" onClick={()=>{setExpanded(false);setActiveTool(null);setMessages([{role:"user",text:"What's the bug?"}]);setTimeout(()=>{setHasNotif(true);},800);}}>Notif</button>
        <div className="demo-div"/>
        <button className={`demo-btn${ollamaError?"on":""}`} onClick={()=>goDemo("chat",true)}>No model</button>
        <div className="demo-div"/>
        <button className={`demo-btn${activeTool==="voice"?"on":""}`} onClick={()=>goDemo("voice")}>Voice</button>
        <div className="demo-div"/>
        <button className={`demo-btn${activeTool==="history"?"on":""}`} onClick={()=>goDemo("history")}>History</button>
        <div className="demo-div"/>
        <button className={`demo-btn${activeTool==="settings"?"on":""}`} onClick={()=>goDemo("settings")}>Settings</button>
      </div>
    </>
  );
}
