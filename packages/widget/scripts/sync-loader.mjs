// No bundler/dependencies: canonical web tokens are scoped into the standalone loader.
import { readFileSync, writeFileSync } from "node:fs";
const root = new URL("../../../", import.meta.url);
const tokenPath = new URL("apps/web/app/tokens.css", root);
const selector = ".chatbot-widget-button,.chatbot-widget-frame";
const tokens = readFileSync(tokenPath, "utf8")
  .replace(
    /:root\[data-theme="light"\]/g,
    ".chatbot-widget-button[data-theme=light],.chatbot-widget-frame[data-theme=light]",
  )
  .replace(/:root:not\(\[data-theme\]\)/g, selector)
  .replace(/:root/g, selector);
const source = new URL("packages/widget/src/loader.js", root);
const code = readFileSync(source, "utf8").replace(
  /\/\* GENERATED_WIDGET_TOKENS \*\/[\s\S]*?\/\* END_WIDGET_TOKENS \*\//,
  `/* GENERATED_WIDGET_TOKENS */\n  var widgetTokens = ${JSON.stringify(tokens)};\n  /* END_WIDGET_TOKENS */`,
);
writeFileSync(source, code);
writeFileSync(new URL("apps/web/public/widget/v1/loader.js", root), code);
console.log("Widget loader copies synchronized from canonical tokens.");
