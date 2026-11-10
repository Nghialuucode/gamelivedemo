import queue
import asyncio
import tempfile
import os
import streamlit as st
from streamlit_autorefresh import st_autorefresh
import edge_tts
from scraper import TikTokLiveScraper

# --- Cấu hình trang ---
st.set_page_config(page_title="TikTok Live Game Demo", page_icon="🎮", layout="wide")
st.title("🎮 TikTok Live: Đọc tên & Bản chiếu Avatar")
st.caption("Demo: Scraper Thread + Queue + Edge TTS + Avatar Stage")


# --- Hàm tạo giọng nói bằng edge-tts ---
async def _generate_tts(text: str, voice: str = "vi-VN-NamMinhNeural") -> bytes:
    """Tạo file âm thanh từ văn bản, trả về dữ liệu bytes."""
    communicate = edge_tts.Communicate(text, voice)
    with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as tmp:
        tmp_path = tmp.name
    try:
        await communicate.save(tmp_path)
        with open(tmp_path, "rb") as f:
            audio_bytes = f.read()
    finally:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)
    return audio_bytes


def generate_tts_sync(text: str, voice: str = "vi-VN-NamMinhNeural") -> bytes:
    """Wrapper đồng bộ để gọi hàm async trong Streamlit."""
    return asyncio.run(_generate_tts(text, voice))


# --- Dialog phóng to avatar ---
@st.dialog("Ảnh đại diện người tặng quà", width="large")
def show_avatar_dialog(image_bytes):
    """Hiển thị ảnh avatar trong một cửa sổ modal lớn."""
    if image_bytes:
        st.image(image_bytes, use_container_width=True)
    else:
        st.warning("Không có dữ liệu ảnh để hiển thị.")


# --- Khởi tạo Session State ---
if "data_queue" not in st.session_state:
    st.session_state.data_queue = queue.Queue()
if "scraper" not in st.session_state:
    st.session_state.scraper = None
if "events_log" not in st.session_state:
    st.session_state.events_log = []
if "latest_gifter" not in st.session_state:
    st.session_state.latest_gifter = None  # {user, avatar_bytes, gift_name, count, avatar_error}
if "audio_bytes" not in st.session_state:
    st.session_state.audio_bytes = None
if "last_audio_text" not in st.session_state:
    st.session_state.last_audio_text = ""
if "audio_unlocked" not in st.session_state:
    st.session_state.audio_unlocked = False


# --- Sidebar: Điều khiển ---
with st.sidebar:
    st.header("⚙️ Điều khiển")
    tiktok_username = st.text_input(
        "Username TikTok",
        value="@tv_asahi_news",
        help="Nhập username của tài khoản đang livestream, ví dụ: @username"
    )

    voice_option = st.selectbox(
        "Giọng đọc AI",
        options=[
            ("vi-VN-NamMinhNeural", "Nam Minh (Nam)"),
            ("vi-VN-HoaiMyNeural", "Hoài My (Nữ)"),
        ],
        format_func=lambda x: x[1],
        index=0
    )
    selected_voice = voice_option[0]

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
                st.session_state.audio_bytes = None
                st.session_state.last_audio_text = ""
                new_scraper = TikTokLiveScraper(
                    tiktok_username, st.session_state.data_queue
                )
                new_scraper.start()
                st.session_state.scraper = new_scraper
                st.success(f"Đang lắng nghe {tiktok_username}...")
                st.rerun()
            elif is_running:
                st.warning("Scraper đang chạy rồi!")

    with col2:
        if st.button("⏹️ Dừng", use_container_width=True):
            if st.session_state.scraper:
                st.session_state.scraper.stop()
                st.session_state.scraper = None
                st.info("Đã gửi yêu cầu dừng.")
                st.rerun()

    st.divider()
    st.caption("🔊 **Quan trọng:** Nhấn nút bên dưới MỘT LẦN để mở khóa âm thanh cho trình duyệt.")
    if st.button("🔈 Kích hoạt Âm thanh", use_container_width=True):
        st.session_state.audio_unlocked = True
        st.success("Âm thanh đã được kích hoạt!")

    if st.session_state.audio_unlocked:
        st.success("🔊 Âm thanh: ĐÃ MỞ KHÓA")
    else:
        st.warning("🔇 Âm thanh: CHƯA MỞ KHÓA")

    st.divider()
    st.caption("API Key EulerStream được cấu hình qua Secrets (`SIGN_API_KEY`) trên Cloud.")


# --- Tự động làm mới UI mỗi 1.5 giây ---
st_autorefresh(interval=1500, key="tiktok_live_refresh")


