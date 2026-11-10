import queue
import asyncio
import tempfile
import os
import sys
import traceback
import threading
import streamlit as st
from streamlit_autorefresh import st_autorefresh
import edge_tts
from scraper import TikTokLiveScraper

# --- FIX ASYNCIO cho Streamlit (bắt buộc phải có trước khi gọi edge-tts) ---
try:
    import nest_asyncio
    nest_asyncio.apply()
except ImportError:
    pass


# --- Cấu hình trang ---
st.set_page_config(page_title="TikTok Live Game Demo", page_icon="🎮", layout="wide")
st.title("🎮 TikTok Live: Đọc tên & Bản chiếu Avatar")
st.caption("Demo: Scraper Thread + Queue + Edge TTS + Avatar Stage")


# --- Hàm tạo giọng nói ---
async def _generate_tts_async(text: str, voice: str) -> bytes:
    """Tạo file âm thanh từ văn bản bằng edge-tts, trả về bytes."""
    communicate = edge_tts.Communicate(text, voice)
    with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as tmp:
        tmp_path = tmp.name
    try:
        await communicate.save(tmp_path)
        with open(tmp_path, "rb") as f:
            return f.read()
    finally:
        if os.path.exists(tmp_path):
            try:
                os.unlink(tmp_path)
            except OSError:
                pass


def generate_tts_sync(text: str, voice: str) -> bytes:
    """
    Chạy edge-tts trong một THREAD RIÊNG có event loop riêng.
    Tránh hoàn toàn lỗi 'asyncio.run() cannot be called from a running event loop'
    thường gặp trong Streamlit.
    """
    result = {"bytes": None, "error": None}

    def _runner():
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                result["bytes"] = loop.run_until_complete(_generate_tts_async(text, voice))
            finally:
                loop.close()
        except Exception as e:
            result["error"] = e

    t = threading.Thread(target=_runner, daemon=True)
    t.start()
    t.join(timeout=30)

    if t.is_alive():
        raise TimeoutError("edge-tts quá 30 giây không phản hồi.")
    if result["error"]:
        raise result["error"]
    if not result["bytes"]:
        raise RuntimeError("edge-tts trả về dữ liệu rỗng.")
    return result["bytes"]


# --- Dialog phóng to avatar ---
@st.dialog("Ảnh đại diện người tặng quà", width="large")
def show_avatar_dialog(image_bytes):
    if image_bytes:
        st.image(image_bytes, use_container_width=True)
    else:
        st.warning("Không có dữ liệu ảnh để hiển thị.")


# --- Khởi tạo Session State ---
for key, default in [
    ("data_queue", queue.Queue()),
    ("scraper", None),
    ("events_log", []),
    ("latest_gifter", None),
    ("audio_bytes", None),
    ("last_audio_text", ""),
    ("audio_unlocked", False),
    ("test_audio_bytes", None),
]:
    if key not in st.session_state:
        st.session_state[key] = default


