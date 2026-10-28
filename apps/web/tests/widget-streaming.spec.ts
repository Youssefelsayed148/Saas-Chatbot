import { expect, type Page, test } from "@playwright/test";
import { registerOperator } from "./e2e-helpers";

/**
 * S.7: the widget's streamed replies (fetch + ReadableStream, Stop, typing
 * indicator, live-region announce at done only, one fallback to the buffered
 * endpoint).
 *
 * The first group mocks the API at the network edge, with a hand-driven
 * Server-Sent Events body, so progressive rendering is deterministic. The last
 * test drives the real stack on the offline stub model (no paid provider);
 * set STUB_STREAM_DELAY_MS (for example 150) in the environment of the test
 * run to also assert progressive growth through the real proxy.
 */

const LOCATOR = "stream";
const SESSION = {
  session_id: "11111111-1111-4111-8111-111111111111",
  token: "tok",
};

const CONFIG = {
  bot_name: "Stream bot",
  assistant_name: "Aida",
  business_name: "Acme",
  welcome_message: { en: "Hello", ar: "مرحبا" },
  opening_questions: [],
  colour: "#123456",
  position: "right",
  default_language: "en",
  dir: "ltr",
};

type StreamMode = "controlled" | "network-error" | "http-502" | "http-429";

declare global {
  interface Window {
    __push: (chunk: string) => void;
    __close: () => void;
    __streamAborted: boolean;
    __streamCalls: number;
  }
}

async function mockWidget(
  page: Page,
  mode: StreamMode,
  counters: { buffered: number },
) {
  await page.route(`**/api/public/v1/widgets/${LOCATOR}/config`, (route) =>
    route.fulfill({ json: { available: true, config: CONFIG } }),
  );
  await page.route(`**/api/public/v1/widgets/${LOCATOR}/sessions`, (route) =>
    route.fulfill({
      status: 201,
      json: {
        ...SESSION,
        expires_at: new Date(Date.now() + 3_600_000).toISOString(),
        config: CONFIG,
      },
    }),
  );
  await page.route("**/api/public/v1/sessions/*/messages", (route) => {
    if (route.request().method() === "GET") {
      return route.fulfill({ json: [] });
    }
    counters.buffered += 1;
    return route.fulfill({
      status: 201,
      json: {
        conversation_id: "c1",
        visitor_message: { id: "v-b", created_at: "2026-10-22T10:00:00Z" },
        ai_message: {
          id: "a-b",
          text: "Buffered answer.",
          citations: [],
          can_answer: true,
          needs_human: false,
          created_at: "2026-10-22T10:00:01Z",
        },
        kind: "answer",
        language: "en",
      },
    });
  });
  // The stream endpoint is replaced inside the page so the test controls
  // exactly when each SSE chunk arrives.
  await page.addInitScript((streamMode) => {
    const realFetch = window.fetch.bind(window);
    window.__streamAborted = false;
    window.__streamCalls = 0;
    window.fetch = (input: RequestInfo | URL, init?: RequestInit) => {
      const url =
        typeof input === "string"
          ? input
          : input instanceof URL
            ? input.href
            : input.url;
      if (!url.endsWith("/messages/stream")) return realFetch(input, init);
      window.__streamCalls += 1;
      if (streamMode === "network-error") {
        return Promise.reject(new TypeError("Failed to fetch"));
      }
      if (streamMode === "http-502") {
        return Promise.resolve(new Response("bad gateway", { status: 502 }));
      }
      if (streamMode === "http-429") {
        return Promise.resolve(
          new Response(
            JSON.stringify({
              error: { code: "RATE_LIMITED", message: "Slow down." },
            }),
            { status: 429, headers: { "content-type": "application/json" } },
          ),
        );
      }
      const encoder = new TextEncoder();
      let controller!: ReadableStreamDefaultController<Uint8Array>;
      const body = new ReadableStream<Uint8Array>({
        start(c) {
          controller = c;
        },
      });
      init?.signal?.addEventListener("abort", () => {
        window.__streamAborted = true;
        try {
          controller.error(new DOMException("aborted", "AbortError"));
        } catch {
          // already closed
        }
      });
      window.__push = (chunk: string) =>
        controller.enqueue(encoder.encode(chunk));
      window.__close = () => {
        try {
          controller.close();
        } catch {
          // the widget already cancelled the reader after `done`
        }
      };
      return Promise.resolve(
        new Response(body, {
          status: 200,
          headers: { "content-type": "text/event-stream; charset=utf-8" },
        }),
      );
    };
  }, mode);
}

