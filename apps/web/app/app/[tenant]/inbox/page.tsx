import { InboxList } from "@/lib/inbox-list";
import { Icon } from "@/lib/icons";
export default function InboxPage() {
  return (
    <div className="inbox-workspace">
      <InboxList />
      <section className="thread-placeholder panel">
        <span className="empty-symbol" aria-hidden="true">
          <Icon name="sparkle" size={22} />
        </span>
        <h2>Every conversation, in context</h2>
        <p className="muted">
          Select a conversation to see its thread and available actions.
        </p>
      </section>
    </div>
  );
}
