# Chatbot widget (P4-02, docs/09)

One script tag for the customer site; everything else is the sandboxed iframe
on this deployment.

## Embed

```html
<script
  src="https://<this-deployment>/widget/v1/loader.js"
  data-locator="<bot widget locator>"
></script>
```

- The **locator is public** (docs/05): it only names the bot. The authority
  lives server-side — a visitor session is a short-lived capability token
  bound to that bot (P4-01), requests are rate-limited, and allowed domains
  remain a defence signal.
- The loader draws the launch bubble and creates the **iframe** at
  `/widget/frame?locator=…` with
  `sandbox="allow-scripts allow-same-origin allow-forms"`. The iframe
  keeps its own origin (this deployment), so the iframe talks to the public
  widget API same-origin — no CORS, no third-party cookies — and the host
  page cannot script the frame beyond the postMessage channel.
- **Versioned asset URL** (`/widget/v1/loader.js`): breaking loader changes
  ship under a new directory after a provable need (iframe frame stays
  current automatically).
- The frame page carries its **own scoped headers**
  (`/widget/:path*` → `frame-ancestors http: https:`) so client sites can
  embed it while the dashboard keeps `frame-ancestors 'none'` (P2-00).

## postMessage protocol

| Direction | Message | Purpose |
|---|---|---|
| parent → iframe | `chatbot:locator` | the loader hands over the locator |
| iframe → parent | `chatbot:ready` | frame booted; parent answers with the locator |
| iframe → parent | `chatbot:size` | auto-height inside `window.innerHeight` bounds |
| iframe → parent | `chatbot:brand` | colour/position/dir so the bubble matches settings (P4-03) |
| iframe → parent | `chatbot:close` | Escape pressed inside the frame |

## States covered (docs/09)

loading · ready · typing · answer with citation chips · no-knowledge
(abstain) · paused · not ready · quota exceeded · rate limited · network
error with retry · graceful expired-session recovery (localStorage-backed
session, silently refreshed on 401). Keyboard accessible (focusable input,
labels, Escape closes), mobile layout, RTL (`dir` from bot settings).

Lead capture (docs/14 §11) is added with P4-04.