function sse(event: string, data: unknown): string {
  return `event: ${event}\ndata: ${JSON.stringify(data)}\n\n`;
}

const DONE = (text: string) =>
  sse("done", {
    conversation_id: "c1",
    visitor_message: { id: "v1", created_at: "2026-10-22T10:00:00Z" },
    ai_message: {
      id: "a1",
      text,
      citations: [],
      can_answer: true,
      needs_human: false,
      created_at: "2026-10-22T10:00:01Z",
    },
    kind: "answer",
    language: "en",
  });

/** The text of the newest assistant bubble (without the feedback buttons). */
const lastReply = (page: Page) =>
  page.getByTestId("widget-ai-msg").last().locator(".md-body");

async function openFrame(page: Page) {
  await page.goto(`/widget/frame?locator=${LOCATOR}`);
  await expect(page.getByTestId("widget-title")).toHaveText("Stream bot");
}

async function ask(page: Page, text: string) {
  await page.getByTestId("widget-input").fill(text);
  await page.getByTestId("widget-send").click();
}

async function push(page: Page, chunk: string) {
  // The page-side controller exists once the widget has issued the request.
  await page.waitForFunction(() => typeof window.__push === "function");
  await page.evaluate((c) => window.__push(c), chunk);
}

test("text appears progressively, announces once at done, and persists the final id", async ({
  page,
}) => {
  const counters = { buffered: 0 };
  await mockWidget(page, "controlled", counters);
  await openFrame(page);
  await ask(page, "When do you open?");

  // Before the first character: typing indicator and Stop, no assistant bubble yet.
  await expect(page.getByTestId("widget-typing")).toBeVisible();
  await expect(page.getByTestId("widget-stop")).toBeVisible();
  await expect(page.getByTestId("widget-input")).toBeDisabled();
  await push(page, ": stream\n\n");
  await push(page, sse("verdict", { can_answer: true, released: true }));
  await expect(page.getByTestId("widget-typing")).toBeVisible();

  // First delta: the indicator goes away, the bubble starts filling.
  await push(page, sse("delta", { text: "We open " }));
  const bubble = page.getByTestId("widget-ai-msg").last();
  await expect(bubble).toHaveText("We open ");
  await expect(page.getByTestId("widget-typing")).toHaveCount(0);
  await expect(bubble).toHaveAttribute("aria-busy", "true");
  // While streaming the thread is not a live region and nothing is announced.
  await expect(page.locator("main.widget-thread")).toHaveAttribute(
    "aria-live",
    "off",
  );
  await expect(page.getByTestId("widget-announce")).toHaveText("");

  await push(page, sse("delta", { text: "9 to 5." }));
  await expect(bubble).toHaveText("We open 9 to 5.");
  await expect(page.getByTestId("widget-announce")).toHaveText("");
  await expect(page.getByTestId("widget-thumbs-up-a1")).toHaveCount(0);

  // Done: the persisted message replaces the bubble, announced once.
  await push(page, DONE("We open 9 to 5."));
  await page.evaluate(() => window.__close());
  await expect(page.getByTestId("widget-announce")).toHaveText(
    "We open 9 to 5.",
  );
  await expect(page.getByTestId("widget-thumbs-up-a1")).toBeVisible();
  await expect(page.getByTestId("widget-ai-msg")).toHaveCount(2); // welcome + reply
  await expect(page.getByTestId("widget-stop")).toHaveCount(0);
  await expect(page.getByTestId("widget-input")).toBeEnabled();
  await expect(page.locator("main.widget-thread")).toHaveAttribute(
    "aria-live",
    "polite",
  );
  expect(counters.buffered).toBe(0);
});

test("done is authoritative: a replaced answer overwrites what streamed", async ({
  page,
}) => {
  await mockWidget(page, "controlled", { buffered: 0 });
  await openFrame(page);
  await ask(page, "Question");
  await push(page, sse("delta", { text: "Partial that will not stick" }));
  await expect(page.getByTestId("widget-ai-msg").last()).toContainText(
    "Partial",
  );
  await push(page, DONE("The validated reply."));
  await page.evaluate(() => window.__close());
  await expect(lastReply(page)).toHaveText("The validated reply.");
  await expect(page.getByTestId("widget-announce")).toHaveText(
    "The validated reply.",
  );
});

