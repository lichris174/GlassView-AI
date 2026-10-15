import { memo } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import remarkMath from "remark-math";
import rehypeKatex from "rehype-katex";
// KaTeX stylesheet — Vite bundles its woff2 fonts locally, so math typesets offline in
// the Tauri shell (no CDN). See plan: KaTeX offline note.
import "katex/dist/katex.min.css";

/**
 * Renders assistant / streaming chat text as GitHub-flavoured Markdown with LaTeX math
 * ($inline$ and $$block$$). Code, links, lists and tables are styled via the .gv-md
 * classes in global.css. react-markdown is resilient to partial/invalid input, so this is
 * safe to feed mid-stream.
 */
export const Markdown = memo(function Markdown({ text }: { text: string }) {
  return (
    <div className="gv-md">
      <ReactMarkdown
        remarkPlugins={[remarkGfm, remarkMath]}
        rehypePlugins={[rehypeKatex]}
        components={{
          // Open links in the system browser, never navigate the overlay webview.
          a: ({ node: _node, ...props }) => (
            <a {...props} target="_blank" rel="noreferrer noopener" />
          ),
        }}
      >
        {text}
      </ReactMarkdown>
    </div>
  );
});