# --- Hàm hút dữ liệu từ Queue ---
def drain_queue():
    q = st.session_state.data_queue
    while not q.empty():
        try:
            ev = q.get_nowait()
            st.session_state.events_log.append(ev)
            if len(st.session_state.events_log) > 100:
                st.session_state.events_log = st.session_state.events_log[-100:]

            # Xử lý sự kiện quà tặng: cập nhật bản chiếu + tạo giọng đọc
            if ev.get("type") == "gift":
                st.session_state.latest_gifter = {
                    "user": ev.get("user", "Ai đó"),
                    "avatar_bytes": ev.get("avatar_bytes"),
                    "avatar_error": ev.get("avatar_error"),
                    "gift_name": ev.get("gift_name", "quà"),
                    "count": ev.get("count", 1),
                }
                # Tạo giọng đọc (chỉ tạo một lần cho mỗi sự kiện)
                text_to_say = (
                    f"Cảm ơn {ev.get('user', 'bạn')} đã tặng "
                    f"{ev.get('count', 1)} {ev.get('gift_name', 'món quà')}!"
                )
                if text_to_say != st.session_state.last_audio_text:
                    try:
                        st.session_state.audio_bytes = generate_tts_sync(
                            text_to_say, voice=selected_voice
                        )
                        st.session_state.last_audio_text = text_to_say
                    except Exception as e:
                        st.error(f"Lỗi tạo giọng nói: {e}")
        except queue.Empty:
            break


drain_queue()


# --- Trạng thái kết nối ---
is_running = (
    st.session_state.scraper is not None
    and st.session_state.scraper._thread is not None
    and st.session_state.scraper._thread.is_alive()
)
if is_running:
    st.success(f"🟢 Đang kết nối và lắng nghe: **{tiktok_username}**")
else:
    st.info("🔴 Chưa kết nối. Nhấn **Bắt đầu** ở sidebar để bắt đầu.")


# --- Bố cục chính: Bản chiếu (trái) + Log (phải) ---
col_stage, col_log = st.columns([2, 1])


# ============ BẢN CHIẾU (STAGE) ============
with col_stage:
    st.subheader("📺 Bản chiếu (Stage)")
    gifter = st.session_state.latest_gifter

    with st.container(border=True):
        avatar_placeholder = st.empty()

        if gifter:
            # Nếu có lỗi tải avatar, hiển thị cảnh báo
            if gifter.get("avatar_error"):
                st.warning(f"⚠️ Không thể tải avatar: {gifter['avatar_error']}")

            # Hiển thị ảnh nếu có
            if gifter.get("avatar_bytes"):
                avatar_placeholder.image(gifter["avatar_bytes"], width=300)

                col_btn1, col_btn2 = st.columns([1, 1])
                with col_btn1:
                    if st.button("🔍 Phóng to Avatar", use_container_width=True, key="zoom_avatar_btn"):
                        show_avatar_dialog(gifter["avatar_bytes"])
                with col_btn2:
                    if st.button("❌ Xóa bản chiếu", use_container_width=True, key="clear_stage_btn"):
                        st.session_state.latest_gifter = None
                        st.rerun()
            else:
                avatar_placeholder.info(
                    "Avatar người tặng quà sẽ xuất hiện ở đây khi có người tặng quà."
                )
        else:
            avatar_placeholder.info(
                "Avatar người tặng quà sẽ xuất hiện ở đây khi có người tặng quà."
            )

        # Hiển thị tên + quà
        if gifter:
            count = gifter.get("count", 1)
            gift_display = f"**{gifter['gift_name']}**"
            if count > 1:
                gift_display += f" (x{count})"
            st.success(f"🎁 **{gifter['user']}** vừa tặng {gift_display}!")

    # --- Phát âm thanh (nếu có và đã kích hoạt) ---
    st.subheader("🔊 Giọng đọc AI")
    if st.session_state.audio_bytes:
        st.audio(st.session_state.audio_bytes, format="audio/mp3", autoplay=True)
        st.caption(f"Nội dung: _{st.session_state.last_audio_text}_")
    else:
        st.caption("Chưa có âm thanh. Sẽ phát khi có người tặng quà.")


# ============ LOG SỰ KIỆN ============
with col_log:
    st.subheader("📨 Sự kiện gần đây")

    if not st.session_state.events_log:
        st.write("Chưa có sự kiện nào. Hãy đảm bảo tài khoản đang livestream và có người tương tác.")
    else:
        for ev in reversed(st.session_state.events_log[-25:]):
            ev_type = ev.get("type")
            if ev_type == "gift":
                st.success(f"🎁 **{ev.get('user', 'Ai đó')}** tặng **{ev.get('gift_name', 'quà')}**")
            elif ev_type == "comment":
                st.chat_message("user").write(
                    f"**{ev.get('user', 'Ai đó')}**: {ev.get('text', '')}"
                )
            elif ev_type == "system":
                st.info(f"ℹ️ {ev.get('message', '')}")
            else:
                st.json(ev)