test("a single cannot-confirm event shows at once with no typing text before it", async ({
  page,
}) => {
  await mockWidget(page, "controlled", { buffered: 0 });
  await openFrame(page);
  await ask(page, "Parachutes?");
  await push(
    page,
    sse("cannot_confirm", { text: "I don't have that information." }),
  );
  await expect(lastReply(page)).toHaveText("I don't have that information.");
  await push(page, DONE("I don't have that information."));
  await page.evaluate(() => window.__close());
  await expect(page.getByTestId("widget-announce")).toHaveText(
    "I don't have that information.",
  );
});

test("Arabic text streams intact and keeps automatic direction", async ({
  page,
}) => {
  await mockWidget(page, "controlled", { buffered: 0 });
  await openFrame(page);
  await ask(page, "متى تفتحون؟");
  await push(page, sse("delta", { text: "نفتح من " }));
  await push(page, sse("delta", { text: "التاسعة." }));
  const bubble = page.getByTestId("widget-ai-msg").last();
  await expect(bubble).toHaveText("نفتح من التاسعة.");
  await expect(bubble.locator(".md-body [dir=auto]")).toHaveCount(1);
});

test("Stop aborts the stream, removes the partial bubble and returns the text to the input", async ({
  page,
}) => {
  const counters = { buffered: 0 };
  await mockWidget(page, "controlled", counters);
  await openFrame(page);
  await ask(page, "Tell me everything");
  await push(page, sse("delta", { text: "Once upon" }));
  await expect(lastReply(page)).toHaveText("Once upon");
  await page.getByTestId("widget-stop").click();
  await expect
    .poll(() => page.evaluate(() => window.__streamAborted))
    .toBe(true);
  await expect(page.getByTestId("widget-ai-msg")).toHaveCount(1); // welcome only
  await expect(page.getByTestId("widget-visitor-msg")).toHaveCount(0);
  await expect(page.getByTestId("widget-input")).toHaveValue(
    "Tell me everything",
  );
  await expect(page.getByTestId("widget-input")).toBeEnabled();
  await expect(page.getByTestId("widget-stop")).toHaveCount(0);
  await expect(page.getByTestId("widget-announce")).toHaveText("");
  expect(counters.buffered).toBe(0); // Stop is not a failure: no fallback
});

for (const mode of ["network-error", "http-502"] as const) {
  test(`stream failure (${mode}) before any text falls back to the buffered endpoint once`, async ({
    page,
  }) => {
    const counters = { buffered: 0 };
    await mockWidget(page, mode, counters);
    await openFrame(page);
    await ask(page, "When do you open?");
    await expect(lastReply(page)).toHaveText("Buffered answer.");
    expect(counters.buffered).toBe(1);
    expect(await page.evaluate(() => window.__streamCalls)).toBe(1);
    await expect(page.getByTestId("widget-error")).toHaveCount(0);
    await expect(page.getByTestId("widget-input")).toBeEnabled();
  });
}

test("an in-stream error before any text also falls back once", async ({
  page,
}) => {
  const counters = { buffered: 0 };
  await mockWidget(page, "controlled", counters);
  await openFrame(page);
  await ask(page, "When do you open?");
  await push(page, sse("error", { code: "INTERNAL_ERROR", message: "x" }));
  await expect(lastReply(page)).toHaveText("Buffered answer.");
  expect(counters.buffered).toBe(1);
});

test("a stream that dies after text drops the partial and does not replay it", async ({
  page,
}) => {
  const counters = { buffered: 0 };
  await mockWidget(page, "controlled", counters);
  await openFrame(page);
  await ask(page, "When do you open?");
  await push(page, sse("delta", { text: "Half an ans" }));
  await expect(lastReply(page)).toHaveText("Half an ans");
  await page.evaluate(() => window.__close()); // ends without `done`
  await expect(page.getByTestId("widget-ai-msg")).toHaveCount(1);
  await expect(page.getByTestId("widget-error")).toBeVisible();
  expect(counters.buffered).toBe(0);
});

test("an application refusal (429) is shown as in the buffered path, with no fallback", async ({
  page,
}) => {
  const counters = { buffered: 0 };
  await mockWidget(page, "http-429", counters);
  await openFrame(page);
  await ask(page, "When do you open?");
  await expect(page.getByTestId("widget-error")).toBeVisible();
  expect(counters.buffered).toBe(0);
});

