import Link from "next/link";

export default function PrivacyPage() {
  return (
    <main style={{ maxWidth: 800, margin: "0 auto", padding: "48px 24px" }}>
      <h1>Privacy notice</h1>
      <p>Updated 28 October 2026</p>
      <h2>Who uses your information</h2>
      <p>
        The business whose chatbot you use determines why it collects your
        information and how its team uses it. The Osiris Labs operates this SaaS
        to process conversations and customer records for that business. We also
        use account, security and operational records to run and protect the
        service. Contact the business through its published support channel for
        questions about your conversation or a request to access or erase it.
      </p>
      <h2>Information processed</h2>
      <p>
        Depending on what you share and the features the business enables, the
        service processes your messages, contact details, channel identifiers,
        conversation history, delivery states, handoff records and feedback.
        Business staff accounts and access records support administration and
        security. Please avoid sending passwords, payment card details or other
        information the business does not need.
      </p>
      <h2>Connected channels and AI services</h2>
      <p>
        A business may connect WhatsApp, Facebook Messenger or Instagram through
        ManyOsirisChat, a separate application operated by The Osiris Labs.
        ManyOsirisChat manages the Meta connection, credentials, incoming
        webhooks and delivery. For a delegated channel it shares customer
        messages and relevant campaign context with this SaaS, which provides
        the business chatbot and team inbox. Meta credentials remain in
        ManyOsirisChat and are not shared with this SaaS.
      </p>
      <p>
        AI providers selected for the business may process the message and
        relevant business knowledge to generate a reply. AI answers can be
        inaccurate. The business can arrange a human handoff; the service is for
        that business&apos;s support, rather than a general-purpose assistant.
        Information is not used to train our own general-purpose AI model.
      </p>
      <h2>Access, retention and erasure</h2>
      <p>
        Authorized business staff and platform operators access data according
        to their roles. Conversation retention follows the business&apos;s
        configured policy. Stored channel-event payloads are cleared at that
        cutoff; limited event identifiers may remain for at least 30 days to
        prevent duplicate processing. Limited usage-accounting records may
        remain without message content or a link to the erased contact. A
        narrowly scoped, pseudonymous record derived from the connection and
        customer identifier may remain after erasure to prevent delayed or
        replayed events recreating the erased record. It is retained until that
        connection or organization is deleted and is not a copy of the
        conversation.
      </p>
      <p>
        A deletion request must cover every application holding your data.
        Disconnecting a channel alone does not erase its conversation history.
        The business or an authorized operator must complete erasure in this
        SaaS and, for connected channels, ManyOsirisChat. Operational backups
        follow the operator&apos;s recovery schedule; restored data must be
        subject to the same erasure instructions. We do not promise that
        disconnecting an account instantly removes data from backups.
      </p>
      <h2>Cookies and service providers</h2>
      <p>
        Necessary cookies support sign-in, request protection and widget
        sessions. Hosting, storage and configured AI services process data
        needed to provide the service. The business can request the applicable
        service-provider and hosting details from its operator. No specific
        storage country is promised by this notice.
      </p>
      <p>
        <Link href="/terms">Terms of use</Link>
      </p>
    </main>
  );
}
