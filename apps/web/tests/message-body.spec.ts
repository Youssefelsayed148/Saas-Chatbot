import { expect, test } from "@playwright/test";

import { parseInline, parseMessage } from "../lib/message-parse";

/** Reply formatting: assistant text becomes paragraphs, lists and bold. No page needed. */

test("a procedure becomes an intro, a numbered list and a labelled notes list", () => {
  const blocks = parseMessage(
    [
      "To return an item:",
      "",
      "1. Start the return from your account.",
      "2. Select the item and **state the reason**.",
      "",
      "Costs and notes:",
      "- Change of mind: a 45 EGP fee applies.",
      "- Defects: shipping is refunded.",
    ].join("\n"),
  );
  expect(blocks.map((block) => block.kind)).toEqual([
    "label",
    "list",
    "label",
    "list",
  ]);
  const steps = blocks[1];
  expect(steps.kind === "list" && steps.ordered).toBe(true);
  expect(steps.kind === "list" && steps.items.length).toBe(2);
  const notes = blocks[3];
  expect(notes.kind === "list" && notes.ordered).toBe(false);
});

test("bold text is split out and everything else stays plain", () => {
  expect(parseInline("Pay **45 EGP** now")).toEqual([
    { text: "Pay ", bold: false },
    { text: "45 EGP", bold: true },
    { text: " now", bold: false },
  ]);
  expect(parseInline("2 * 3 = 6")).toEqual([
    { text: "2 * 3 = 6", bold: false },
  ]);
});

test("a bullet and a numbered list in a row are two lists", () => {
  const blocks = parseMessage("- a\n- b\n1. one\n2. two");
  expect(blocks.map((block) => block.kind)).toEqual(["list", "list"]);
});

test("plain lines stay one paragraph with line breaks and html is never interpreted", () => {
  const blocks = parseMessage("Line one\nLine two <script>alert(1)</script>");
  expect(blocks).toHaveLength(1);
  const [block] = blocks;
  expect(block.kind).toBe("paragraph");
  // The markup is kept as literal text: React renders it escaped.
  expect(
    block.kind === "paragraph" &&
      block.lines[1].map((part) => part.text).join(""),
  ).toContain("<script>alert(1)</script>");
});

test("Arabic text and empty input are handled", () => {
  expect(parseMessage("")).toEqual([]);
  const blocks = parseMessage("للإرجاع:\n- الخطوة الأولى\n- الخطوة الثانية");
  expect(blocks.map((block) => block.kind)).toEqual(["label", "list"]);
});
