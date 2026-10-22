import Link from "next/link";
import { Icon } from "@/lib/icons";

export default function Home() {
  return (
    <main className="auth-page landing-page">
      <span className="brand-mark" aria-hidden="true">
        <Icon name="sparkle" size={22} />
      </span>
      <p className="eyebrow">Website Chatbot SaaS</p>
      <h1>Application foundation</h1>
      <p>
        Give your visitors answers grounded in your knowledge, and help your
        team continue the conversation.
      </p>
      <nav aria-label="Get started" className="action-row">
        <Link href="/login">Sign in</Link> ·{" "}
        <Link href="/register">Register</Link>
      </nav>
    </main>
  );
}