# --- Sidebar ---
with st.sidebar:
    st.header("⚙️ Điều khiển")
    tiktok_username = st.text_input(
        "Username TikTok",
        value="@tiktok",
        help="Nhập username của tài khoản đang livestream."
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

    # --- Nút test giọng đọc (công cụ debug quan trọng) ---
    if st.button("🎤 Test giọng đọc", use_container_width=True):
        try:
            with st.spinner("Đang tạo âm thanh test..."):
                test_audio = generate_tts_sync(
                    "Xin chào, đây là bài kiểm tra giọng đọc AI.",
                    selected_voice
                )
            st.session_state.test_audio_bytes = test_audio
            st.success("Tạo âm thanh thành công!")
        except Exception as e:
            st.error(f"Lỗi tạo giọng đọc: {e}")
            traceback.print_exc(file=sys.stderr)

    if st.session_state.test_audio_bytes:
        st.audio(st.session_state.test_audio_bytes, format="audio/mp3")

    st.divider()

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
                new_scraper = TikTokLiveScraper(tiktok_username, st.session_state.data_queue)
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
    st.caption("🔊 **Quan trọng:** Nhấn nút dưới MỘT LẦN để mở khóa âm thanh cho trình duyệt.")
    if st.button("🔈 Kích hoạt Âm thanh", use_container_width=True):
        st.session_state.audio_unlocked = True
        st.success("Âm thanh đã được kích hoạt!")
    if st.session_state.audio_unlocked:
        st.success("🔊 Âm thanh: ĐÃ MỞ KHÓA")
    else:
        st.warning("🔇 Âm thanh: CHƯA MỞ KHÓA")


# --- Tự động làm mới UI ---
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

            if ev.get("type") == "gift":
                st.session_state.latest_gifter = {
                    "user": ev.get("user", "Ai đó"),
                    "avatar_bytes": ev.get("avatar_bytes"),
                    "avatar_error": ev.get("avatar_error"),
                    "gift_name": ev.get("gift_name", "quà"),
                    "count": ev.get("count", 1),
                }

                text_to_say = (
                    f"Cảm ơn {ev.get('user', 'bạn')} đã tặng "
                    f"{ev.get('count', 1)} {ev.get('gift_name', 'món quà')}!"
                )
                if text_to_say != st.session_state.last_audio_text:
                    try:
                        st.session_state.audio_bytes = generate_tts_sync(
                            text_to_say, selected_voice
                        )
                        st.session_state.last_audio_text = text_to_say
                    except Exception as e:
                        traceback.print_exc(file=sys.stderr)
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
    st.info("🔴 Chưa kết nối. Nhấn **Bắt đầu** ở sidebar.")


# --- Bố cục chính ---
col_stage, col_log = st.columns([2, 1])


# ============ BẢN CHIẾU ============
with col_stage:
    st.subheader("📺 Bản chiếu (Stage)")
    gifter = st.session_state.latest_gifter

    with st.container(border=True):
        avatar_placeholder = st.empty()

        if gifter and gifter.get("avatar_bytes"):
            # Hiển thị ảnh lớn hơn (380px) và thêm caption độ phân giải
            img = gifter["avatar_bytes"]
            try:
                from PIL import Image
                import io
                w, h = Image.open(io.BytesIO(img)).size
                caption = f"Độ phân giải: {w}×{h}px"
            except Exception:
                caption = ""

            avatar_placeholder.image(img, width=380, caption=caption)

            col_btn1, col_btn2 = st.columns(2)
            with col_btn1:
                if st.button("🔍 Phóng to Avatar", use_container_width=True, key="zoom_avatar_btn"):
                    show_avatar_dialog(img)
            with col_btn2:
                if st.button("❌ Xóa bản chiếu", use_container_width=True, key="clear_stage_btn"):
                    st.session_state.latest_gifter = None
                    st.rerun()

            if gifter.get("avatar_error"):
                st.warning(f"⚠️ {gifter['avatar_error']}")

            count = gifter.get("count", 1)
            gift_display = f"**{gifter['gift_name']}**" + (f" (x{count})" if count > 1 else "")
            st.success(f"🎁 **{gifter['user']}** vừa tặng {gift_display}!")
        else:
            if gifter and gifter.get("avatar_error"):
                st.warning(f"⚠️ Không thể tải avatar: {gifter['avatar_error']}")
                count = gifter.get("count", 1)
                gift_display = f"**{gifter['gift_name']}**" + (f" (x{count})" if count > 1 else "")
                st.success(f"🎁 **{gifter['user']}** vừa tặng {gift_display}!")
            else:
                avatar_placeholder.info("Avatar người tặng quà sẽ xuất hiện ở đây.")

    # --- Phát âm thanh (đã sửa: bỏ tham số key) ---
    st.subheader("🔊 Giọng đọc AI")
    if st.session_state.audio_bytes:
        st.audio(
            st.session_state.audio_bytes,
            format="audio/mp3",
            autoplay=True
        )
        st.caption(f"Nội dung: _{st.session_state.last_audio_text}_")
    else:
        st.caption("Chưa có âm thanh. Sẽ phát khi có người tặng quà.")


# ============ LOG SỰ KIỆN ============
with col_log:
    st.subheader("📨 Sự kiện gần đây")
    if not st.session_state.events_log:
        st.write("Chưa có sự kiện nào.")
    else:
        for ev in reversed(st.session_state.events_log[-25:]):
            ev_type = ev.get("type")
            if ev_type == "gift":
                st.success(f"🎁 **{ev.get('user', 'Ai đó')}** tặng **{ev.get('gift_name', 'quà')}**")
            elif ev_type == "comment":
                st.chat_message("user").write(f"**{ev.get('user', 'Ai đó')}**: {ev.get('text', '')}")
            elif ev_type == "system":
                st.info(f"ℹ️ {ev.get('message', '')}")
            else:
                st.json(ev)
