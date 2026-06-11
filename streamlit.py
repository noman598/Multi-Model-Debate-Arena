import streamlit as st
import time

st.set_page_config(page_title="Multi-Model Debate Arena", layout="wide")

st.title("🏟️ Multi-Model Debate Arena")
st.markdown("Ask a question and see how 3 different models respond. Vote for the best answer!")

DUMMY_RESPONSES = {
    "llama3": "This is a sample response from LLaMA 3. It would contain the model's perspective on the question asked by the user with detailed reasoning and examples.",
    "mistral": "Mistral's response would appear here. This model tends to be concise and accurate, providing well-structured answers with clear points.",
    "gemma": "Gemma would respond here with its unique perspective. Google's model often provides balanced viewpoints with good factual grounding."
}

# --- Session state init ---
if "responses_ready" not in st.session_state:
    st.session_state.responses_ready = False
if "voted" not in st.session_state:
    st.session_state.voted = None

question = st.text_area("💬 Enter your question:", placeholder="e.g. Is Python better than JavaScript?", height=100)
category = st.selectbox("📂 Category:", ["Technology", "Science", "Philosophy", "Creative", "General"])

if st.button("⚔️ Start Debate", use_container_width=True):
    if not question.strip():
        st.warning("Please enter a question first.")
    else:
        with st.spinner("Models are thinking..."):
            time.sleep(2)
        st.session_state.voted = None  # reset vote on new debate
    st.session_state.responses_ready = True

# --- Show responses only if ready ---
if st.session_state.responses_ready:
    st.divider()
    st.subheader("🤖 Model Responses")

    col1, col2, col3 = st.columns(3)

    with col1:
        st.markdown("### 🦙 LLaMA 3")
        st.info(DUMMY_RESPONSES["llama3"])
        st.caption("⏱️ Response time: 1.2s")
        if st.session_state.voted is None:
            if st.button("👑 Vote LLaMA 3", key="vote_llama", use_container_width=True):
                st.session_state.voted = "LLaMA 3"
                st.rerun()
        elif st.session_state.voted == "LLaMA 3":
            st.success("✅ You voted for this!")

    with col2:
        st.markdown("### 🌬️ Mistral")
        st.info(DUMMY_RESPONSES["mistral"])
        st.caption("⏱️ Response time: 0.9s")
        if st.session_state.voted is None:
            if st.button("👑 Vote Mistral", key="vote_mistral", use_container_width=True):
                st.session_state.voted = "Mistral"
                st.rerun()
        elif st.session_state.voted == "Mistral":
            st.success("✅ You voted for this!")

    with col3:
        st.markdown("### 💎 Gemma")
        st.info(DUMMY_RESPONSES["gemma"])
        st.caption("⏱️ Response time: 1.5s")
        if st.session_state.voted is None:
            if st.button("👑 Vote Gemma", key="vote_gemma", use_container_width=True):
                st.session_state.voted = "Gemma"
                st.rerun()
        elif st.session_state.voted == "Gemma":
            st.success("✅ You voted for this!")

    if st.session_state.voted:
        st.balloons()
        st.success(f"🏆 Winner: **{st.session_state.voted}**")