import { Icon } from "../Icon";
import { Icons } from "../icons";

interface ErrorPanelProps {
  onOpenSettings: () => void;
}

/** Shown instead of chat content when /health reports no model or is unreachable. */
export function ErrorPanel({ onOpenSettings }: ErrorPanelProps) {
  return (
    <div className="gv-error">
      <div className="gv-error-hdr">
        <Icon d={Icons.warning} size={16} stroke="var(--gv-warnIcon)" sw={1.5} />
        <span className="gv-error-title">No model connected</span>
      </div>
      <div className="gv-error-body">
        Ollama isn't running or no model is pulled. Start Ollama and run{" "}
        <code style={{ fontFamily: "var(--gv-font-mono)", fontSize: 11, background: "var(--gv-accentSoft)", padding: "1px 5px", borderRadius: 4 }}>ollama pull qwen3-vl:8b</code>, or
        add an API key in Settings.
      </div>
      <button className="gv-error-btn" onClick={onOpenSettings}>Open Settings</button>
    </div>
  );
}
