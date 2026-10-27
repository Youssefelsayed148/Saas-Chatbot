import type { ChangeEvent } from "react";
import type { InboxMessage } from "@/lib/api";

const reasons: Record<string, string> = {
  window_closed:
    "The reply window has closed. An approved template is required.",
  template_required:
    "An approved template is required to contact this recipient.",
  recipient_unreachable: "The recipient could not be reached.",
  connection_paused: "The channel connection is paused.",
  connection_revoked: "The channel connection was revoked.",
  secret_unavailable:
    "The connection secret cannot be read. Contact support.",
  many_unreachable: "Delivery failed after repeated attempts to reach Many.",
  channel_disconnected: "The channel is disconnected.",
  rate_limited: "The channel delivery limit was reached.",
  invalid_many_target:
    "The channel delivery address is unavailable. Contact support.",
  previous_part_failed: "A previous part of this reply failed to send.",
  message_too_long: "The message was too long for this channel.",
  unknown: "The channel could not deliver this message.",
};

export function ChannelDelivery({
  channel,
  message,
  onResend,
  resendBusy,
}: {
  channel: string;
  message: Pick<InboxMessage, "sender_type" | "delivery_status" | "error_code">;
  /** Offered only for messages that failed while the connection was paused. */
  onResend?: () => void;
  resendBusy?: boolean;
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
    unconfirmed: "Not confirmed",
  }[message.delivery_status];
  return (
    <p
      className="delivery-state"
      role="status"
      dir="auto"
      data-testid="channel-delivery"
      data-state={message.delivery_status}
    >
      <span>
        {label}
        {message.delivery_status === "failed"
          ? `: ${reasons[message.error_code ?? ""] ?? "The channel could not deliver this message. Contact support."}`
          : ""}
        {message.delivery_status === "unconfirmed"
          ? ": the channel has not confirmed delivery yet."
          : ""}
      </span>
      {onResend &&
        message.delivery_status === "failed" &&
        message.error_code === "connection_paused" && (
          <button
            type="button"
            className="quiet-button"
            disabled={resendBusy}
            onClick={onResend}
          >
            Send again
          </button>
        )}
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
        <p
          id="channel-reply-block"
          role="note"
          dir="auto"
          className="paused-composer"
          data-testid="paused-composer"
        >
          {block}
        </p>
      )}
      <button disabled={!value.trim() || busy || !!block}>Send reply</button>
    </>
  );
}
