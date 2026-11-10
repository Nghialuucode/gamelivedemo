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
from streamlit_TTS import auto_play
from scraper import TikTokLiveScraper

# --- FIX ASYNCIO cho Streamlit ---
try:
    import nest_asyncio
    nest_asyncio.apply()
except ImportError:
    pass


# --- Cấu hình trang (Layout rộng) ---
st.set_page_config(page_title="TikTok Live Art Stage", page_icon="🎨", layout="wide")

# --- CSS để loại bỏ khoảng trắng thừa, tạo không gian full màn hình ---
st.markdown("""
<style>
    /* Loại bỏ padding-top của container chính */
    .stAppViewBlockContainer {
        padding-top: 0rem;
    }
    /* Ẩn header mặc định của Streamlit để có thêm không gian */
    header.stAppHeader {
        background-color: transparent;
    }
    /* Đảm bảo nội dung chính bắt đầu ngay từ trên cùng */
    section.stMain .block-container {
        padding-top: 0rem;
        z-index: 1;
    }
</style>
""", unsafe_allow_html=True)


st.title("🎨 TikTok Live: Sân khấu Nghệ thuật")
st.caption("Avatar người tặng quà sẽ được 'vẽ lại' thành tranh ký họa.")


# --- Hàm tạo giọng nói (Giữ nguyên logic cũ) ---
async def _generate_tts_async(text: str, voice: str) -> bytes:
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


# --- Dialog phóng to ảnh (Giữ nguyên) ---
@st.dialog("Tác phẩm từ người tặng quà", width="large")
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
    ("audio_to_play", None), # Lưu trữ dict audio chờ phát
    ("last_audio_text", ""),
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

    if st.button("🎤 Test giọng đọc", use_container_width=True):
        try:
            with st.spinner("Đang tạo âm thanh test..."):
                test_audio_bytes = generate_tts_sync(
                    "Xin chào, đây là bài kiểm tra giọng đọc AI.",
                    selected_voice
                )
            # Với mục đích test, chúng ta vẫn dùng st.audio
            st.audio(test_audio_bytes, format="audio/mp3")
            st.success("Tạo âm thanh thành công!")
        except Exception as e:
            st.error(f"Lỗi tạo giọng đọc: {e}")
            traceback.print_exc(file=sys.stderr)

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
                st.session_state.audio_to_play = None
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
                    "sketch_bytes": ev.get("avatar_sketch_bytes"), # Sử dụng ảnh sketch
                    "error": ev.get("avatar_error"),
                    "gift_name": ev.get("gift_name", "quà"),
                    "count": ev.get("count", 1),
                }

                text_to_say = (
                    f"Cảm ơn {ev.get('user', 'bạn')} đã tặng "
                    f"{ev.get('count', 1)} {ev.get('gift_name', 'món quà')}!"
                )
                if text_to_say != st.session_state.last_audio_text:
                    try:
                        audio_bytes = generate_tts_sync(text_to_say, selected_voice)
                        # Chuẩn bị dict audio cho streamlit-TTS
                        # edge-tts trả về MP3, nhưng streamlit-TTS cần WAV.
                        # Đây là một hạn chế. Để đơn giản, chúng ta vẫn dùng st.audio với autoplay=True
                        # và chấp nhận rằng nó có thể không tự động phát 100% trên mọi trình duyệt.
                        # Giải pháp hoàn hảo với streamlit-TTS đòi hỏi phải chuyển đổi sang WAV.
                        # Tuy nhiên, để giữ code gọn, chúng ta sẽ thử nghiệm với st.audio trước.
                        st.session_state.audio_to_play = audio_bytes
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


# ============ KHU VỰC "MÁY CHIẾU" FULL MÀN HÌNH ============
st.subheader("🖼️ Sân khấu Nghệ thuật")
gifter = st.session_state.latest_gifter

# Sử dụng một container rộng để hiển thị ảnh
with st.container():
    if gifter and gifter.get("sketch_bytes"):
        # Hiển thị ảnh sketch với kích thước lớn
        st.image(gifter["sketch_bytes"], use_container_width=True)
        
        col_info, col_btn = st.columns([3, 1])
        with col_info:
            count = gifter.get("count", 1)
            gift_display = f"**{gifter['gift_name']}**" + (f" (x{count})" if count > 1 else "")
            st.success(f"🎁 Tác phẩm từ **{gifter['user']}** (đã tặng {gift_display})")
        with col_btn:
            if st.button("🔍 Xem ảnh gốc", use_container_width=True):
                # Giả sử chúng ta vẫn lưu ảnh gốc, nhưng hiện tại chỉ có sketch.
                # Để đơn giản, nút này sẽ mở dialog với ảnh sketch.
                show_avatar_dialog(gifter["sketch_bytes"])
    else:
        st.info("Tác phẩm nghệ thuật từ người tặng quà sẽ xuất hiện tại đây.")
        if gifter and gifter.get("error"):
            st.warning(f"⚠️ Không thể tạo tác phẩm: {gifter['error']}")

# --- Phát âm thanh tự động (sử dụng st.audio với autoplay) ---
if st.session_state.audio_to_play:
    # Đặt audio player vào một container riêng, ẩn đi nếu có thể
    # và cố gắng tự động phát.
    st.audio(st.session_state.audio_to_play, format="audio/mp3", autoplay=True)
    # Xóa audio sau khi đã cố gắng phát để tránh phát lại không cần thiết
    # st.session_state.audio_to_play = None # (Tạm thời giữ lại để người dùng có thể nghe lại nếu muốn)


# ============ LOG SỰ KIỆN (Thu gọn) ============
with st.expander("📨 Nhật ký sự kiện gần đây", expanded=False):
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
