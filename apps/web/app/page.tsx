import { Icon } from "@/lib/icons";
import { LinkButton } from "@/lib/ui";

export default function Home() {
  return (
    <main className="auth-page landing-page">
      <span className="brand-mark" aria-hidden="true">
        <Icon name="sparkle" size={22} />
      </span>
      <p className="eyebrow">AI chatbot and human inbox</p>
      <h1>Website Chatbot</h1>
      <p className="page-purpose">
        An AI chatbot for your website with a human inbox. Answer visitors
        instantly, hand off to your team when it matters.
      </p>
      <nav aria-label="Get started" className="action-row">
        <LinkButton href="/login" variant="primary" iconEnd="arrow-right">
          Sign in
        </LinkButton>
      </nav>
    </main>
  );
}
