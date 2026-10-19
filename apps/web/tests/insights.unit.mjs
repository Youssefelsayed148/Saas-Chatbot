/* P6-05b unit tests for the shared insights helpers (lib/insights.ts). */
import { test } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import Module from "node:module";
import { fileURLToPath } from "node:url";
import ts from "typescript";

const filename = fileURLToPath(new URL("../lib/insights.ts", import.meta.url));
const compiled = ts.transpileModule(fs.readFileSync(filename, "utf8"), {
  compilerOptions: { module: ts.ModuleKind.CommonJS },
}).outputText;
const mod = new Module(filename);
mod.filename = filename;
mod.paths = Module._nodeModulePaths(path.dirname(filename));
mod._compile(compiled, filename);
const {
  CHANNEL_VALUES,
  channelOptions,
  connectionSuffix,
  formatMedian,
  formatRate,
  humanChannel,
  sortedCampaigns,
} = mod.exports;

test("channel options cover the four channel values plus All", () => {
  const options = channelOptions();
  assert.deepEqual(
    options.map((option) => option.value),
    ["", "website", "instagram", "whatsapp", "messenger"],
  );
  assert.deepEqual(
    options.map((option) => option.label),
    ["All", "Website", "Instagram", "WhatsApp", "Messenger"],
  );
  assert.deepEqual(CHANNEL_VALUES.length, 4);
});

test("website can be omitted from the filter (single-channel tenants)", () => {
  const options = channelOptions(false);
  assert.ok(!options.some((option) => option.value === "website"));
  assert.equal(options[0].label, "All");
});

test("human channel labels are spelled out safely", () => {
  assert.equal(humanChannel("whatsapp"), "WhatsApp");
  assert.equal(humanChannel("messenger"), "Messenger");
  assert.equal(humanChannel("instagram"), "Instagram");
  assert.equal(humanChannel("website"), "Website");
  assert.equal(humanChannel("unknown_thing"), "unknown_thing");
});

test("connection suffix is only shown for channel rows with a name", () => {
  assert.equal(connectionSuffix("whatsapp", "Support WhatsApp"), "Support WhatsApp");
  assert.equal(connectionSuffix("messenger", "  Page A  "), "Page A");
  for (const [channel, name] of [
    ["website", "Support WhatsApp"],
    ["whatsapp", undefined],
    ["whatsapp", null],
    ["whatsapp", "   "],
  ]) {
    assert.equal(connectionSuffix(channel, name), null);
  }
});

test("rates render as percentages or a dash when not measured", () => {
  assert.equal(formatRate(null), "—");
  assert.equal(formatRate(undefined), "—");
  assert.equal(formatRate(0), "0.0%");
  assert.equal(formatRate(0.4237), "42.4%");
});

test("median response renders in human units", () => {
  assert.equal(formatMedian(null), "—");
  assert.equal(formatMedian(0), "0s");
  assert.equal(formatMedian(59.4), "59s");
  assert.equal(formatMedian(60), "1 min");
  assert.equal(formatMedian(7200), "2.0 h");
});

test("campaign rows sort by conversations then name", () => {
  const rows = sortedCampaigns({ "Spring": 3, " Ramadan": 5, "Autumn": 3 });
  assert.deepEqual(
    rows.map((row) => row.campaign),
    [" Ramadan", "Autumn", "Spring"],
  );
  assert.deepEqual(rows[0].conversations, 5);
});

test("sorting an empty campaign map is an empty list", () => {
  assert.deepEqual(sortedCampaigns({}), []);
});