test("real stack on the stub model streams through the proxy and persists at done", async ({
  page,
}) => {
  test.setTimeout(240_000);
  const { tenantId } = await registerOperator(page, "WidgetStream", {
    botName: "Stream real",
  });
  await page.getByRole("link", { name: /Open Stream real/ }).click();
  await page.waitForURL(/\/settings$/);
  const botId = new URL(page.url()).pathname.split("/")[4];
  const bot = (await (
    await page.request.get(`/api/v1/tenants/${tenantId}/bots/${botId}`)
  ).json()) as { widget_locator: string };
  const csrf = await page.evaluate(() => {
    const entry = document.cookie
      .split("; ")
      .find((part) => part.startsWith("chatbot_csrf="));
    return entry ? entry.split("=")[1] : "";
  });
  const base = `/api/v1/tenants/${tenantId}/bots/${botId}`;
  const patch = await page.request.patch(base, {
    headers: { "X-CSRF-Token": csrf },
    data: { status: "active" },
  });
  expect(patch.ok()).toBeTruthy();
  const upload = await page.request.post(`${base}/sources/files`, {
    headers: { "X-CSRF-Token": csrf },
    multipart: {
      files: {
        name: "hours.md",
        mimeType: "text/markdown",
        buffer: Buffer.from(
          "---\ntitle: Stream hours\nsource_url: https://stream.example.com/hours\nlanguage: en\n---\n\n# Stream opening hours\n\nStream Store opens at 7:00 every day of the week.\n",
          "utf-8",
        ),
      },
    },
  });
  expect(upload.status()).toBe(201);
  const start = await page.request.post(`${base}/ingestion`, {
    headers: { "X-CSRF-Token": csrf },
    data: {},
  });
  expect([201, 202]).toContain(start.status());
  let status = "";
  for (let attempt = 0; attempt < 60; attempt += 1) {
    const jobs = (await (await page.request.get(`${base}/jobs`)).json()) as {
      status: string;
    }[];
    status = jobs[0]?.status ?? "missing";
    if (status === "succeeded" || status === "failed") break;
    await page.waitForTimeout(500);
  }
  expect(status).toBe("succeeded");
  const revisions = (await (
    await page.request.get(`${base}/revisions`)
  ).json()) as { revisions: { id: string; status: string }[] };
  const draft = revisions.revisions.find((row) => row.status === "draft");
  const publish = await page.request.post(
    `${base}/revisions/${String(draft?.id)}/publish`,
    { headers: { "X-CSRF-Token": csrf } },
  );
  expect(publish.status()).toBe(200);

  // Record every distinct text the assistant bubble shows while the reply streams.
  await page.addInitScript(() => {
    (window as unknown as { __seen: string[] }).__seen = [];
    const record = () => {
      const bubbles = document.querySelectorAll("[data-testid=widget-ai-msg]");
      const last = bubbles[bubbles.length - 1];
      const seen = (window as unknown as { __seen: string[] }).__seen;
      const text = last?.textContent ?? "";
      if (text && seen[seen.length - 1] !== text) seen.push(text);
    };
    new MutationObserver(record).observe(document, {
      subtree: true,
      childList: true,
      characterData: true,
    });
  });
  const streamResponse = page.waitForResponse(
    (response) =>
      response.url().endsWith("/messages/stream") &&
      response.request().method() === "POST",
    { timeout: 120_000 },
  );
  await page.goto(
    `/widget/frame?locator=${encodeURIComponent(bot.widget_locator)}`,
  );
  await expect(page.getByTestId("widget-input")).toBeVisible();
  await ask(page, "When do you open?");
  const response = await streamResponse;
  expect(response.status()).toBe(200);
  expect(response.headers()["content-type"]).toContain("text/event-stream");
  expect(response.headers()["cache-control"]).toContain("no-transform");
  await expect(page.getByTestId("widget-ai-msg").last()).toContainText("7:00", {
    timeout: 60_000,
  });
  await expect(page.getByTestId("widget-announce")).toContainText("7:00");
  await expect(page.getByTestId("widget-stop")).toHaveCount(0);
  const seen = await page.evaluate(
    () => (window as unknown as { __seen: string[] }).__seen,
  );
  if (process.env.STUB_STREAM_DELAY_MS) {
    // The stub emits a few characters at a time: the bubble must have shown
    // growing intermediate text, not just the final string.
    const final = seen[seen.length - 1] ?? "";
    const partial = seen.filter(
      (text) => text.length < final.length && final.startsWith(text),
    );
    expect(partial.length).toBeGreaterThan(1);
  }
});
