import { memo } from "react";
import ReactMarkdown, { type Components } from "react-markdown";
import remarkGfm from "remark-gfm";
import "./markdown.css";
import { type ChatMarkdownProps, closeUnterminatedFence, sanitizeMarkdownUrl } from "./markdown";

const components: Components = {
  a({ node: _node, ...props }) {
    return <a {...props} target="_blank" rel="noreferrer noopener" />;
  },
  img({ node: _node, ...props }) {
    return <img {...props} alt={props.alt ?? ""} loading="lazy" />;
  },
};

export const ChatMarkdown = memo(function ChatMarkdown({
  children,
  streaming = false,
}: ChatMarkdownProps) {
  const source = streaming ? closeUnterminatedFence(children) : children;
  return (
    <div className={streaming ? "ab-chat-markdown ab-chat-markdown-streaming" : "ab-chat-markdown"}>
      <ReactMarkdown
        components={components}
        remarkPlugins={[remarkGfm]}
        skipHtml
        urlTransform={(url) => sanitizeMarkdownUrl(url, true) ?? ""}
      >
        {source}
      </ReactMarkdown>
      {streaming ? <span aria-hidden="true" className="ab-chat-markdown-cursor" /> : null}
    </div>
  );
});
