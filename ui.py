"""Streamlit 界面 - 小说转漫剧"""
import streamlit as st
import httpx
import json
import time

API_BASE = "http://localhost:8000"

st.set_page_config(
    page_title="小说转漫剧",
    page_icon="🎬",
    layout="wide",
)

st.title("🎬 小说转漫剧 AI 平台")
st.markdown("上传小说文本，AI 自动生成漫剧短视频")


# ============ 工具函数 ============

def api_get(path: str):
    try:
        resp = httpx.get(f"{API_BASE}{path}", timeout=10)
        return resp.json()
    except Exception as e:
        st.error(f"API 请求失败: {e}")
        return None


def api_post(path: str, data: dict = None):
    try:
        resp = httpx.post(f"{API_BASE}{path}", json=data, timeout=30)
        return resp.json()
    except Exception as e:
        st.error(f"API 请求失败: {e}")
        return None


def poll_status(project_id: str, placeholder):
    """轮询项目状态"""
    while True:
        result = api_get(f"/api/projects/{project_id}")
        if not result:
            break
        status = result.get("status", "unknown")
        error = result.get("error_message", "")

        status_text = {
            "created": "⏳ 已创建",
            "script_generating": "📝 正在生成剧本...",
            "script_done": "✅ 剧本完成",
            "characters_generating": "🎨 正在生成角色三视图...",
            "characters_done": "✅ 角色完成",
            "shots_generating": "🖼️ 正在生成分镜画面...",
            "shots_done": "✅ 画面完成",
            "audio_generating": "🎤 正在合成语音...",
            "audio_done": "✅ 语音完成",
            "video_generating": "🎬 正在生成AI视频...",
            "video_done": "✅ 视频完成",
            "composing": "🎞️ 正在合成最终视频...",
            "done": "🎉 全部完成！",
            "error": f"❌ 出错: {error}",
        }.get(status, f"状态: {status}")

        placeholder.info(status_text)

        if status in ["done", "error"]:
            return result
        time.sleep(3)


# ============ 侧边栏：项目列表 ============

with st.sidebar:
    st.header("📁 项目列表")
    projects = api_get("/api/projects") or []
    for p in projects:
        status_icon = "✅" if p["status"] == "done" else "🔄" if "generating" in p["status"] else "📝"
        st.markdown(f"- {status_icon} **{p['name']}** (`{p['id']}`)")

    st.divider()
    if st.button("🔄 刷新列表"):
        st.rerun()


# ============ 主区域 ============

tab1, tab2, tab3 = st.tabs(["📝 新建项目", "▶️ 执行生成", "📊 项目详情"])

# --- Tab 1: 新建项目 ---
with tab1:
    st.header("创建新项目")
    project_name = st.text_input("项目名称", placeholder="例如：斗破苍穹第一集")
    novel_text = st.text_area(
        "粘贴小说文本",
        height=400,
        placeholder="将小说文本粘贴到这里...\n\n建议3000字以内，太长会截断。",
    )

    if st.button("🚀 创建项目", type="primary", disabled=not (project_name and novel_text)):
        result = api_post("/api/projects", {
            "name": project_name,
            "novel_text": novel_text,
        })
        if result:
            st.success(f"项目创建成功！ID: {result['project_id']}")
            st.session_state["current_project"] = result["project_id"]
            st.rerun()


