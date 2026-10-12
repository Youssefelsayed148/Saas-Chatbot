import Link from "next/link";

export default function Home() {
  return (
    <main>
      <p className="eyebrow">Website Chatbot SaaS</p>
      <h1>Application foundation</h1>
      <p>
        The frontend is running. Product features will be added in individually
        approved implementation tickets.
      </p>
      <nav>
        <Link href="/login">Sign in</Link> ·{" "}
        <Link href="/register">Register</Link>
      </nav>
    </main>
  );
}
