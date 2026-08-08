"""Search saved posts by topic/meaning using the backend's semantic search."""

import streamlit as st

from lib.api_client import ApiError
from lib.components import render_post_card, render_sidebar, require_settings_and_client
from lib.data import category_options, load_export, posts_dataframe

st.set_page_config(page_title="Search — SuperBrain", page_icon="🧠", layout="wide")

settings, client = require_settings_and_client()
render_sidebar(settings)

try:
    export_payload = load_export(client)
except Exception as e:
    st.error(str(e))
    st.stop()

posts_df = posts_dataframe(export_payload)
categories = category_options(posts_df)

st.title("Search by topic")
st.caption(
    "Real semantic search — matches by meaning, not just keyword overlap "
    "(e.g. a query for \"personal growth, mindset, life advice\" can rank a "
    "relevant post first even if that post's own title/tags never use those words)."
)

query = st.text_input("What are you looking for?")
c1, c2 = st.columns(2)
with c1:
    max_results = st.slider("Max results", 1, 100, 20)
with c2:
    min_similarity = st.slider("Min similarity", 0.0, 1.0, 0.0, step=0.01)

if query.strip():
    try:
        results = client.search_semantic(query, limit=max_results, min_similarity=min_similarity)
    except ApiError as e:
        st.error(str(e))
        results = None

    if results is not None:
        hits = results.get("data", [])
        st.caption(f"{len(hits)} result(s)")
        posts_by_shortcode = (
            posts_df.set_index("shortcode").to_dict("index") if not posts_df.empty else {}
        )
        for hit in hits:
            shortcode = hit["shortcode"]
            full_post = dict(posts_by_shortcode.get(shortcode, {}))
            full_post.update(hit)
            full_post["shortcode"] = shortcode
            render_post_card(
                full_post,
                client,
                settings.api_url,
                key_prefix=f"search_{shortcode}",
                category_choices=categories,
            )
else:
    st.info("Enter a topic or phrase above to search.")
