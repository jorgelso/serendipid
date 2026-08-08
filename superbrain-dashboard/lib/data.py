"""Data loading, caching, and derived views over the /export payload."""

import pandas as pd
import streamlit as st

from .api_client import ApiClient

# Never rendered in the UI — dropped as soon as the export payload becomes a
# DataFrame so it can't accidentally end up in a table or detail view.
POSTS_DISPLAY_DROP_COLS = ["embedding"]


@st.cache_data(show_spinner="Loading posts from SuperBrain backend...")
def load_export(_client: ApiClient) -> dict:
    """One bulk call, cached for the session. The leading underscore on
    _client tells st.cache_data not to try to hash the (unhashable) client
    object. Cleared by the sidebar's "Refresh data" button."""
    return _client.export(limit=50000, offset=0)


def posts_dataframe(export_payload: dict) -> pd.DataFrame:
    df = pd.DataFrame(export_payload.get("posts", []))
    if df.empty:
        return df
    df = df.drop(columns=[c for c in POSTS_DISPLAY_DROP_COLS if c in df.columns])
    if "is_hidden" in df.columns:
        df["is_hidden"] = df["is_hidden"].fillna(0).astype(int)
    if "tags" in df.columns:
        df["tags"] = df["tags"].apply(lambda v: v if isinstance(v, list) else [])
    if "source_hashtags" in df.columns:
        df["source_hashtags"] = df["source_hashtags"].apply(
            lambda v: v if isinstance(v, list) else []
        )
    return df


def collections_dataframe(export_payload: dict) -> pd.DataFrame:
    return pd.DataFrame(export_payload.get("collections", []))


def posts_in_collection(posts_df: pd.DataFrame, collection_row: dict) -> pd.DataFrame:
    post_ids = set(collection_row.get("post_ids", []))
    return posts_df[posts_df["shortcode"].isin(post_ids)]


def category_options(posts_df: pd.DataFrame) -> list[str]:
    """Derived from live data, not a hardcoded vocabulary — the category
    docstring in the backend's api.py is known to be stale."""
    if posts_df.empty or "category" not in posts_df.columns:
        return []
    return sorted(posts_df["category"].dropna().unique().tolist())


def filter_by_tags(posts_df: pd.DataFrame, tags: list[str]) -> pd.DataFrame:
    tags_lower = [t.strip().lower() for t in tags if t.strip()]
    if not tags_lower or posts_df.empty:
        return posts_df

    def matches(row_tags):
        row_tags_lower = [str(t).lower() for t in row_tags]
        return any(t in rt for t in tags_lower for rt in row_tags_lower)

    return posts_df[posts_df["tags"].apply(matches)]


def resolve_thumbnail(url_or_path: str | None, api_base_url: str) -> str | None:
    if not url_or_path:
        return None
    if url_or_path.startswith(("http://", "https://", "data:image/")):
        return url_or_path
    if url_or_path.startswith("/static/"):
        return f"{api_base_url}{url_or_path}"
    return None


def compute_category_counts(posts_df: pd.DataFrame) -> pd.Series:
    if posts_df.empty or "category" not in posts_df.columns:
        return pd.Series(dtype=int)
    return posts_df["category"].fillna("uncategorized").value_counts()


def compute_collection_counts(collections_df: pd.DataFrame) -> pd.Series:
    if collections_df.empty:
        return pd.Series(dtype=int)
    counts = {
        row["name"]: len(row.get("post_ids", [])) for _, row in collections_df.iterrows()
    }
    return pd.Series(counts)
