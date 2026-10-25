import { InboxList } from "@/lib/inbox-list";

export default function InboxPage() {
  return (
    <div className="inbox-workspace">
      <InboxList />
      <section className="thread-placeholder panel">
        <h2>Select a conversation</h2>
        <p className="muted">
          Pick one from the list to read the thread and reply.
        </p>
      </section>
    </div>
  );
}
