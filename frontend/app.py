import streamlit as st
import requests
from urllib.parse import quote
import plotly.graph_objects as go

BASE_URL = "http://localhost:8000"

st.set_page_config(page_title="Serverless Platform", layout="wide")
st.markdown("<h1 style='text-align: center;'>☁️ Serverless Function Execution Platform</h1>", unsafe_allow_html=True)
st.markdown("<h4 style='text-align: center;'>Built with Docker, gVisor, and FastAPI</h4>", unsafe_allow_html=True)

st.markdown("""
<style>
    .metric-label > div {
        font-size: 18px !important;
    }
    .stButton>button {
        font-size: 16px;
        padding: 10px 24px;
        border-radius: 8px;
        background-color: #4CAF50;
        color: white;
    }
    .stTextInput>div>div>input {
        font-size: 16px;
    }
</style>
""", unsafe_allow_html=True)

with st.expander("👨‍💻 Project Contributors"):
    st.markdown("""
    - 🧑‍💻 **S Samartha :     : PES1UG22CS492**  
    - 👩‍💻 **Pushpavathi      : PES1UG22CS459**  
    - 👩‍💻 **Preeti Madabbhavi: PES1UG22CS449**  
    - 👩‍💻 **Thrisha M        : PES1UG23CS834**
    """)

# --- Deploy Function ---
st.header("🚀 Deploy a New Function")
with st.form("deploy_form"):
    st.subheader("💡 Function Configuration")
    col1, col2 = st.columns(2)
    with col1:
        name = st.text_input("📝 Function Name")
        route = st.text_input("🛣️ Route", "/your_route")
    with col2:
        language = st.selectbox("💻 Language", ["python"])
        timeout = st.slider("⏱️ Timeout (seconds)", 1, 30, 5)
    code = st.text_area("🧾 Code", "print('Hello from serverless')", height=200)
    submitted = st.form_submit_button("🚀 Deploy Function")

    if submitted:
        if name and route and language and code:
            params = {
                "name": name,
                "route": route,
                "language": language,
                "timeout": timeout,
                "code": code
            }
            try:
                response = requests.post(f"{BASE_URL}/functions/", params=params)
                if response.ok:
                    st.success("✅ Function deployed successfully!")
                    st.json(response.json())
                else:
                    st.error(f"❌ Deployment failed: {response.status_code}")
                    st.json(response.json())
            except Exception as e:
                st.error(f"🚨 Error: {e}")
        else:
            st.warning("⚠️ Please fill in all fields.")

from urllib.parse import quote  # for safe URL formatting

st.header("📜 Available Functions")

try:
    response = requests.get(f"{BASE_URL}/functions/")
    if response.ok:
        functions = response.json().get("data", [])
        if functions:
            for fn in functions:
                with st.expander(f"🔧 Manage Function: {fn}"):
                    col1, col2 = st.columns(2)

                    # 🔴 Delete Button
                    if col1.button(f"🗑️ Delete `{fn}`", key=f"delete_{fn}"):
                        delete_url = f"{BASE_URL}/functions/delete/{quote(fn)}"
                        res = requests.delete(delete_url)
                        if res.ok:
                            st.success(f"✅ `{fn}` deleted successfully!")
                            st.experimental_rerun()
                        else:
                            st.error(f"❌ Delete failed: {res.json().get('detail')}")

                    # 🟢 Update Form
                    with col2.form(f"update_form_{fn}"):
                        st.markdown("**Update Function Code**")
                        updated_code = st.text_area("Code", height=150, key=f"update_code_{fn}")
                        update_submit = st.form_submit_button("📤 Update")

                        if update_submit:
                            payload = {"code": updated_code}
                            update_url = f"{BASE_URL}/functions/update/{quote(fn)}"
                            res = requests.put(update_url, json=payload)
                            if res.ok:
                                st.success(f"✅ `{fn}` updated successfully!")
                            else:
                                st.error(f"❌ Update failed: {res.json().get('detail')}")
        else:
            st.info("ℹ️ No deployed functions yet.")
    else:
        st.error("❌ Failed to fetch functions list.")
except Exception as e:
    st.error(f"🚨 Error: {e}")



# --- Execute Function ---
st.header("⚙️ Execute a Function")
col_exec_1, col_exec_2 = st.columns([3, 1])
with col_exec_1:
    exec_name = st.text_input("🎯 Function Name to Execute")
with col_exec_2:
    runtime = st.selectbox("🧬 Runtime", ["runc", "runsc"])

if st.button("▶️ Run Function"):
    try:
        response = requests.post(f"{BASE_URL}/functions/execute", json={
            "name": exec_name,
            "runtime": runtime
        })
        if response.ok:
            res = response.json()
            st.success("✅ Execution completed successfully!")
            with st.expander("🖨️ Output"):
                st.code(res['output'], language="bash")
            col1, col2, col3 = st.columns(3)
            col1.metric("⏱️ Time", f"{res['execution_time_sec']} sec")
            col2.metric("🧠 CPU", f"{res['cpu_percent']}%")
            col3.metric("💾 Memory", f"{res['memory_mb']} MB")
        else:
            st.error(f"❌ Execution failed: {response.status_code}")
            st.json(response.json())
    except Exception as e:
        st.error(f"🚨 Error: {e}")

# --- Metrics Dashboard ---
st.header("📈 Aggregated Function Metrics")

metric_fn_name = st.text_input("🔍 Function Name for Metrics")

if st.button("📊 Get Metrics"):
    if not metric_fn_name:
        st.warning("⚠️ Please enter a function name.")
    else:
        try:
            response = requests.get(f"{BASE_URL}/metrics/{quote(metric_fn_name)}")
            if response.ok:
                data = response.json()
                metrics = data["metrics"]

                st.subheader(f"📊 Metrics for Function: `{metric_fn_name}`")

                # Metric Tiles
                mcol1, mcol2, mcol3 = st.columns(3)
                mcol1.metric("✅ Success", metrics["success_count"])
                mcol2.metric("❌ Failure", metrics["failure_count"])
                mcol3.metric("🔁 Total", metrics["success_count"] + metrics["failure_count"])

                mcol4, mcol5, mcol6 = st.columns(3)
                mcol4.metric("⏱ Avg Time (s)", round(metrics["avg_time"], 2))
                mcol5.metric("🧠 Avg CPU (%)", round(metrics["avg_cpu"], 2))
                mcol6.metric("💾 Avg Memory (MB)", round(metrics["avg_mem"], 2))

                # Pie Chart
                pie_fig = go.Figure(data=[
                    go.Pie(
                        labels=["Success", "Failure"],
                        values=[metrics["success_count"], metrics["failure_count"]],
                        hole=0.4,
                        marker=dict(colors=["#00cc96", "#EF553B"])
                    )
                ])
                pie_fig.update_layout(title="✅ Success vs ❌ Failure", height=400)

                # Bar Chart
                bar_fig = go.Figure(data=[
                    go.Bar(
                        name="Resource Usage",
                        x=["Avg Time (s)", "Avg CPU (%)", "Avg Memory (MB)"],
                        y=[metrics["avg_time"], metrics["avg_cpu"], metrics["avg_mem"]],
                        marker_color="#636EFA"
                    )
                ])
                bar_fig.update_layout(title="📉 Average Resource Usage", height=400)

                st.plotly_chart(pie_fig, use_container_width=True)
                st.plotly_chart(bar_fig, use_container_width=True)

            else:
                st.error(f"❌ Failed to fetch metrics: {response.status_code}")
                st.json(response.json())
        except Exception as e:
            st.error(f"🚨 Error fetching metrics: {e}")
