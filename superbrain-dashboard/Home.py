"""SuperBrain Dashboard — overview page (Streamlit multi-page entrypoint)."""

import streamlit as st

from lib.components import render_sidebar, require_settings_and_client
from lib.data import (
    collections_dataframe,
    compute_category_counts,
    compute_collection_counts,
    load_export,
    posts_dataframe,
)

st.set_page_config(page_title="SuperBrain Dashboard", page_icon="🧠", layout="wide")

settings, client = require_settings_and_client()
render_sidebar(settings)

try:
    export_payload = load_export(client)
except Exception as e:
    st.error(str(e))
    st.stop()

posts_df = posts_dataframe(export_payload)
collections_df = collections_dataframe(export_payload)

st.title("SuperBrain — Overview")

if posts_df.empty:
    st.info("No analyzed posts found yet.")
    st.stop()

c1, c2, c3 = st.columns(3)
c1.metric("Total posts", len(posts_df))
c2.metric("Categories", posts_df["category"].nunique())
c3.metric("Collections", len(collections_df))

st.subheader("Posts by category")
st.bar_chart(compute_category_counts(posts_df))

st.subheader("Posts by collection")
collection_counts = compute_collection_counts(collections_df)
if not collection_counts.empty:
    st.bar_chart(collection_counts)
else:
    st.caption("No collections yet.")
