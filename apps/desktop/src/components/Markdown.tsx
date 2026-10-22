import { memo } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import remarkMath from "remark-math";
import rehypeKatex from "rehype-katex";
// KaTeX stylesheet — Vite bundles its woff2 fonts locally, so math typesets offline in
// the Tauri shell (no CDN). See plan: KaTeX offline note.
import "katex/dist/katex.min.css";
import { openExternal } from "../lib/tauri";

/** Only web links leave the app; anything else (relative, mailto:, …) is inert. */
function isWebLink(href: string | undefined): href is string {
  return !!href && /^https?:\/\//i.test(href);
}

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
          // Never navigate the overlay webview: web links are handed to the system
          // browser, everything else is swallowed.
          a: ({ node: _node, ...props }) => (
            <a
              {...props}
              rel="noreferrer noopener"
              onClick={(e) => {
                e.preventDefault();
                if (isWebLink(props.href)) {
                  openExternal(props.href).catch((err) =>
                    console.error("[link] failed to open:", err),
                  );
                }
              }}
            />
          ),
        }}
      >
        {text}
      </ReactMarkdown>
    </div>
  );
});
