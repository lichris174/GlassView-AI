import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import remarkMath from "remark-math";
import rehypeKatex from "rehype-katex";
import type { Message as MessageT } from "../lib/types";

/** One chat bubble. Assistant content renders Markdown + LaTeX; user is plain. */
export function Message({ message }: { message: MessageT }) {
  const isUser = message.role === "user";
  return (
    <div className={`msg msg--${isUser ? "user" : "assistant"}`}>
      {isUser ? (
        <span>{message.content}</span>
      ) : (
        <ReactMarkdown
          remarkPlugins={[remarkGfm, remarkMath]}
          rehypePlugins={[rehypeKatex]}
        >
          {message.content || "..."}
        </ReactMarkdown>
      )}
      {message.images?.map((src, i) => (
        <img key={i} src={src} alt="screenshot" />
      ))}
    </div>
  );
}
