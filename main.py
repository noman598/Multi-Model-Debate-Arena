import streamlit as st

from services.chat_utilities import get_answer
from services.get_models import get_ollama_models_list
from services.get_title import get_title
from db.conversations import (
    create_new_conversation,
    add_message,
    get_conversation,
    get_all_conversations,
)
st.write("4")
st.set_page_config(page_title="Multi-Model Debate Arena", layout="wide")

st.title("🏟️ Multi-Model Debate Arena")

# ---- Models ----
if "OLLAMA_MODELS" not in st.session_state:
    st.session_state.OLLAMA_MODELS = get_ollama_models_list()

# selected_model = st.selectbox("Select Model", st.session_state.OLLAMA_MODELS)
selected_models = st.multiselect(
    "Select Models",
    st.session_state.OLLAMA_MODELS,
    max_selections=3
)

# ---- Session state ----
st.session_state.setdefault("conversation_id", None)
st.session_state.setdefault("conversation_title", None)
st.session_state.setdefault("chat_history", [])  # [{role, content}]

# ---- Sidebar: conversations ----
with st.sidebar:
    st.header("💬 Chat History")
    conversations = get_all_conversations()  # {conv_id: title}

    if st.button("➕ New Chat"):
        st.session_state.conversation_id = None
        st.session_state.conversation_title = None
        st.session_state.chat_history = []

    for cid, title in conversations.items():
        is_current = cid == st.session_state.conversation_id
        label = f"**{title}**" if is_current else title
        if st.button(label, key=f"conv_{cid}"):
            doc = get_conversation(cid) or {}
            st.session_state.conversation_id = cid
            st.session_state.conversation_title = doc.get("title", "Untitled")
            st.session_state.chat_history = [
                {"role": m["role"], "content": m["content"]} for m in doc.get("messages", [])
            ]
    

# ---- Show chat so far ----
for msg in st.session_state.chat_history:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

# st.write("4")
# ---- Chat input ----
user_query = st.chat_input("Ask AI...")
if user_query:
    # 1) Show + store user message in UI state
    st.chat_message("user").markdown(user_query)
    st.session_state.chat_history.append({"role": "user", "content": user_query})

    # 2) Persist to DB (create convo on first message, else append)
    if st.session_state.conversation_id is None:
        try:
            title = get_title(selected_models[0], user_query) or "New Chat"
        except Exception:
            title = "New Chat"
        conv_id = create_new_conversation(title=title, role="user", content=user_query)
        st.session_state.conversation_id = conv_id
        st.session_state.conversation_title = title
    else:
        add_message(st.session_state.conversation_id, "user", user_query)

    # 3) Get assistant response (direct service)
    try:
        print(selected_models)
        assistant_text = {model:get_answer(model,st.session_state.chat_history) for model in selected_models}
        print(type(assistant_text))
        print(assistant_text)
        st.session_state.responses_ready = True
        # assistant_text = get_answer(selected_model, st.session_state.chat_history)
    except Exception as e:
        assistant_text = f"[Error getting response: {e}]"

    # # 4) Show + store assistant message
    # with st.chat_message("assistant"):
    #     st.markdown(assistant_text)
    # st.session_state.chat_history.append({"role": "assistant", "content": assistant_text})

    # 5) Persist assistant message
    if st.session_state.conversation_id:
        add_message(st.session_state.conversation_id, "assistant", assistant_text)

        # --- Show responses only if ready ---
    # if st.session_state.responses_ready:
    st.divider()
    st.subheader("🤖 Model Responses")
    cols = st.columns(len(assistant_text))
    # col1, col2, col3 = st.columns(3)
    for col, (key, value) in zip(cols,assistant_text.items()):
        with col:
            st.markdown(f"### 🦙 {key}")
            st.info(value)
            st.caption("⏱️ Response time: 1.2s")


        # with col1:
        #     st.markdown("### 🦙 LLaMA 3")
        #     st.info(DUMMY_RESPONSES["llama3"])
        #     st.caption("⏱️ Response time: 1.2s")
        #     if st.session_state.voted is None:
        #         if st.button("👑 Vote LLaMA 3", key="vote_llama", use_container_width=True):
        #             st.session_state.voted = "LLaMA 3"
        #             st.rerun()
        #     elif st.session_state.voted == "LLaMA 3":
        #         st.success("✅ You voted for this!")

        # with col2:
        #     st.markdown("### 🌬️ Mistral")
        #     st.info(DUMMY_RESPONSES["mistral"])
        #     st.caption("⏱️ Response time: 0.9s")
        #     if st.session_state.voted is None:
        #         if st.button("👑 Vote Mistral", key="vote_mistral", use_container_width=True):
        #             st.session_state.voted = "Mistral"
        #             st.rerun()
        #     elif st.session_state.voted == "Mistral":
        #         st.success("✅ You voted for this!")

        # if st.session_state.voted:
        #     st.balloons()
        #     st.success(f"🏆 Winner: **{st.session_state.voted}**")