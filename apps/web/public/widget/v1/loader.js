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
    brand: { colour: "#1f7a5c", position: "right", dir: "ltr" },
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
    var colour = state.brand.colour;
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
    button.style.boxShadow = "0 6px 20px rgba(15,35,60,0.35)";
    button.style.cursor = "pointer";
    button.style.zIndex = "2147483000";
    button.style.color = "#ffffff";
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
    frame.setAttribute("sandbox", "allow-scripts allow-same-origin allow-forms");
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
          { targetOrigin: frameBase }
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

  styleButton();

  var css = document.createElement("style");
  css.textContent =
    ".chatbot-widget-frame{position:fixed;bottom:5rem;border:0;border-radius:1rem;" +
    "box-shadow:0 10px 40px rgba(10,25,50,0.35);z-index:2147483000;background:#ffffff;" +
    "overflow:hidden;width:min(23.5rem, calc(100vw - 2.5rem));}" +
    "@media (max-width: 480px)" +
    "{.chatbot-widget-frame{bottom:0;width:calc(100vw - 1rem);border-radius:1rem 1rem 0 0;min-height:70dvh}}";
  document.head.appendChild(css);
})();
