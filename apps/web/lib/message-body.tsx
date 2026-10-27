import "@/app/message-body.css";
import type { ReactNode } from "react";

import { parseMessage, type InlinePart } from "@/lib/message-parse";

/**
 * Renders an assistant reply as structured, scannable content.
 *
 * The model writes plain text with hyphen bullets, numbered steps and `**bold**`.
 * This turns that into paragraphs, lists and emphasis as React nodes. It never uses
 * raw HTML, so reply text (which is untrusted) cannot inject markup. Channel
 * replies (WhatsApp and the like) are plain text and do not use this component.
 */

function renderInline(parts: InlinePart[]): ReactNode {
  return parts.map((part, index) =>
    part.bold ? <strong key={index}>{part.text}</strong> : part.text,
  );
}

export function MessageBody({ text }: { text: string }) {
  const blocks = parseMessage(text);
  return (
    <div className="md-body">
      {blocks.map((block, index) => {
        if (block.kind === "label") {
          return (
            <p key={index} dir="auto" className="md-label">
              {renderInline(block.parts)}
            </p>
          );
        }
        if (block.kind === "list") {
          const Tag = block.ordered ? "ol" : "ul";
          return (
            <Tag key={index} className="md-list">
              {block.items.map((item, itemIndex) => (
                <li key={itemIndex} dir="auto">
                  {renderInline(item)}
                </li>
              ))}
            </Tag>
          );
        }
        return (
          <p key={index} dir="auto" className="md-paragraph">
            {block.lines.map((line, lineIndex) => (
              <span key={lineIndex}>
                {lineIndex > 0 ? <br /> : null}
                {renderInline(line)}
              </span>
            ))}
          </p>
        );
      })}
    </div>
  );
}
