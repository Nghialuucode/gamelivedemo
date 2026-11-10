import queue
import asyncio
import tempfile
import streamlit as st
from streamlit_autorefresh import st_autorefresh
import edge_tts
from scraper import TikTokLiveScraper

st.set_page_config(page_title="TikTok Live Game Demo", page_icon="🎮", layout="wide")
st.title("🎮 TikTok Live: Đọc tên & Avatar")

# --- Khởi tạo Session State ---
if "data_queue" not in st.session_state:
    st.session_state.data_queue = queue.Queue()
if "scraper" not in st.session_state:
    st.session_state.scraper = None
if "events_log" not in st.session_state:
    st.session_state.events_log = []
if "latest_gifter" not in st.session_state:
    st.session_state.latest_gifter = None  # Lưu {user, avatar_bytes, gift_name}
if "audio_bytes" not in st.session_state:
    st.session_state.audio_bytes = None
if "last_audio_text" not in st.session_state:
    st.session_state.last_audio_text = ""

# --- Hàm tạo giọng nói bằng edge-tts ---
async def _generate_tts(text: str) -> bytes:
    """Tạo file âm thanh từ văn bản, trả về dữ liệu bytes."""
    # Sử dụng giọng Nam Minh (nam) hoặc Hoài My (nữ). Ở đây chọn Nam Minh.
    voice = "vi-VN-NamMinhNeural"
    communicate = edge_tts.Communicate(text, voice)
    # Ghi ra file tạm và đọc lại dưới dạng bytes
    with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as tmp:
        tmp_path = tmp.name
    await communicate.save(tmp_path)
    with open(tmp_path, "rb") as f:
        audio_bytes = f.read()
    import os
    os.unlink(tmp_path) # Xóa file tạm
    return audio_bytes

def generate_tts_sync(text: str) -> bytes:
    """Wrapper đồng bộ để gọi hàm async trong Streamlit."""
    return asyncio.run(_generate_tts(text))

# --- Sidebar ---
with st.sidebar:
    st.header("⚙️ Điều khiển")
    tiktok_username = st.text_input("Username TikTok", value="@tv_asahi_news")
    
    col1, col2 = st.columns(2)
    with col1:
        if st.button("▶️ Bắt đầu", use_container_width=True):
            is_running = (
                st.session_state.scraper is not None 
                and st.session_state.scraper._thread is not None 
                and st.session_state.scraper._thread.is_alive()
            )
            if tiktok_username and not is_running:
                st.session_state.events_log = []
                st.session_state.latest_gifter = None
                new_scraper = TikTokLiveScraper(tiktok_username, st.session_state.data_queue)
                new_scraper.start()
                st.session_state.scraper = new_scraper
                st.rerun()
    with col2:
        if st.button("⏹️ Dừng", use_container_width=True):
            if st.session_state.scraper:
                st.session_state.scraper.stop()
                st.session_state.scraper = None
                st.rerun()
    
    st.divider()
    st.caption("🔊 **Quan trọng:** Hãy nhấp vào nút bên dưới một lần để 'mở khóa' âm thanh cho trình duyệt.")
    if st.button("🔈 Kích hoạt Âm thanh", use_container_width=True):
        st.session_state.audio_unlocked = True
        st.success("Âm thanh đã được kích hoạt!")

# --- Tự động làm mới ---
st_autorefresh(interval=1500, key="refresh")

# --- Xử lý dữ liệu từ Queue ---
def drain_queue():
    q = st.session_state.data_queue
    while not q.empty():
        try:
            ev = q.get_nowait()
            st.session_state.events_log.append(ev)
            if len(st.session_state.events_log) > 100:
                st.session_state.events_log = st.session_state.events_log[-100:]

            # Nếu là quà tặng: cập nhật "bản chiếu" và tạo giọng đọc
            if ev.get("type") == "gift":
                st.session_state.latest_gifter = {
                    "user": ev.get("user", "Ai đó"),
                    "avatar_bytes": ev.get("avatar_bytes"),
                    "gift_name": ev.get("gift_name", "quà"),
                    "count": ev.get("count", 1)
                }
                # Tạo giọng đọc (chỉ tạo một lần cho mỗi sự kiện quà)
                text_to_say = f"Cảm ơn {ev.get('user', 'bạn')} đã tặng {ev.get('count', 1)} {ev.get('gift_name', 'món quà')}!"
                if text_to_say != st.session_state.last_audio_text:
                    try:
                        st.session_state.audio_bytes = generate_tts_sync(text_to_say)
                        st.session_state.last_audio_text = text_to_say
                    except Exception as e:
                        st.error(f"Lỗi tạo giọng nói: {e}")

        except queue.Empty:
            break

drain_queue()

# --- Giao diện chính ---
col_stage, col_log = st.columns([2, 1])

with col_stage:
    st.subheader("📺 Bản chiếu (Stage)")
    gifter = st.session_state.latest_gifter
    
    # Khung hiển thị Avatar
    avatar_placeholder = st.empty()
    if gifter and gifter.get("avatar_bytes"):
        avatar_placeholder.image(gifter["avatar_bytes"], width=200)
    else:
        avatar_placeholder.info("Avatar người tặng quà sẽ xuất hiện ở đây.")
    
    # Hiển thị tên và quà
    if gifter:
        st.success(f"🎁 **{gifter['user']}** vừa tặng **{gifter['gift_name']}** (x{gifter['count']})!")
    
    # Phát âm thanh (nếu có và đã được kích hoạt)
    if st.session_state.get("audio_bytes"):
        # Sử dụng autoplay=True. Lưu ý: có thể bị chặn nếu chưa tương tác.
        st.audio(st.session_state.audio_bytes, format="audio/mp3", autoplay=True)

with col_log:
    st.subheader("📨 Sự kiện gần đây")
    for ev in reversed(st.session_state.events_log[-20:]):
        if ev.get("type") == "gift":
            st.write(f"🎁 **{ev.get('user')}** tặng **{ev.get('gift_name')}**")
        elif ev.get("type") == "comment":
            st.write(f"💬 **{ev.get('user')}**: {ev.get('text')}")
        elif ev.get("type") == "system":
            st.caption(f"ℹ️ {ev.get('message')}")
