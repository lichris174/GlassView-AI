import { useEffect, useRef, useState } from "react";
import { Icon } from "../Icon";
import { Icons } from "../icons";

interface VoicePanelProps {
  onTranscript: (text: string) => void;
}

// Minimal shape of the Web Speech API we use (not in the standard TS lib).
type SpeechRec = {
  lang: string;
  interimResults: boolean;
  continuous: boolean;
  onresult: (e: { results: ArrayLike<ArrayLike<{ transcript: string }>> }) => void;
  onend: () => void;
  onerror: (e: { error?: string; message?: string }) => void;
  start: () => void;
  stop: () => void;
};

function getRecognizer(): SpeechRec | null {
  const w = window as unknown as { SpeechRecognition?: new () => SpeechRec; webkitSpeechRecognition?: new () => SpeechRec };
  const Ctor = w.SpeechRecognition ?? w.webkitSpeechRecognition;
  return Ctor ? new Ctor() : null;
}

export function VoicePanel({ onTranscript }: VoicePanelProps) {
  const [recording, setRecording] = useState(false);
  const [transcript, setTranscript] = useState("");
  const [supported, setSupported] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const recRef = useRef<SpeechRec | null>(null);

  useEffect(() => {
    return () => recRef.current?.stop();
  }, []);

  const toggle = () => {
    if (recording) {
      recRef.current?.stop();
      return;
    }
    const rec = getRecognizer();
    if (!rec) {
      setSupported(false);
      return;
    }
    rec.lang = "en-US";
    rec.interimResults = true;
    rec.continuous = false;
    let finalText = "";
    rec.onresult = (e) => {
      let text = "";
      for (let i = 0; i < e.results.length; i++) text += e.results[i][0].transcript;
      finalText = text;
      setTranscript(text);
      setError(null);
    };
    rec.onerror = (e: { error?: string; message?: string }) => {
      setRecording(false);
      setError(e.message || e.error || "Voice recognition failed. Try again.");
    };
    rec.onend = () => {
      setRecording(false);
      const t = finalText.trim();
      if (t) {
        setError(null);
        onTranscript(t);
      }
    };
    recRef.current = rec;
    setTranscript("");
    setError(null);
    setRecording(true);
    rec.start();
  };

  if (!supported) {
    return <div className="gv-hist-empty">Voice input isn't supported in this runtime.</div>;
  }

  return (
    <div className="gv-voice">
      <div className="voice-ring">
        {recording && (
          <>
            <div className="vring" /><div className="vring" /><div className="vring" />
          </>
        )}
        <button className={`voice-btn${recording ? " rec" : ""}`} onClick={toggle}>
          <Icon d={Icons.mic} size={22} stroke="currentColor" sw={1.5} />
        </button>
      </div>
      <div className="voice-transcript">{transcript || (recording ? "Listening…" : "Tap to speak")}</div>
      <div className="voice-label">{error ? error : recording ? "Recording — tap to stop" : "Voice input"}</div>
    </div>
  );
}
