import type { ChangeEvent } from "react";
import type { InboxMessage } from "@/lib/api";

const reasons: Record<string, string> = {
  window_closed:
    "The reply window has closed. An approved template is required.",
  template_required:
    "An approved template is required to contact this recipient.",
  recipient_unreachable: "The recipient could not be reached.",
  connection_paused: "The channel connection is paused or revoked.",
  many_unreachable: "Delivery failed after repeated attempts to reach Many.",
  channel_disconnected: "The channel is disconnected.",
  rate_limited: "The channel delivery limit was reached.",
  invalid_many_target:
    "The channel delivery address is unavailable. Contact support.",
  previous_part_failed: "A previous part of this reply failed to send.",
};

export function ChannelDelivery({
  channel,
  message,
}: {
  channel: string;
  message: Pick<InboxMessage, "sender_type" | "delivery_status" | "error_code">;
}) {
  if (
    channel === "website" ||
    !["ai", "agent"].includes(message.sender_type) ||
    !message.delivery_status
  )
    return null;
  const label = {
    pending: "Pending",
    sent: "Sent",
    delivered: "Delivered",
    read: "Read",
    failed: "Failed",
  }[message.delivery_status];
  return (
    <p
      className="muted"
      role="status"
      dir="auto"
      data-testid="channel-delivery"
    >
      {label}
      {message.delivery_status === "failed"
        ? `: ${reasons[message.error_code ?? ""] ?? "The channel could not deliver this message. Contact support."}`
        : ""}
    </p>
  );
}

export function connectionReplyBlock(
  channel: string,
  status?: string,
): string | null {
  if (channel === "website" || status === "active") return null;
  return status === "revoked"
    ? "This channel connection was revoked. Replies are disabled."
    : "This channel connection is paused. Replies are disabled until it resumes.";
}

export function ChannelReplyFields({
  value,
  busy,
  block,
  onChange,
}: {
  value: string;
  busy: boolean;
  block: string | null;
  onChange: (event: ChangeEvent<HTMLTextAreaElement>) => void;
}) {
  return (
    <>
      <label>
        Reply
        <textarea
          dir="auto"
          disabled={!!block || busy}
          aria-describedby={block ? "channel-reply-block" : undefined}
          aria-label="Reply"
          value={value}
          maxLength={4000}
          onChange={onChange}
          rows={3}
        />
      </label>
      {block && (
        <p id="channel-reply-block" role="note" dir="auto">
          {block}
        </p>
      )}
      <button disabled={!value.trim() || busy || !!block}>Send reply</button>
    </>
  );
}
