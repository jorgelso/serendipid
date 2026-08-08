"""Shared Streamlit UI pieces used across Home and every page/*.py file."""

import streamlit as st

from .api_client import ApiClient, ApiError
from .config import Settings, get_settings
from .data import resolve_thumbnail


@st.cache_resource
def get_client() -> ApiClient:
    return ApiClient(get_settings())


def require_settings_and_client() -> tuple[Settings, ApiClient]:
    try:
        settings = get_settings()
    except RuntimeError as e:
        st.error(str(e))
        st.stop()
    return settings, get_client()


def render_sidebar(settings: Settings) -> None:
    with st.sidebar:
        st.header("SuperBrain")
        st.caption(f"Backend: {settings.api_url}")
        if st.button("🔄 Refresh data"):
            st.cache_data.clear()
            st.rerun()


def _safe_index(options: list[str], value: str | None) -> int:
    try:
        return options.index(value)
    except (ValueError, TypeError):
        return 0


def render_post_card(
    post: dict,
    client: ApiClient,
    api_base_url: str,
    key_prefix: str,
    category_choices: list[str],
) -> None:
    """Renders one post: detail view, inline edit form, and a hide action.

    key_prefix must be unique per call site (e.g. f"browse_{shortcode}" vs
    f"search_{shortcode}") since the same shortcode can appear on more than
    one page in the same Streamlit session.
    """
    shortcode = post["shortcode"]
    label = post.get("title") or shortcode
    username = post.get("username", "")

    with st.expander(f"{label} — @{username}"):
        col1, col2 = st.columns([1, 2])
        with col1:
            thumb = resolve_thumbnail(post.get("thumbnail"), api_base_url)
            if thumb:
                st.image(thumb, width="stretch")
            st.caption(post.get("url", ""))
            if "similarity" in post:
                st.metric("Similarity", f"{post['similarity']:.3f}")
        with col2:
            st.write("**Summary:**", post.get("summary") or "_none_")
            st.write("**Tags:**", ", ".join(post.get("tags") or []))
            st.write("**Category:**", post.get("category") or "_none_")
            with st.expander("Full analysis fields"):
                st.write("**Visual analysis:**", post.get("visual_analysis") or "_none_")
                st.write(
                    "**Audio transcription:**", post.get("audio_transcription") or "_none_"
                )
                st.write("**Text analysis:**", post.get("text_analysis") or "_none_")
                st.write("**Music:**", post.get("music") or "_none_")
                st.write("**Post date:**", post.get("post_date") or "_unknown_")
                st.write("**Likes:**", post.get("likes"))

        st.divider()
        st.markdown("**Edit**")
        with st.form(key=f"{key_prefix}_edit_form"):
            options = sorted(set(category_choices) | {post.get("category") or ""})
            new_category = st.selectbox(
                "Category",
                options=options,
                index=_safe_index(options, post.get("category")),
                key=f"{key_prefix}_category",
            )
            new_title = st.text_input(
                "Title", value=post.get("title") or "", key=f"{key_prefix}_title"
            )
            new_summary = st.text_area(
                "Summary", value=post.get("summary") or "", key=f"{key_prefix}_summary"
            )
            if st.form_submit_button("Save changes"):
                updates = {
                    "category": new_category,
                    "title": new_title,
                    "summary": new_summary,
                }
                try:
                    result = client.update_post(shortcode, updates)
                    st.success(f"Updated: {', '.join(result.get('updated_fields', []))}")
                    st.cache_data.clear()
                except ApiError as e:
                    st.error(str(e))

        st.divider()
        st.markdown(
            "**Hide post** _(soft-delete — removes it from all views; "
            "cannot be undone from this dashboard once confirmed)_"
        )
        confirm = st.checkbox(
            "I understand this cannot be undone here", key=f"{key_prefix}_hide_confirm"
        )
        if st.button("Hide this post", key=f"{key_prefix}_hide_btn", disabled=not confirm):
            try:
                client.hide_post(shortcode)
                st.success("Post hidden.")
                st.cache_data.clear()
                st.rerun()
            except ApiError as e:
                st.error(str(e))
