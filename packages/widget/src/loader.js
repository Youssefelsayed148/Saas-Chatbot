/**
 * Widget loader (docs/09) — the ONLY deliverable the customer's site embeds:
 *
 *   <script src="https://<this-deployment>/widget/v1/loader.js" data-locator="w…"></script>
 *
 * The locator is NOT a secret (docs/05): it merely names the bot; all
 * authority stays server-side (short-lived capability tokens, rate limits).
 *
 * Everything else lives in the sandboxed iframe at /widget/frame on the SAME
 * origin as this deployment — the iframe talks to the public API same-origin
 * (no CORS, no third-party cookies), and the customer page can never script
 * the frame beyond the postMessage channel below.
 *
 * Protocol (postMessage):
 *   parent → iframe  {type:"chatbot:locator", locator}
 *   iframe → parent  {type:"chatbot:ready"} — the parent answers with the locator
 *                    {type:"chatbot:size", height}
 *                    {type:"chatbot:brand", colour, position, dir}
 *                    {type:"chatbot:close"} — viewport Escape inside the frame
 * Public API contract: docs/05 (config/session/messages), docs/14 §7/§11.
 */
(function () {
  "use strict";

  var VERSION = "v1";
  /* GENERATED_WIDGET_TOKENS */
  var widgetTokens = "/* Canonical semantic tokens, shared by dashboard and scoped widget surfaces. */\n.chatbot-widget-button,.chatbot-widget-frame {\n  color-scheme: dark;\n  --bg: #0b1018;\n  --surface: #111925;\n  --surface-raised: #172231;\n  --surface-hover: #1e2c3d;\n  --text: #edf3fa;\n  --muted: #a3b2c6;\n  --border: #2b3a4e;\n  --accent: #8aafff;\n  --accent-soft: #20324f;\n  --button: #b1c9ff;\n  --button-text: #101e38;\n  --danger: #ffaaa5;\n  --danger-soft: #382022;\n  --success: #86ddbd;\n  --success-soft: #14372d;\n  --warning: #f2ce8e;\n  --warning-soft: #372e1d;\n  --focus: #b9d0ff;\n  --staff: #d1b3ff;\n  --staff-soft: #302440;\n  --overlay: #050912b8;\n  --shadow: 0 18px 48px #00000030;\n  --radius: 16px;\n  --radius-sm: 9px;\n  --space-1: 0.25rem;\n  --space-2: 0.5rem;\n  --space-3: 0.75rem;\n  --space-4: 1rem;\n  --space-5: 1.5rem;\n  --space-6: 2rem;\n  --space-7: 3rem;\n  --font: ui-sans-serif, system-ui, -apple-system, \"Segoe UI\", sans-serif;\n  --text-sm: 0.825rem;\n  --text-base: 0.925rem;\n  --text-lg: 1.2rem;\n  --heading: clamp(1.65rem, 3vw, 2.3rem);\n  --ease: 160ms ease;\n  --widget-brand: #1f7a5c;\n  --ink-light: #ffffff;\n  --ink-dark: #101820;\n}\n.chatbot-widget-button[data-theme=light],.chatbot-widget-frame[data-theme=light] {\n  color-scheme: light;\n  --bg: #f3f6fb;\n  --surface: #ffffff;\n  --surface-raised: #edf2f9;\n  --surface-hover: #e5edf7;\n  --text: #19263a;\n  --muted: #52647c;\n  --border: #cbd6e5;\n  --accent: #2459b4;\n  --accent-soft: #e5edff;\n  --button: #234f9a;\n  --button-text: #ffffff;\n  --danger: #a62631;\n  --danger-soft: #fff0f0;\n  --success: #176449;\n  --success-soft: #e3f4ec;\n  --warning: #745015;\n  --warning-soft: #fff2d9;\n  --focus: #2459b4;\n  --staff: #7040a2;\n  --staff-soft: #f0e8fa;\n  --overlay: #17263a80;\n  --shadow: 0 18px 48px #1d3c5912;\n}\n@media (prefers-color-scheme: light) {\n  .chatbot-widget-button,.chatbot-widget-frame {\n    color-scheme: light;\n    --bg: #f3f6fb;\n    --surface: #ffffff;\n    --surface-raised: #edf2f9;\n    --surface-hover: #e5edf7;\n    --text: #19263a;\n    --muted: #52647c;\n    --border: #cbd6e5;\n    --accent: #2459b4;\n    --accent-soft: #e5edff;\n    --button: #234f9a;\n    --button-text: #ffffff;\n    --danger: #a62631;\n    --danger-soft: #fff0f0;\n    --success: #176449;\n    --success-soft: #e3f4ec;\n    --warning: #745015;\n    --warning-soft: #fff2d9;\n    --focus: #2459b4;\n    --staff: #7040a2;\n    --staff-soft: #f0e8fa;\n    --overlay: #17263a80;\n    --shadow: 0 18px 48px #1d3c5912;\n  }\n}\n";
  /* END_WIDGET_TOKENS */

  var script =
    document.currentScript ||
    (function () {
      var candidates = document.getElementsByTagName("script");
      for (var i = candidates.length - 1; i >= 0; i--) {
        if (candidates[i].src && candidates[i].src.indexOf("loader") !== -1) {
          return candidates[i];
        }
      }
      return null;
    })();

  if (!script) return;

  var locator = script.getAttribute("data-locator") || "";
  if (!locator) {
    console.error("[widget] Missing data-locator on the loader script tag.");
    return;
  }

  var base = new URL(script.src);
  var frameBase = base.origin;

  var state = {
    opened: false,
    brand: { colour: "", position: "right", dir: "ltr" },
  };

  // --- bubble button ---------------------------------------------------------

  var button = document.createElement("button");
  button.type = "button";
  button.className = "chatbot-widget-button";
  button.setAttribute("aria-label", "Open chat");
  button.setAttribute("aria-expanded", "false");
  button.setAttribute("data-testid", "widget-bubble");
  button.textContent = "💬";
  document.body.appendChild(button);

  button.addEventListener("click", function () {
    if (state.opened) {
      close();
    } else {
      open();
    }
  });

  function styleButton() {
    var colour = state.brand.colour || "var(--widget-brand)";
    var right = state.brand.position !== "left";
    button.style.background = colour;
    button.style.position = "fixed";
    button.style.bottom = "1.25rem";
    button.style[right ? "right" : "left"] = "1.25rem";
    button.style[right ? "left" : "right"] = "auto";
    button.style.width = "3.5rem";
    button.style.height = "3.5rem";
    button.style.borderRadius = "50%";
    button.style.border = "0";
    button.style.boxShadow = "var(--shadow)";
    button.style.cursor = "pointer";
    button.style.zIndex = "2147483000";
    var rgb = /^#[0-9a-f]{6}$/i.test(colour)
      ? [1, 3, 5].map(function (i) {
          var v = parseInt(colour.slice(i, i + 2), 16) / 255;
          return v <= 0.04045 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4);
        })
      : [0, 0, 0];
    button.style.color =
      0.2126 * rgb[0] + 0.7152 * rgb[1] + 0.0722 * rgb[2] > 0.179
        ? "var(--ink-dark)"
        : "var(--ink-light)";
    button.style.fontSize = "1.35rem";
    button.style.lineHeight = "1";
  }

  // --- iframe ------------------------------------------------------------

  var frame = null;

  function createFrame() {
    frame = document.createElement("iframe");
    frame.className = "chatbot-widget-frame";
    frame.title = "Chat with our assistant";
    // Sandboxed per docs/09: scripts and forms run, the frame keeps its own
    // origin (so the public API stays same-origin and cookie-free), and the
    // customer page cannot script the frame beyond the message channel.
    frame.setAttribute(
      "sandbox",
      "allow-scripts allow-same-origin allow-forms",
    );
    frame.setAttribute("data-testid", "widget-frame");
    document.body.appendChild(frame);
    var sourceUrl =
      frameBase +
      "/widget/frame?locator=" +
      encodeURIComponent(locator) +
      "&v=" +
      VERSION;
    frame.src = sourceUrl;
    positionFrame();
  }

  function positionFrame() {
    if (!frame) return;
    var right = state.brand.position !== "left";
    frame.style[right ? "right" : "left"] = "1.25rem";
    frame.style[right ? "left" : "right"] = "auto";
    frame.style.bottom = window.innerWidth <= 480 ? "0" : "5rem";
  }

  function toggleFrame(shown) {
    if (!frame) return;
    frame.style.display = shown ? "block" : "none";
  }

  function open() {
    if (!frame) createFrame();
    toggleFrame(true);
    state.opened = true;
    button.setAttribute("aria-expanded", "true");
    button.setAttribute("aria-label", "Close chat");
  }

  function close() {
    toggleFrame(false);
    state.opened = false;
    button.setAttribute("aria-expanded", "false");
    button.setAttribute("aria-label", "Open chat");
    button.focus();
  }

  function applyFrameSize(height) {
    if (!frame) return;
    var max = window.innerHeight - 106; // bubble + margins
    var px = Math.min(Math.max(height || 600, 200), Math.max(max, 200));
    frame.style.height = px + "px";
  }

  // --- message channel -------------------------------------------------------

  window.addEventListener("message", function (event) {
    if (event.origin !== frameBase) return;
    var data = event.data || {};
    if (data.type === "chatbot:ready") {
      if (event.source) {
        event.source.postMessage(
          { type: "chatbot:locator", locator: locator },
          { targetOrigin: frameBase },
        );
      }
      applyFrameSize(600);
    } else if (data.type === "chatbot:size") {
      applyFrameSize(data.height);
    } else if (data.type === "chatbot:brand") {
      state.brand.colour = data.colour || state.brand.colour;
      state.brand.position = data.position || state.brand.position;
      state.brand.dir = data.dir || state.brand.dir;
      styleButton();
      positionFrame();
    } else if (data.type === "chatbot:close") {
      close();
    }
  });

  window.addEventListener("resize", positionFrame);

  // --- styles ----------------------------------------------------------------

  var css = document.createElement("style");
  css.textContent =
    widgetTokens +
    ".chatbot-widget-frame{position:fixed;bottom:5rem;border:0;border-radius:1rem;" +
    "box-shadow:var(--shadow);z-index:2147483000;background:var(--surface);" +
    "overflow:hidden;width:min(23.5rem, calc(100vw - 2.5rem));}" +
    "@media (max-width: 480px)" +
    "{.chatbot-widget-frame{bottom:0;width:calc(100vw - 1rem);border-radius:1rem 1rem 0 0;min-height:70dvh}}";
  document.head.appendChild(css);
  styleButton();
})();
