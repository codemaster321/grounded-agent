"""A small chat page over the agent.

  streamlit run app.py

Each message is answered on its own: the agent does not remember earlier messages.
The customer picker stands in for a login, which would supply customer_id in production.
"""
import json
import os

os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")

import streamlit as st  # noqa: E402
from dotenv import load_dotenv  # noqa: E402

load_dotenv()

from agent.pipeline import Agent  # noqa: E402
from agent.tools import DATA_DIR  # noqa: E402


@st.cache_resource
def load_agent() -> Agent:
    return Agent()  # builds the search index once, not on every message


def customer_ids() -> list[str]:
    return sorted(json.loads((DATA_DIR / "accounts.json").read_text(encoding="utf-8")))


def details(result) -> str:
    usage = result.trace["usage"]
    return (f"status={result.status} · path={result.path} · {result.trace['total_ms']}ms · "
            f"AI calls={usage['llm_calls']} · cost=${usage['cost_usd']:.5f}")


st.title("Card service agent")
st.caption("Each message is answered on its own. The agent does not remember earlier messages.")
customer_id = st.selectbox("Customer (stands in for a login)", customer_ids())

if st.session_state.get("customer_id") != customer_id:
    st.session_state.customer_id = customer_id
    st.session_state.messages = []  # one customer must never see another's conversation

for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["text"])
        if message.get("details"):
            st.caption(message["details"])

if question := st.chat_input("Ask about your card"):
    st.session_state.messages.append({"role": "user", "text": question})
    with st.spinner("Checking..."):
        result = load_agent().answer(customer_id, question)
    st.session_state.messages.append({"role": "assistant", "text": result.customer_message, "details": details(result)})
    st.rerun()
