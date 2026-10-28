import Link from "next/link";

export default function TermsPage() {
  return (
    <main style={{ maxWidth: 800, margin: "0 auto", padding: "48px 24px" }}>
      <h1>Terms of use</h1>
      <p>Updated 28 October 2026</p>
      <h2>Service and responsibilities</h2>
      <p>
        The Osiris Labs provides a business chatbot, knowledge tools and team
        inbox. The business using the service is responsible for the content it
        supplies, its authority to process customer information, instructions
        given to staff, required notices and lawful use of connected channels.
        These terms do not replace an applicable service agreement or data
        processing agreement with that business.
      </p>
      <h2>Connected channels</h2>
      <p>
        ManyOsirisChat is a separate application that provides Meta channel
        connectivity. This SaaS processes the delegated conversation on the
        business&apos;s instructions; it does not receive Meta access tokens or
        independently manage Meta webhooks. Channel availability, permissions,
        opt-in requirements and messaging windows continue to apply. Connecting
        a channel does not grant permission to send unsolicited messages or
        override Meta&apos;s restrictions.
      </p>
      <h2>AI and human support</h2>
      <p>
        Automated replies are generated for the specific business using its
        configured information. They may be incomplete or inaccurate and do not
        guarantee prices, availability, outcomes or professional advice. Ask the
        business for human support when an answer needs confirmation. Staff must
        review sensitive matters and use appropriate human handoff.
      </p>
      <h2>Account security and acceptable use</h2>
      <p>
        Keep credentials private and use only accounts and resources you are
        authorized to access. Do not attempt to access another
        organization&apos;s data, bypass rate limits or messaging controls,
        upload malicious material, or use the service for unlawful or abusive
        messaging. Service access may be restricted to protect customers and
        resolve misuse.
      </p>
      <h2>Data requests and service changes</h2>
      <p>
        The business handles customer data requests and instructs authorized
        operators to complete deletion across connected applications. Removing
        access or disconnecting a channel is not the same as erasure. Retention,
        limited replay-prevention records and backups are described in the
        privacy notice. The operator may update the service and these terms; any
        separately agreed commercial terms remain subject to that agreement.
      </p>
      <p>
        <Link href="/privacy">Privacy notice</Link>
      </p>
    </main>
  );
}
