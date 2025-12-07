// ---------------------------------------------
// Backend entrypoint: vision chat via Ollama
// - /analyze-screenshot handles image + text
// - Keeps a short rolling history
// - Falls back to generate if chat returns empty
// ---------------------------------------------
import express from "express";
import cors from "cors";

const app = express();
app.use(express.json({ limit: "300mb" }));
app.use(cors());

// Default model; override with OLLAMA_MODEL if you want a different one.
const MODEL = process.env.OLLAMA_MODEL || "qwen3-vl";
const OLLAMA_HOST = process.env.OLLAMA_HOST || "http://127.0.0.1:11434";
const MAX_HISTORY = 12; // number of past turns to keep (user/assistant pairs)

const SYSTEM_PROMPT =
  "You are an AI Screen Assistant. Respond directly and clearly. You may include math in LaTeX (inline $...$ or block $$...$$). Do not include chain-of-thought or meta commentary; just answer the user.";

// Keep a system message at the front, then recent history.
const conversation = [{ role: "system", content: SYSTEM_PROMPT }];

function logVisionInfo(label, imageBase64) {
  const len = imageBase64 ? imageBase64.length : 0;
  console.log(`${label} (image length=${len})`);
}

function pushMessage(entry) {
  conversation.push(entry);

  // Trim to keep memory short: system + last MAX_HISTORY*2 messages
  const maxMessages = 1 + MAX_HISTORY * 2;
  if (conversation.length > maxMessages) {
    const system = conversation[0];
    const recent = conversation.slice(conversation.length - (maxMessages - 1));
    conversation.length = 0;
    conversation.push(system, ...recent);
  }
}

function buildUserEntry(userMessage, imageBase64) {
  const msg = (userMessage || "").trim() || "Describe this screenshot briefly.";
  const entry = { role: "user", content: msg };
  if (imageBase64) {
    // Accept both pure base64 and data URLs; strip prefix if present.
    const base64 =
      typeof imageBase64 === "string" && imageBase64.includes(",")
        ? imageBase64.split(",").pop()
        : imageBase64;
    entry.images = [base64];
  }
  return entry;
}

function normalizeContent(value, { trim = true } = {}) {
  if (value === undefined || value === null) return "";
  if (Array.isArray(value)) {
    const joined = value.join(" ");
    return trim ? joined.trim() : joined;
  }
  const str = String(value);
  return trim ? str.trim() : str;
}

async function callOllamaChat(messages) {
  try {
    const res = await fetch(`${OLLAMA_HOST}/api/chat`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        model: MODEL,
        messages,
        stream: false,
        options: {
          temperature: 0.6,
          top_p: 0.9,
          num_predict: -1, // let the model respond without truncation
        },
      }),
    });

    if (!res.ok) {
      const text = await res.text();
      throw new Error(`Ollama HTTP ${res.status}: ${text}`);
    }

    const data = await res.json();
    const msg = data?.message || {};

    // Normalize possible content shapes
    let answer = normalizeContent(msg.content);
    const responseField = normalizeContent(data?.response);

    if (!answer && responseField) {
      answer = responseField;
    }

    if (!answer) {
      console.warn("Ollama returned no content. Raw response:", data);
      return "(no response)";
    }

    return answer;
  } catch (err) {
    if (err.code === "ECONNREFUSED") {
      throw new Error(
        `Cannot reach Ollama at ${OLLAMA_HOST}. Is the daemon running?`
      );
    }
    throw err;
  }
}

async function callOllamaGenerate(message, imageBase64) {
  const prompt = (message || "").trim() || "Describe this screenshot briefly.";
  try {
    const res = await fetch(`${OLLAMA_HOST}/api/generate`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        model: MODEL,
        prompt: `${SYSTEM_PROMPT}\nUser: ${prompt}\nAnswer:`,
        images: imageBase64 ? [imageBase64] : [],
        stream: false,
        options: {
          temperature: 0.6,
          top_p: 0.9,
          num_predict: -1, // let the model respond without truncation
        },
      }),
    });

    if (!res.ok) {
      const text = await res.text();
      throw new Error(`Ollama generate HTTP ${res.status}: ${text}`);
    }

    const data = await res.json();
    const responseField = normalizeContent(data?.response);
    if (!responseField) {
      console.warn("Ollama generate returned no content. Raw response:", data);
      return "(no response)";
    }
    return responseField;
  } catch (err) {
    if (err.code === "ECONNREFUSED") {
      throw new Error(
        `Cannot reach Ollama at ${OLLAMA_HOST}. Is the daemon running?`
      );
    }
    throw err;
  }
}

