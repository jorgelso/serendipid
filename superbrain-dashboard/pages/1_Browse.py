"""Browse all analyzed posts, filterable by category, collection, and tag."""

import streamlit as st

from lib.components import render_post_card, render_sidebar, require_settings_and_client
from lib.data import (
    category_options,
    collections_dataframe,
    filter_by_tags,
    load_export,
    posts_dataframe,
    posts_in_collection,
)

st.set_page_config(page_title="Browse — SuperBrain", page_icon="🧠", layout="wide")

settings, client = require_settings_and_client()
render_sidebar(settings)

try:
    export_payload = load_export(client)
except Exception as e:
    st.error(str(e))
    st.stop()

posts_df = posts_dataframe(export_payload)
collections_df = collections_dataframe(export_payload)

st.title("Browse")

if posts_df.empty:
    st.info("No analyzed posts found yet.")
    st.stop()

categories = category_options(posts_df)
collection_names = ["All"] + (
    collections_df["name"].tolist() if not collections_df.empty else []
)

col1, col2, col3 = st.columns([2, 1, 1])
with col1:
    tag_filter = st.text_input("Filter by tag (comma-separated)")
with col2:
    selected_categories = st.multiselect("Category", options=categories)
with col3:
    selected_collection = st.selectbox("Collection", options=collection_names)

filtered = posts_df
if selected_categories:
    filtered = filtered[filtered["category"].isin(selected_categories)]
if selected_collection != "All" and not collections_df.empty:
    collection_row = collections_df[collections_df["name"] == selected_collection].iloc[0]
    filtered = posts_in_collection(filtered, collection_row.to_dict())
if tag_filter.strip():
    filtered = filter_by_tags(filtered, tag_filter.split(","))

st.caption(f"{len(filtered)} of {len(posts_df)} posts match")

summary_cols = [
    c
    for c in ["shortcode", "username", "title", "category", "likes", "post_date"]
    if c in filtered.columns
]
st.dataframe(filtered[summary_cols], width="stretch", hide_index=True)

MAX_RENDERED = 50
st.subheader(f"Details (showing up to {MAX_RENDERED})")
if len(filtered) > MAX_RENDERED:
    st.caption(
        f"{len(filtered)} posts match — narrow the filters above to see more detail cards."
    )

for _, post in filtered.head(MAX_RENDERED).iterrows():
    render_post_card(
        post.to_dict(),
        client,
        settings.api_url,
        key_prefix=f"browse_{post['shortcode']}",
        category_choices=categories,
    )
