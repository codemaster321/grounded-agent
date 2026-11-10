"use client";

import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { Answer } from "@/components/Answer";
import { api, ApiError, type Me, type Turn } from "@/lib/api";

const SUGGESTIONS = [
  "What is the markup if I use my card abroad?",
  "Was my annual fee waived this year?",
  "Please increase my credit limit.",
  "I don't recognise a transaction on my card.",
  "Can I add travel insurance to my card?",
];

const STAGES = ["Reading your account", "Searching the policies", "Checking the answer"];

function greeting() {
  const hour = new Date().getHours();
  return hour < 12 ? "Good morning" : hour < 18 ? "Good afternoon" : "Good evening";
}

export default function Chat() {
  const router = useRouter();
  const [me, setMe] = useState<Me | null>(null);
  const [turns, setTurns] = useState<Turn[]>([]);
  const [draft, setDraft] = useState("");
  const [pending, setPending] = useState(false);
  const [stage, setStage] = useState(0);
  const [notice, setNotice] = useState("");
  const end = useRef<HTMLDivElement>(null);

  useEffect(() => {
    Promise.all([api.me(), api.history()])
      .then(([who, past]) => { setMe(who); setTurns(past.messages); })
      .catch(() => router.replace("/"));
  }, [router]);

  useEffect(() => { end.current?.scrollIntoView({ behavior: "smooth", block: "end" }); }, [turns, pending]);

  useEffect(() => {
    if (!pending) return;
    setStage(0);
    const timer = setInterval(() => setStage((s) => Math.min(s + 1, STAGES.length - 1)), 1400);
    return () => clearInterval(timer);
  }, [pending]);

  async function ask(question: string) {
    if (!question.trim() || pending) return;
    setDraft("");
    setNotice("");
    setTurns((t) => [...t, { role: "customer", text: question }]);
    setPending(true);
    try {
      const reply = await api.ask(question);
      setTurns((t) => [...t, reply]);
    } catch (e) {
      if (e instanceof ApiError && e.status === 401) return router.replace("/");
      setTurns((t) => t.slice(0, -1));
      setDraft(question);
      setNotice(e instanceof ApiError ? e.message : "We couldn't reach the service. Please try again.");
    } finally {
      setPending(false);
    }
  }

  async function signOut() {
    await api.logout().catch(() => {});
    router.replace("/");
  }

  async function newChat() {
    if (pending) return;
    await api.clearHistory().catch(() => {});
    setTurns([]);
    setNotice("");
  }

  if (!me) return null;
  const firstName = me.name?.split(" ")[0];

  return (
    <>
      <header className="topbar">
        <a className="wordmark" href="/chat"><b>Grounded</b><span className="eyebrow">Card desk</span></a>
        <nav>
          <span className="who eyebrow">{me.card_product ? `${me.card_product} card · ` : ""}{me.customer_id}</span>
          {turns.length > 0 && <button className="link" onClick={newChat} disabled={pending}>New chat</button>}
          <button className="link" onClick={signOut}>Sign out</button>
        </nav>
      </header>

      <main className="thread">
        {turns.length === 0 && !pending && (
          <section className="empty">
            <h1 className="serif">{greeting()}{firstName ? "," : "."}<br /><em>{firstName ? `${firstName}.` : "How can I help?"}</em></h1>
            <p>Ask anything about your card. Every answer shows where it came from, and I&apos;ll pass you to a colleague if I&apos;m not sure.</p>
            <ol className="suggestions">
              {SUGGESTIONS.map((s, i) => (
                <li key={s}>
                  <button onClick={() => ask(s)}>
                    <span className="mono">{String(i + 1).padStart(2, "0")}</span>{s}<span className="arrow">→</span>
                  </button>
                </li>
              ))}
            </ol>
          </section>
        )}

        {turns.map((turn, i) =>
          turn.role === "customer" ? (
            <article className="turn" key={i}>
              <span className="eyebrow">You asked</span>
              <p className="question serif">{turn.text}</p>
              {pending && i === turns.length - 1 && (
                <div className="pending mono" aria-live="polite"><span className="bar" />{STAGES[stage]}…</div>
              )}
              {turns[i + 1]?.role === "agent" && <Answer reply={turns[i + 1] as Extract<Turn, { role: "agent" }>} />}
            </article>
          ) : null,
        )}
        <div ref={end} />
      </main>

      <footer className="composer">
        <form onSubmit={(e) => { e.preventDefault(); ask(draft); }}>
          <input value={draft} onChange={(e) => setDraft(e.target.value)} placeholder="Ask about your card"
                 maxLength={1000} aria-label="Your question" disabled={pending} autoFocus />
          <button className="send" disabled={!draft.trim() || pending} aria-label="Send">↑</button>
        </form>
        <p className="fine mono">{notice || "Each question is answered on its own. Answers cite the bank's policies."}</p>
      </footer>
    </>
  );
}
