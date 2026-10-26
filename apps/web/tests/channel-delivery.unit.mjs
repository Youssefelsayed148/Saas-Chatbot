/* Component unit tests use the installed TypeScript compiler and React renderer. */
import { test } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import Module from "node:module";
import { fileURLToPath } from "node:url";
import ts from "typescript";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
const filename = fileURLToPath(
  new URL("../lib/channel-delivery.tsx", import.meta.url),
);
const compiled = ts.transpileModule(fs.readFileSync(filename, "utf8"), {
  compilerOptions: { module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX },
}).outputText;
const mod = new Module(filename);
mod.filename = filename;
mod.paths = Module._nodeModulePaths(path.dirname(filename));
mod._compile(compiled, filename);
const { ChannelDelivery, ChannelReplyFields, connectionReplyBlock } =
  mod.exports;
const render = (component, props) =>
  renderToStaticMarkup(React.createElement(component, props));

for (const status of [
  "pending",
  "sent",
  "delivered",
  "read",
  "failed",
  "unconfirmed",
]) {
  test(`channel delivery renders ${status}`, () => {
    assert.match(
      render(ChannelDelivery, {
        channel: "whatsapp",
        message: {
          sender_type: "agent",
          delivery_status: status,
          error_code: "window_closed",
        },
      }),
      new RegExp(status, "i"),
    );
  });
}
for (const sender of ["visitor", "system"]) {
  test(`${sender} has no delivery state`, () => {
    assert.equal(
      render(ChannelDelivery, {
        channel: "instagram",
        message: {
          sender_type: sender,
          delivery_status: "sent",
        },
      }),
      "",
    );
  });
}
test("website and unstated deliveries are hidden", () => {
  assert.equal(
    render(ChannelDelivery, {
      channel: "website",
      message: { sender_type: "ai", delivery_status: "read" },
    }),
    "",
  );
  assert.equal(
    render(ChannelDelivery, {
      channel: "messenger",
      message: { sender_type: "ai" },
    }),
    "",
  );
});
for (const code of [
  "window_closed",
  "template_required",
  "recipient_unreachable",
]) {
  test(`readable reason for ${code}`, () => {
    const html = render(ChannelDelivery, {
      channel: "whatsapp",
      message: {
        sender_type: "ai",
        delivery_status: "failed",
        error_code: code,
      },
    });
    assert.doesNotMatch(html, new RegExp(code));
    assert.match(html, /Failed:/);
    assert.match(html, /template|required|recipient/);
  });
}
for (const status of ["paused", "revoked"]) {
  test(`${status} disables composer and explains why`, () => {
    const block = connectionReplyBlock("whatsapp", status);
    assert.match(block, new RegExp(status));
    const html = render(ChannelReplyFields, {
      value: "مرحبا",
      busy: false,
      block,
      onChange: () => {},
    });
    assert.equal((html.match(/disabled=""/g) || []).length, 2);
    assert.match(html, /aria-describedby="channel-reply-block"/);
    assert.match(html, /dir="auto"/);
  });
}
test("active channel and website composer stay enabled", () => {
  for (const [channel, status] of [
    ["whatsapp", "active"],
    ["website", undefined],
  ]) {
    const block = connectionReplyBlock(channel, status);
    assert.equal(block, null);
    assert.doesNotMatch(
      render(ChannelReplyFields, {
        value: "Reply",
        busy: false,
        block,
        onChange: () => {},
      }),
      /disabled/,
    );
  }
});
