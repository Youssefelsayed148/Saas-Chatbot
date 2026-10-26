import { expect, type Page, test } from "@playwright/test";

import {
  handoffFromTurn,
  nextPollDelay,
  parsePollHint,
  POLL_BASE_MS,
  POLL_MAX_MS,
  shouldPoll,
} from "../lib/widget-polling";
import { registerStaffSession } from "./e2e-helpers";

/**
 * H5: the widget polls only while a human reply or a scheduled follow-up can
 * still arrive (X-Poll-Hint: active), backs off on errors and stops when idle.
 * The first group are the pure rules; the second drives the real frame with the
 * network edge mocked.
 */

test.describe("polling rules", () => {
  test("the server hint wins; a handoff only counts until a hint arrives", () => {
    expect(shouldPoll({ hint: "active", handoff: false, hidden: false })).toBe(
      true,
    );
    expect(shouldPoll({ hint: "idle", handoff: true, hidden: false })).toBe(
      false,
    );
    expect(shouldPoll({ hint: null, handoff: true, hidden: false })).toBe(true);
    expect(shouldPoll({ hint: null, handoff: false, hidden: false })).toBe(
      false,
    );
  });

  test("a hidden tab never polls", () => {
    expect(shouldPoll({ hint: "active", handoff: true, hidden: true })).toBe(
      false,
    );
  });

  test("hint parsing and handoff detection", () => {
    expect(parsePollHint("active")).toBe("active");
    expect(parsePollHint(" Idle ")).toBe("idle");
    expect(parsePollHint("other")).toBeNull();
    expect(parsePollHint(null)).toBeNull();
    expect(handoffFromTurn("waiting_human", null)).toBe(true);
    expect(handoffFromTurn("answer", true)).toBe(true);
    expect(handoffFromTurn("answer", false)).toBe(false);
    expect(handoffFromTurn(undefined, undefined)).toBe(false);
  });

  test("errors back off exponentially up to a cap and success resets", () => {
    expect(nextPollDelay(0)).toBe(POLL_BASE_MS);
    expect(nextPollDelay(1)).toBe(POLL_BASE_MS * 2);
    expect(nextPollDelay(2)).toBe(POLL_BASE_MS * 4);
    expect(nextPollDelay(50)).toBe(POLL_MAX_MS);
    expect(nextPollDelay(-1)).toBe(POLL_BASE_MS);
  });
});

const LOCATOR = "polling";

type Turn = { kind: string; needsHuman: boolean };

/** Mock the widget API. `hints` is consumed one per GET (the last repeats). */
async function mockWidget(
  page: Page,
  options: { turn: Turn; hints: ("active" | "idle")[]; agentOnPoll?: number },
) {
  const config = {
    bot_name: "Poll bot",
    assistant_name: "Aida",
    business_name: "Acme",
    welcome_message: { en: "Hello there", ar: "" },
    opening_questions: [],
    colour: "#123456",
    position: "right",
    default_language: "en",
    dir: "ltr",
  };
  const state = { gets: 0 };
  await page.route(`**/api/public/v1/widgets/${LOCATOR}/config`, (route) =>
    route.fulfill({ json: { available: true, config } }),
  );
  await page.route(`**/api/public/v1/widgets/${LOCATOR}/sessions`, (route) =>
    route.fulfill({
      status: 201,
      json: {
        session_id: "22222222-2222-4222-8222-222222222222",
        token: "tok",
        expires_at: new Date(Date.now() + 3_600_000).toISOString(),
        config,
      },
    }),
  );
  await page.route("**/api/public/v1/sessions/*/messages/stream", (route) =>
    route.fulfill({ status: 502, body: "bad gateway" }),
  );
  // The poll carries a ?since= cursor, so match the path with or without a query.
  await page.route(
    /\/api\/public\/v1\/sessions\/[^/]+\/messages(\?.*)?$/,
    (route) => {
      if (route.request().method() === "GET") {
        const hint =
          options.hints[Math.min(state.gets, options.hints.length - 1)];
        state.gets += 1;
        const rows =
          options.agentOnPoll === state.gets
            ? [
                {
                  id: "agent-1",
                  sender_type: "agent",
                  text: "A human here, how can I help?",
                  citations: [],
                  needs_human: false,
                  created_at: "2026-10-25T10:00:05Z",
                },
              ]
            : [];
        return route.fulfill({
          json: rows,
          headers: { "X-Poll-Hint": hint },
        });
      }
      return route.fulfill({
        status: 201,
        json: {
          conversation_id: "c1",
          visitor_message: { id: "v-1", created_at: "2026-10-25T10:00:00Z" },
          ai_message: options.turn.needsHuman
            ? null
            : {
                id: "a-1",
                text: "Returns are accepted within 14 days.",
                citations: [],
                can_answer: true,
                needs_human: false,
                created_at: "2026-10-25T10:00:01Z",
              },
          kind: options.turn.kind,
          language: "en",
        },
      });
    },
  );
  return state;
}

async function openAndAsk(page: Page, question: string) {
  await registerStaffSession(page, "widget-polling");
  await page.goto(`/widget/sample?locator=${LOCATOR}`);
  await page.getByTestId("widget-bubble").click();
  const frame = page.frameLocator("[data-testid=widget-frame]");
  await expect(frame.getByTestId("widget-title")).toHaveText("Poll bot");
  await frame.getByTestId("widget-input").fill(question);
  await frame.getByTestId("widget-send").click();
  return frame;
}

test("an answered conversation is looked at once and then not polled", async ({
  page,
}) => {
  const state = await mockWidget(page, {
    turn: { kind: "answer", needsHuman: false },
    hints: ["idle"],
  });
  const frame = await openAndAsk(page, "What is the return window?");
  await expect(frame.getByTestId("widget-ai-msg").last()).toContainText(
    "Returns are accepted",
  );
  await expect.poll(() => state.gets).toBe(1); // the single look after the turn
  await page.waitForTimeout(5000); // the old 2 s timer would have fired twice
  expect(state.gets).toBe(1);
});

test("a handoff starts polling, shows the agent reply and stops when idle", async ({
  page,
}) => {
  const state = await mockWidget(page, {
    turn: { kind: "waiting_human", needsHuman: true },
    hints: ["active", "active", "idle"],
    agentOnPoll: 2,
  });
  const frame = await openAndAsk(page, "I want to talk to a person");
  await expect(frame.getByText("A human here, how can I help?")).toBeVisible({
    timeout: 15000,
  });
  await expect.poll(() => state.gets, { timeout: 15000 }).toBe(3);
  await page.waitForTimeout(5000);
  expect(state.gets).toBe(3); // the idle hint stopped the loop
});
