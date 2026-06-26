import { detectProvider } from "../../hooks/useSettings";
import type { Settings, ThemeName } from "../../types";

interface SettingsPanelProps {
  settings: Settings;
  update: <K extends keyof Settings>(key: K, value: Settings[K]) => void;
  theme: ThemeName;
  setTheme: (t: ThemeName) => void;
  apiKey: string;
  setApiKey: (k: string) => void;
  model: string | null;
}

type BooleanSettingKey = {
  [K in keyof Settings]: Settings[K] extends boolean ? K : never;
}[keyof Settings];

const BEHAVIOR: [string, BooleanSettingKey][] = [
  ["Close on click outside", "closeOnBlur"],
  ["Auto-launch on login", "autoLaunch"],
  ["Stream responses", "streaming"],
];
const PRIVACY: [string, BooleanSettingKey][] = [
  ["Privacy redaction", "privacy"],
  ["Auto-capture context", "autoContext"],
];

export function SettingsPanel({ settings, update, theme, setTheme, apiKey, setApiKey, model }: SettingsPanelProps) {
  const provider = detectProvider(apiKey);
  const providerLabel = provider === "ollama" ? "Ollama" : provider === "openai" ? "OpenAI" : "Anthropic";

  const toggle = (key: BooleanSettingKey) => update(key, !settings[key]);

  return (
    <div className="gv-settings">
      <div className="gv-sg">
        <div className="gv-sg-label">Appearance</div>
        <div className="gv-sr">
          <span className="gv-sr-name">Theme</span>
          <div style={{ display: "flex", gap: 6 }}>
            {(["dark", "light"] as ThemeName[]).map((th) => (
              <button
                key={th}
                className={`gv-theme-btn${theme === th ? " on" : ""}`}
                onClick={() => setTheme(th)}
              >
                {th === "dark" ? "Dark" : "Light"}
              </button>
            ))}
          </div>
        </div>
      </div>

      <div className="gv-sg">
        <div className="gv-sg-label">Model</div>
        <div className="gv-sr" style={{ flexDirection: "column", alignItems: "stretch", gap: 8 }}>
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
            <span className="gv-sr-name">API Key</span>
            <span className={`gv-api-badge ${provider}`}>{providerLabel}</span>
          </div>
          <input
            className="gv-api-input"
            type="password"
            placeholder="sk-… or sk-ant-… or leave blank for Ollama"
            value={apiKey}
            onChange={(e) => setApiKey(e.target.value)}
          />
        </div>
        {provider === "ollama" && (
          <div className="gv-sr">
            <span className="gv-sr-name">Ollama model</span>
            <span className="gv-sr-val">{model ?? "not detected"}</span>
          </div>
        )}
      </div>

      <div className="gv-sg">
        <div className="gv-sg-label">Shortcut</div>
        <div className="gv-sr">
          <span className="gv-sr-name">Global trigger</span>
          <input
            className="gv-kbd-input"
            value={settings.shortcut}
            onChange={(e) => update("shortcut", e.target.value)}
          />
        </div>
      </div>

      <div className="gv-sg">
        <div className="gv-sg-label">Behavior</div>
        {BEHAVIOR.map(([label, key]) => (
          <div key={key} className="gv-sr">
            <span className="gv-sr-name">{label}</span>
            <button
              className={`gv-toggle${settings[key] ? " on" : ""}`}
              onClick={() => toggle(key)}
            />
          </div>
        ))}
      </div>

      <div className="gv-sg">
        <div className="gv-sg-label">Privacy</div>
        {PRIVACY.map(([label, key]) => (
          <div key={key} className="gv-sr">
            <span className="gv-sr-name">{label}</span>
            <button
              className={`gv-toggle${settings[key] ? " on" : ""}`}
              onClick={() => toggle(key)}
            />
          </div>
        ))}
      </div>
    </div>
  );
}
