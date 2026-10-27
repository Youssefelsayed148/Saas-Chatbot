/**
 * Parser behind MessageBody: assistant reply text (plain text with hyphen bullets,
 * numbered steps and `**bold**`) into blocks. Pure, so it is unit-testable.
 */

export type InlinePart = { text: string; bold: boolean };

export type MessageBlock =
  | { kind: "paragraph"; lines: InlinePart[][] }
  | { kind: "label"; parts: InlinePart[] }
  | { kind: "list"; ordered: boolean; items: InlinePart[][] };

const BULLET = /^\s*[-*•–]\s+(.*)$/;
const NUMBERED = /^\s*(\d+)[.)]\s+(.*)$/;
const HEADING = /^\s*#{1,4}\s+(.*)$/;
// A short line ending in a colon ("Costs/notes:") introduces what follows.
const LABEL_MAX_CHARS = 60;

export function parseInline(text: string): InlinePart[] {
  return text
    .split(/(\*\*[^*\n]+\*\*)/g)
    .filter((piece) => piece !== "")
    .map((piece) =>
      piece.startsWith("**") && piece.endsWith("**") && piece.length > 4
        ? { text: piece.slice(2, -2), bold: true }
        : { text: piece, bold: false },
    );
}

export function parseMessage(source: string): MessageBlock[] {
  const blocks: MessageBlock[] = [];
  let paragraph: string[] = [];
  let list: { ordered: boolean; items: string[] } | null = null;

  const closeParagraph = () => {
    if (paragraph.length > 0) {
      blocks.push({
        kind: "paragraph",
        lines: paragraph.map((line) => parseInline(line)),
      });
      paragraph = [];
    }
  };
  const closeList = () => {
    if (list) {
      blocks.push({
        kind: "list",
        ordered: list.ordered,
        items: list.items.map((item) => parseInline(item)),
      });
      list = null;
    }
  };
  const addItem = (ordered: boolean, text: string) => {
    closeParagraph();
    if (list && list.ordered !== ordered) closeList();
    if (!list) list = { ordered, items: [] };
    list.items.push(text);
  };

  for (const raw of source.replace(/\r\n?/g, "\n").split("\n")) {
    const line = raw.trimEnd();
    if (line.trim() === "") {
      closeParagraph();
      closeList();
      continue;
    }
    const heading = HEADING.exec(line);
    if (heading) {
      closeParagraph();
      closeList();
      blocks.push({ kind: "label", parts: parseInline(heading[1]) });
      continue;
    }
    const bullet = BULLET.exec(line);
    if (bullet) {
      addItem(false, bullet[1]);
      continue;
    }
    const numbered = NUMBERED.exec(line);
    if (numbered) {
      addItem(true, numbered[2]);
      continue;
    }
    closeList();
    const trimmed = line.trim();
    if (
      paragraph.length === 0 &&
      trimmed.endsWith(":") &&
      trimmed.length <= LABEL_MAX_CHARS
    ) {
      blocks.push({ kind: "label", parts: parseInline(trimmed) });
      continue;
    }
    paragraph.push(line);
  }
  closeParagraph();
  closeList();
  return blocks;
}