async function streamOllamaChat(messages, onToken) {
  const res = await fetch(`${OLLAMA_HOST}/api/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      model: MODEL,
      messages,
      stream: true,
      options: {
        temperature: 0.6,
        top_p: 0.9,
        num_predict: -1,
      },
    }),
  });

  if (!res.ok) {
    const text = await res.text();
    throw new Error(`Ollama HTTP ${res.status}: ${text}`);
  }

  const reader = res.body?.getReader();
  if (!reader) throw new Error("No response body from Ollama");

  const decoder = new TextDecoder();
  let buffer = "";
    let answer = "";

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      let idx;
      while ((idx = buffer.indexOf("\n")) !== -1) {
        const line = buffer.slice(0, idx).trim();
        buffer = buffer.slice(idx + 1);
        if (!line) continue;
        try {
          const json = JSON.parse(line);
          const raw = json?.message?.content ?? json?.delta ?? "";
          const delta =
            typeof raw === "string" ? raw : normalizeContent(raw, { trim: false });
          if (delta) {
            answer += delta;
            if (typeof onToken === "function") onToken(delta);
          }
        } catch (_) {
        // ignore malformed line
      }
    }
  }

  return answer || "(no response)";
}

// ---------------------------------------------
// API endpoint
// ---------------------------------------------
app.post("/analyze-screenshot", async (req, res) => {
  try {
    console.log("\n--- Incoming Request ---");
    console.log("Message:", req.body.message);
    console.log("Image present:", !!req.body.imageBase64);
    if (req.body.imageBase64) {
      logVisionInfo("Incoming image", req.body.imageBase64);
    }

    const userEntry = buildUserEntry(req.body.message, req.body.imageBase64);

    // Build message list: system + history + new user
    const messages = [...conversation, userEntry];

    let answer = await callOllamaChat(messages);

    if (!answer || answer === "(no response)") {
      console.warn("Chat returned no answer; retrying with generate.");
      answer = await callOllamaGenerate(req.body.message, userEntry.images?.[0]);
    }

    // Persist dialogue
    pushMessage(userEntry);
    pushMessage({ role: "assistant", content: answer });

    res.json({ feedback: answer });
  } catch (err) {
    console.error("Server error:", err);
    const status = err.name === "AbortError" ? 504 : 500;
    res.status(status).json({ error: err.toString() });
  }
});

// Streaming endpoint: streams plain text tokens as they arrive.
app.post("/analyze-screenshot-stream", async (req, res) => {
  try {
    console.log("\n--- Incoming Request (stream) ---");
    console.log("Message:", req.body.message);
    console.log("Image present:", !!req.body.imageBase64);
    if (req.body.imageBase64) {
      logVisionInfo("Incoming image", req.body.imageBase64);
    }

    const userEntry = buildUserEntry(req.body.message, req.body.imageBase64);
    const messages = [...conversation, userEntry];

    res.setHeader("Content-Type", "text/plain; charset=utf-8");
    res.setHeader("Cache-Control", "no-cache");
    res.setHeader("X-Accel-Buffering", "no"); // for nginx buffers, harmless otherwise

    let answer = "";
    const tokenHandler = (chunk) => {
      answer += chunk;
      res.write(chunk);
      if (typeof res.flush === "function") res.flush();
    };

    try {
      await streamOllamaChat(messages, tokenHandler);
    } catch (err) {
      console.warn("Stream failed, retrying with generate:", err);
      // If chat stream fails, fallback to generate (non-stream) and write once.
      answer = await callOllamaGenerate(req.body.message, userEntry.images?.[0]);
      res.write(answer);
    }

    pushMessage(userEntry);
    pushMessage({ role: "assistant", content: answer });

    res.end();
  } catch (err) {
    console.error("Stream server error:", err);
    const status = err.name === "AbortError" ? 504 : 500;
    res.status(status).json({ error: err.toString() });
  }
});

// ---------------------------------------------
// Start server
// ---------------------------------------------
app.listen(3000, () => {
  console.log("Backend running at http://localhost:3000");
});
