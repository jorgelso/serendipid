"""Aggregate insights: category/collection/tag breakdowns and a semantic
instructional-vs-life-advice split."""

from collections import Counter

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from lib.api_client import ApiError
from lib.components import render_sidebar, require_settings_and_client
from lib.data import (
    collections_dataframe,
    compute_category_counts,
    compute_collection_counts,
    load_export,
    posts_dataframe,
)

st.set_page_config(page_title="Insights — SuperBrain", page_icon="🧠", layout="wide")

settings, client = require_settings_and_client()
render_sidebar(settings)

try:
    export_payload = load_export(client)
except Exception as e:
    st.error(str(e))
    st.stop()

posts_df = posts_dataframe(export_payload)
collections_df = collections_dataframe(export_payload)

st.title("Insights")

if posts_df.empty:
    st.info("No analyzed posts found yet.")
    st.stop()

# Muted ink and a fixed categorical hue order, borrowed from the dataviz
# skill's validated default palette — kept as plain hex since this is a
# handful of single-series bar charts, not a themed component system.
MUTED_INK = "#898781"
HUE_BLUE = "#2a78d6"
HUE_ORANGE = "#eb6834"
HUE_AQUA = "#1baf7a"


def _bar_chart(series: pd.Series, color: str, x_title: str, y_title: str = "Posts") -> go.Figure:
    fig = go.Figure(
        go.Bar(x=series.index.tolist(), y=series.values.tolist(), marker_color=color)
    )
    fig.update_layout(
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font_color=MUTED_INK,
        xaxis_title=x_title,
        yaxis_title=y_title,
        margin=dict(l=10, r=10, t=10, b=10),
    )
    fig.update_xaxes(gridcolor="rgba(137,135,129,0.2)")
    fig.update_yaxes(gridcolor="rgba(137,135,129,0.2)")
    return fig


col1, col2 = st.columns(2)
with col1:
    st.subheader("Posts by category")
    st.plotly_chart(
        _bar_chart(compute_category_counts(posts_df), HUE_BLUE, "Category"),
        width="stretch",
    )
with col2:
    st.subheader("Posts by collection")
    collection_counts = compute_collection_counts(collections_df)
    if not collection_counts.empty:
        st.plotly_chart(
            _bar_chart(collection_counts, HUE_AQUA, "Collection"), width="stretch"
        )
    else:
        st.caption("No collections yet.")

st.subheader("Most common tags")
all_tags = [t for tags in posts_df.get("tags", []) for t in (tags or [])]
if all_tags:
    top_tags = pd.Series(dict(Counter(all_tags).most_common(20)))
    st.plotly_chart(_bar_chart(top_tags, HUE_ORANGE, "Tag"), width="stretch")
else:
    st.caption("No tags recorded yet.")

st.divider()
st.subheader("Instructional vs. self-improvement content")
st.caption(
    "Classifies each post by comparing its semantic similarity to two reference "
    "phrases via the backend's real semantic search — not keyword matching. "
    "Each axis only considers its top-100 most similar posts (the API's per-call "
    "limit), so coverage is best-effort on very large libraries."
)

INSTRUCTIONAL_QUERY = "step-by-step tutorial, recipe, DIY guide, how-to instructions"
SELF_IMPROVEMENT_QUERY = "personal growth, mindset, life advice, productivity habits"

threshold = st.slider(
    "Classification confidence threshold",
    0.0,
    1.0,
    0.15,
    step=0.01,
    help=(
        "Minimum similarity a post must reach on either axis to be classified "
        "at all; tune this once you see real results — no default is authoritative."
    ),
)

try:
    instr_hits = {
        h["shortcode"]: h["similarity"]
        for h in client.search_semantic(INSTRUCTIONAL_QUERY, limit=100)["data"]
    }
    advice_hits = {
        h["shortcode"]: h["similarity"]
        for h in client.search_semantic(SELF_IMPROVEMENT_QUERY, limit=100)["data"]
    }
except ApiError as e:
    st.error(str(e))
    instr_hits, advice_hits = {}, {}

if instr_hits or advice_hits:

    def classify(shortcode: str) -> str:
        i, a = instr_hits.get(shortcode, 0.0), advice_hits.get(shortcode, 0.0)
        if max(i, a) < threshold:
            return "Unclassified"
        return "Instructional" if i > a else "Self-improvement / life advice"

    life_category = posts_df["shortcode"].apply(classify)
    counts = life_category.value_counts()
    colors = {
        "Instructional": HUE_BLUE,
        "Self-improvement / life advice": HUE_ORANGE,
        "Unclassified": MUTED_INK,
    }
    ordered_labels = [
        c for c in ["Instructional", "Self-improvement / life advice", "Unclassified"] if c in counts.index
    ]
    fig = go.Figure(
        go.Bar(
            x=ordered_labels,
            y=[counts[c] for c in ordered_labels],
            marker_color=[colors[c] for c in ordered_labels],
        )
    )
    fig.update_layout(
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font_color=MUTED_INK,
        yaxis_title="Posts",
        margin=dict(l=10, r=10, t=10, b=10),
    )
    st.plotly_chart(fig, width="stretch")
else:
    st.caption("No results from semantic search yet.")
