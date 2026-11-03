"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { api, ApiError } from "@/lib/api";

// One-click accounts for the demo, each showing a different behaviour. All synthetic data.
const DEMO_PASSWORD = process.env.NEXT_PUBLIC_DEMO_PASSWORD ?? "demo1234";
const DEMO_ACCOUNTS = [
  { id: "CUST-2007", label: "Everyday questions" },
  { id: "CUST-2003", label: "Open dispute" },
  { id: "CUST-2009", label: "Classic card" },
];

export default function SignIn() {
  const router = useRouter();
  const [customerId, setCustomerId] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  // Already signed in: go straight to the chat.
  useEffect(() => {
    api.me().then(() => router.replace("/chat")).catch(() => {});
  }, [router]);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    await signIn(customerId.trim().toUpperCase(), password);
  }

  async function signIn(id: string, secret: string) {
    setBusy(true);
    setError("");
    try {
      await api.login(id, secret);
      router.replace("/chat");
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "We couldn't reach the service. Please try again.");
      setBusy(false);
    }
  }

  return (
    <main className="signin">
      <section className="signin-hero">
        <a className="wordmark" href="/">
          <b>Grounded</b>
          <span className="eyebrow">Card desk</span>
        </a>
        <div>
          <h1 className="headline serif">
            <span className="line"><span>Answers,</span></span>
            <span className="line"><span><em>with receipts.</em></span></span>
          </h1>
          <p className="lede">
            Ask about your card. Every fact comes with its source, declines follow the bank&apos;s rules, and
            anything uncertain goes to a person.
          </p>
          <div className="facts">
            <div><strong>Every</strong><span className="eyebrow">fact cited</span></div>
            <div><strong>0</strong><span className="eyebrow">guesses</span></div>
            <div><strong>1</strong><span className="eyebrow">human, when unsure</span></div>
          </div>
        </div>
      </section>

      <form className="signin-form" onSubmit={submit}>
        <span className="eyebrow">Sign in</span>
        <h2 className="serif">Welcome back.</h2>
        <label className="field">
          <span className="eyebrow">Customer ID</span>
          <input value={customerId} onChange={(e) => setCustomerId(e.target.value)} placeholder="CUST-2000"
                 autoComplete="username" required />
        </label>
        <label className="field">
          <span className="eyebrow">Password</span>
          <input type="password" value={password} onChange={(e) => setPassword(e.target.value)}
                 autoComplete="current-password" required />
        </label>
        {error && <p className="error" role="alert">{error}</p>}
        <button className="primary" disabled={busy}>
          {busy ? "Signing in…" : "Continue"} <span className="arrow">→</span>
        </button>
        <div className="demo">
          <span className="eyebrow">Or try a demo account</span>
          <div className="demo-list">
            {DEMO_ACCOUNTS.map((a) => (
              <button type="button" key={a.id} disabled={busy} onClick={() => signIn(a.id, DEMO_PASSWORD)}>
                <span>{a.label}</span>
                <span className="mono">{a.id}</span>
              </button>
            ))}
          </div>
        </div>
      </form>
    </main>
  );
}