# --- Tab 2: 执行生成 ---
with tab2:
    st.header("执行生成流程")

    # 选择项目
    project_id = st.text_input(
        "项目 ID",
        value=st.session_state.get("current_project", ""),
        placeholder="输入项目ID",
    )

    if project_id:
        col1, col2 = st.columns(2)

        with col1:
            st.subheader("一键生成")
            st.markdown("点击后自动执行全流程：剧本 → 角色 → 画面 → 语音 → 合成")
            if st.button("🎬 一键生成全流程", type="primary", use_container_width=True):
                result = api_post(f"/api/projects/{project_id}/generate-all")
                if result:
                    st.info(result.get("message", ""))
                    status_placeholder = st.empty()
                    final = poll_status(project_id, status_placeholder)
                    if final and final.get("status") == "done":
                        st.balloons()
                        st.success("生成完成！请到「项目详情」标签查看结果")

        with col2:
            st.subheader("分步执行（调试用）")
            if st.button("1️⃣ 生成剧本", use_container_width=True):
                api_post(f"/api/projects/{project_id}/generate-script")
                st.info("剧本生成已启动")
            if st.button("2️⃣ 生成角色三视图", use_container_width=True):
                api_post(f"/api/projects/{project_id}/generate-characters")
                st.info("角色生成已启动")
            if st.button("3️⃣ 生成分镜画面", use_container_width=True):
                api_post(f"/api/projects/{project_id}/generate-shots")
                st.info("画面生成已启动")
            if st.button("4️⃣ 生成语音", use_container_width=True):
                api_post(f"/api/projects/{project_id}/generate-audio")
                st.info("语音生成已启动")
            if st.button("5️⃣ 生成AI视频", use_container_width=True):
                api_post(f"/api/projects/{project_id}/generate-videos")
                st.info("视频生成已启动")
            if st.button("6️⃣ 合成最终视频", use_container_width=True):
                api_post(f"/api/projects/{project_id}/compose")
                st.info("视频合成已启动")

        # 状态轮询
        if st.button("🔄 刷新状态"):
            result = api_get(f"/api/projects/{project_id}")
            if result:
                status = result.get("status", "unknown")
                st.json({"status": status, "error": result.get("error_message", "")})


# --- Tab 3: 项目详情 ---
with tab3:
    project_id = st.text_input("项目 ID", key="detail_project_id", value=st.session_state.get("current_project", ""))

    if project_id and st.button("📂 加载项目"):
        result = api_get(f"/api/projects/{project_id}")
        if result:
            st.session_state["project_data"] = result

    if "project_data" in st.session_state:
        data = st.session_state["project_data"]

        # 基本信息
        st.subheader(f"📋 {data['name']}")
        status_map = {
            "created": "⏳ 已创建",
            "done": "✅ 已完成",
            "error": "❌ 出错",
        }
        st.write(f"**状态**: {status_map.get(data['status'], data['status'])}")

        # 剧本
        if data.get("script"):
            with st.expander("📝 剧本", expanded=False):
                script = data["script"]
                st.write(f"**标题**: {script.get('title', '')}")

                st.write("**角色:**")
                for char in script.get("characters", []):
                    st.markdown(f"- **{char['name']}**: {char['description']} ({char.get('personality', '')})")

                st.write("**场景:**")
                for scene in script.get("scenes", []):
                    st.markdown(f"**场景 {scene['scene_number']}**: {scene['location']} - {scene.get('mood', '')}")
                    for shot in scene.get("shots", []):
                        dialogue_text = ""
                        if shot.get("dialogue"):
                            d = shot["dialogue"]
                            dialogue_text = f" | 💬 {d['character']}: {d['line']} ({d.get('emotion', '')})"
                        st.markdown(f"  - 🎥 镜头{shot['shot_number']} [{shot['shot_type']}] {shot['description']}{dialogue_text}")

        # 角色
        if data.get("characters"):
            with st.expander("🎨 角色三视图", expanded=False):
                for char in data["characters"]:
                    st.write(f"**{char['character_name']}**: {char['description']}")
                    cols = st.columns(3)
                    for col, (label, key) in zip(cols, [("正面", "front_image"), ("侧面", "side_image"), ("背面", "back_image")]):
                        with col:
                            path = char.get(key, "")
                            if path:
                                try:
                                    st.image(path, caption=f"{char['character_name']} - {label}")
                                except Exception:
                                    st.write(f"({label}: {path})")

        # 最终结果
        if data.get("status") == "done":
            st.subheader("🎬 最终视频")
            video_result = api_get(f"/api/projects/{project_id}/result")
            if video_result and video_result.get("video_path"):
                video_path = video_result["video_path"]
                st.write(f"视频路径: `{video_path}`")
                try:
                    st.video(video_path)
                except Exception:
                    st.info("请到服务器查看视频文件")
