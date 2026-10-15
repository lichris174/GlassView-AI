import { PROVIDER_LABELS, detectProvider } from "../../hooks/useSettings";
import type { Provider, Settings, ThemeName } from "../../types";

const PROVIDERS: Provider[] = ["ollama", "openai", "anthropic", "deepseek"];

const KEY_PLACEHOLDER: Record<Provider, string> = {
  ollama: "",
  openai: "sk-…",
  anthropic: "sk-ant-…",
  deepseek: "sk-… (DeepSeek)",
};

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

interface ToggleRow {
  label: string;
  key: BooleanSettingKey;
  /** The backing feature does not exist yet, so show state instead of a control
   *  that silently does nothing. Drop this flag once the feature ships. */
  soon?: boolean;
}

const BEHAVIOR: ToggleRow[] = [
  { label: "Close on click outside", key: "closeOnBlur" },
  { label: "Auto-launch on login", key: "autoLaunch" },
  { label: "Stream responses", key: "streaming" },
];
const PRIVACY: ToggleRow[] = [
  { label: "Privacy redaction", key: "privacy" },
  { label: "Auto-capture context", key: "autoContext", soon: true },
];

export function SettingsPanel({ settings, update, theme, setTheme, apiKey, setApiKey, model }: SettingsPanelProps) {
  const provider = settings.provider;
  const providerLabel = PROVIDER_LABELS[provider];

  // Pasting a key while still on the local provider pre-selects the obvious
  // match. DeepSeek is never guessed — its keys look exactly like OpenAI's.
  const onApiKeyChange = (key: string) => {
    setApiKey(key);
    if (provider === "ollama") {
      const guess = detectProvider(key);
      if (guess !== "ollama") update("provider", guess);
    }
  };

  const toggle = (key: BooleanSettingKey) => update(key, !settings[key]);

  const renderRow = ({ label, key, soon }: ToggleRow) => (
    <div key={key} className="gv-sr">
      <span className="gv-sr-name">{label}</span>
      {soon ? (
        <span className="gv-sr-val">Soon</span>
      ) : (
        <button
          className={`gv-toggle${settings[key] ? " on" : ""}`}
          onClick={() => toggle(key)}
        />
      )}
    </div>
  );

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
            <span className="gv-sr-name">Provider</span>
            <span className={`gv-api-badge ${provider}`}>{providerLabel}</span>
          </div>
          <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
            {PROVIDERS.map((p) => (
              <button
                key={p}
                className={`gv-theme-btn${provider === p ? " on" : ""}`}
                onClick={() => update("provider", p)}
              >
                {PROVIDER_LABELS[p]}
              </button>
            ))}
          </div>
        </div>

        {provider === "ollama" ? (
          <div className="gv-sr">
            <span className="gv-sr-name">Ollama model</span>
            <span className="gv-sr-val">{model ?? "not detected"}</span>
          </div>
        ) : (
          <div className="gv-sr" style={{ flexDirection: "column", alignItems: "stretch", gap: 8 }}>
            <span className="gv-sr-name">API Key</span>
            <input
              className="gv-api-input"
              type="password"
              placeholder={KEY_PLACEHOLDER[provider]}
              value={apiKey}
              onChange={(e) => onApiKeyChange(e.target.value)}
            />
            {!apiKey && (
              <span className="gv-sr-val">Key required for {providerLabel}</span>
            )}
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
        {BEHAVIOR.map(renderRow)}
      </div>

      <div className="gv-sg">
        <div className="gv-sg-label">Privacy</div>
        {PRIVACY.map(renderRow)}
      </div>
    </div>
  );
}
