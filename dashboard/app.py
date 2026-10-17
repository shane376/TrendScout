"""Launch from the repository: python -m streamlit run dashboard/app.py."""

from pathlib import Path

import pandas as pd
import streamlit as st

from trendscout.config import Settings
from trendscout.dashboard.data import discover_runs, load_run


st.set_page_config(page_title="TrendScout Local Intelligence", layout="wide")
st.title("TrendScout · Local Intelligence")
st.caption("Opportunity scores are research heuristics on a 0–100 scale, not predictions of virality. Scores from different candidate sets are not directly comparable.")
root = Path(st.sidebar.text_input("Output directory", str(Settings.from_env().output_dir), key="output-root"))
st.sidebar.button("Refresh exports")
try:
    runs = discover_runs(root)
except OSError as error:
    st.error(f"Cannot read output directory: {error}")
    st.stop()
if not runs:
    st.info("No timestamped runs found. Generate an offline demo, then refresh. Custom outputs can be selected in the sidebar.")
    st.code('python -m trendscout run --niche "AI tools" --limit 5 --demo')
    st.stop()
folder = st.sidebar.selectbox("Run (UTC, newest first)", runs, format_func=lambda path: path.name)
st.caption(str(folder.resolve()))
run = load_run(folder)
st.info(run.provenance)
for issue in run.issues:
    st.warning(issue)
if run.issues:
    st.caption("Counts and charts include only validated records. Data and evaluation issues are listed above.")
st.caption("Exported source platforms: " + (", ".join(sorted({p.post.platform for p in run.posts} | {i.source_platform for i in run.ideas})) or "Unknown"))
overview, trends, ideas = st.tabs(["Overview", "Ranked trends", "Content ideas"])
rows = [{**item.post.model_dump(mode="json"), **item.model_dump(exclude={"post"})} for item in run.posts]
frame = pd.DataFrame(rows)
with overview:
    columns = st.columns(4)
    columns[0].metric("Ranked candidates", len(rows) if run.posts_available else "Unavailable")
    columns[1].metric("Content ideas", len(run.ideas) if run.ideas_available else "Unavailable")
    columns[2].metric("Average opportunity / 100", f"{frame.opportunity_score.mean():.2f}" if rows else "Unavailable")
    columns[3].metric("Editorial warnings", len(run.quality_warnings) if run.quality_warnings is not None else "Unavailable")
    st.caption(run.quality_status)
    if rows:
        st.subheader("Opportunity score distribution")
        bins = pd.cut(frame.opportunity_score, bins=list(range(0, 101, 10)), include_lowest=True)
        distribution = bins.value_counts(sort=False)
        distribution.index = distribution.index.astype(str)
        st.bar_chart(distribution.rename("Candidates"))
        st.subheader("Top ranked candidates")
        top = frame.sort_values("rank").head(20).copy()
        top["Candidate"] = top["rank"].astype(str) + " · " + top["title"]
        st.bar_chart(top.set_index("Candidate")[["opportunity_score", "engagement_score", "recency_score", "discussion_score"]], stack=False)
    else:
        st.info("No valid ranked candidates available for charts.")
with trends:
    if rows:
        query = st.text_input("Search title, body, or community", key="candidate-query")
        platforms = st.multiselect("Source platforms", sorted(frame.platform.unique()), default=sorted(frame.platform.unique()))
        minimum = st.slider("Minimum opportunity score", 0, 100, 0)
        visible = frame[frame.platform.isin(platforms) & (frame.opportunity_score >= minimum)]
        if query and not visible.empty:
            visible = visible[visible[["title", "body", "community"]].fillna("").agg(" ".join, axis=1).str.contains(query, case=False, regex=False)]
        st.caption(f"{len(visible)} matching candidates. Click column headers to sort.")
        st.dataframe(visible, hide_index=True, column_config={"url": st.column_config.LinkColumn("Original source")})
        if not visible.empty:
            identity = st.selectbox("Inspect candidate", visible.index, format_func=lambda idx: f"#{frame.loc[idx, 'rank']} · {frame.loc[idx, 'title']}", key="candidate-inspect")
            selected = frame.loc[identity]
            st.text(selected["title"])
            st.text(selected["body"] or "No body exported.")
            st.link_button("Original source", selected["url"])
            st.json(selected.to_dict())
    else:
        st.info("No valid ranked candidates. Check the selected run's CSV and warnings above.")
with ideas:
    st.caption(run.quality_status)
    if not run.ideas:
        st.info("No valid ideas. Check the selected run's JSON and warnings above.")
    for number, idea in zip(run.idea_numbers, run.ideas):
        with st.expander(f"{number}. {idea.title}"):
            st.caption(f"Opportunity {idea.opportunity_score:.2f}/100 · {idea.mode} · {idea.generation_method}")
            for label, value in [("Niche", idea.target_niche), ("Angle", idea.content_angle), ("Hook", idea.hook), ("Script", idea.script)]:
                st.subheader(label)
                st.text(value)
            st.subheader("Visual plan")
            for visual in idea.suggested_visuals:
                st.text(visual)
            st.subheader("Call to action")
            st.text(idea.call_to_action)
            st.subheader("Source attribution")
            st.text(f"{idea.source_platform} / {idea.source_id}: {idea.source_title}")
            st.link_button("Open source", str(idea.source_url), key=f"source-{number}")
            st.text(f"Fact-check required: {idea.requires_fact_check}")
            st.text(idea.fact_check_note)
            for warning in run.quality_warnings or []:
                if number in warning.idea_numbers:
                    st.warning(f"{warning.code} · ideas {warning.idea_numbers}: {warning.message}")
