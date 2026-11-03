"use client";

import type { AgentReply } from "@/lib/api";

const STATUS_LABEL: Record<AgentReply["status"], string> = {
  answer: "Answered",
  decline_with_reason: "Declined by rule",
  raise_request: "Passed to a colleague",
  refuse: "Not something I can answer",
};

const TICKET = /^I've raised request (\S+) with our (\S+) team\. They aim to respond within (.+)\.$/;

// The message is written by the backend from validated claims (pipeline.render).
// This only styles it: citation markers, the sources line and ticket lines.
function parse(message: string) {
  const body: string[] = [];
  const tickets: { id: string; queue: string; sla: string }[] = [];
  let sources: string[] = [];
  for (const part of message.split("\n\n")) {
    const ticket = part.match(TICKET);
    if (ticket) tickets.push({ id: ticket[1], queue: ticket[2], sla: ticket[3] });
    else if (part.startsWith("Sources: ")) sources = part.slice("Sources: ".length).split("; ");
    else body.push(part);
  }
  return { body, tickets, sources };
}

function withCitations(text: string) {
  return text.split(/\s?\[(\d+(?:, \d+)*)\]/g).map((piece, i) =>
    i % 2 ? <sup key={i}>{piece.replace(/ /g, "")}</sup> : piece,
  );
}

// Timing, cost and trace IDs stay in the API response and traces for staff, not on the customer's screen.
const PATH_LABEL: Record<AgentReply["path"], string> = {
  rules: "Decided by the bank's rules",
  llm: "Checked against our policies",
  safe_fallback: "Passed on to keep you safe",
  customer_not_found: "Account not found",
  small_talk: "",
};

// "your account record (card_year_spend)" -> "Your account · card year spend"
function sourceLabel(label: string) {
  const field = label.match(/^your account record \((.+)\)$/);
  return field ? `Your account · ${field[1].replace(/_/g, " ")}` : label;
}

export function Answer({ reply }: { reply: AgentReply }) {
  const { body, tickets, sources } = parse(reply.message);

  // A greeting gets a plain reply: no status, no sources, no note on how it was decided.
  if (reply.path === "small_talk") {
    return <div className="answer">{body.map((p, i) => <p key={i}>{p}</p>)}</div>;
  }

  return (
    <div className="answer">
      <span className="status eyebrow" data-kind={reply.status}><i />{STATUS_LABEL[reply.status]}</span>
      {body.map((p, i) => <p key={i}>{withCitations(p)}</p>)}
      {tickets.map((t) => (
        <div className="ticket" key={t.id}>
          <span className="eyebrow">Request opened</span>
          <span className="eyebrow meta-right">Response within</span>
          <span className="serif">{t.id}</span>
          <span className="serif meta-right">{t.sla}</span>
          <span className="mono">{t.queue.replace("_", " ")} team</span>
        </div>
      ))}
      {sources.length > 0 && (
        <div className="sources">
          {sources.map((s) => {
            const [, n, label] = s.match(/^\[(\d+)\] (.*)$/) ?? [, "", s];
            return <span className="chip mono" key={s}><b>{n}</b>{sourceLabel(label)}</span>;
          })}
        </div>
      )}
      <div className="meta mono">
        <span>{PATH_LABEL[reply.path]}</span>
      </div>
    </div>
  );
}
