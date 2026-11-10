import queue
import asyncio
import tempfile
import os
import sys
import traceback
import threading
import uuid
import base64
import streamlit as st
import streamlit.components.v1 as components
from streamlit_autorefresh import st_autorefresh
import edge_tts
from scraper import TikTokLiveScraper

# --- FIX ASYNCIO cho Streamlit ---
try:
    import nest_asyncio
    nest_asyncio.apply()
except ImportError:
    pass


# --- Cấu hình trang ---
st.set_page_config(page_title="TikTok Live Art Stage", page_icon="🎨", layout="wide")

st.markdown("""
<style>
    .stAppViewBlockContainer { padding-top: 0rem; }
    header.stAppHeader { background-color: transparent; }
    section.stMain .block-container { padding-top: 0.5rem; }
    .sketch-frame {
        border: 3px solid #FF4B4B;
        border-radius: 16px;
        padding: 10px;
        background: #0E1117;
        box-shadow: 0 0 30px rgba(255, 75, 75, 0.4);
    }
</style>
""", unsafe_allow_html=True)

st.title("🎨 TikTok Live: Sân khấu Nghệ thuật")
st.caption("Avatar người tặng quà sẽ được 'vẽ lại' thành tranh ký họa.")


# --- TTS với retry (sửa lỗi NoAudioReceived) ---
async def _generate_tts_async(text: str, voice: str, max_retries: int = 3) -> bytes:
    last_error = None
    for attempt in range(max_retries):
        try:
            communicate = edge_tts.Communicate(text, voice)
            chunks = []
            async for chunk in communicate.stream():
                if chunk["type"] == "audio":
                    chunks.append(chunk["data"])
            if chunks:
                return b"".join(chunks)
            last_error = RuntimeError("Không nhận được audio chunk.")
        except Exception as e:
            last_error = e
            if attempt < max_retries - 1:
                await asyncio.sleep(1.5 * (attempt + 1))
                continue
            raise
    raise last_error or RuntimeError("TTS thất bại sau nhiều lần thử.")


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
    t.join(timeout=45)

    if t.is_alive():
        raise TimeoutError("edge-tts quá 45 giây không phản hồi.")
    if result["error"]:
        raise result["error"]
    if not result["bytes"]:
        raise RuntimeError("edge-tts trả về dữ liệu rỗng.")
    return result["bytes"]


# --- Tự động phát audio qua HTML5 (không cần bấm) ---
def play_audio_autoplay(audio_bytes: bytes) -> None:
    """Nhúng audio dưới dạng HTML5 với unique ID → luôn autoplay khi có audio mới."""
    if not audio_bytes:
        return
    try:
        b64 = base64.b64encode(audio_bytes).decode()
        audio_id = uuid.uuid4().hex
        audio_html = f"""
        <audio id="audio_{audio_id}" autoplay="autoplay" style="display:none;">
            <source src="data:audio/mp3;base64,{b64}" type="audio/mp3">
        </audio>
        <script>
            (function() {{
                var a = document.getElementById("audio_{audio_id}");
                if (a) {{
                    var p = a.play();
                    if (p !== undefined) {{
                        p.catch(function(e) {{ console.log("Autoplay blocked:", e); }});
                    }}
                }}
            }})();
        </script>
        """
        components.html(audio_html, height=0, width=0)
    except Exception as e:
        st.error(f"Lỗi phát audio: {e}")


# --- Dialog phóng to ảnh ---
@st.dialog("Tác phẩm từ người tặng quà", width="large")
def show_avatar_dialog(image_bytes):
    if image_bytes:
        st.image(image_bytes, width="stretch")
    else:
        st.warning("Không có dữ liệu ảnh để hiển thị.")


# --- Session State ---
for key, default in [
    ("data_queue", queue.Queue()),
    ("scraper", None),
    ("events_log", []),
    ("latest_gifter", None),
    ("audio_bytes", None),
    ("audio_token", None),
    ("last_audio_text", ""),
    ("audio_unlocked", False),
]:
    if key not in st.session_state:
        st.session_state[key] = default


# --- Sidebar ---
with st.sidebar:
    st.header("⚙️ Điều khiển")
    tiktok_username = st.text_input(
        "Username TikTok", value="@tiktok",
        help="Username của tài khoản đang livestream."
    )

    voice_option = st.selectbox(
        "Giọng đọc AI",
        options=[
            ("vi-VN-NamMinhNeural", "Nam Minh (Nam)"),
            ("vi-VN-HoaiMyNeural", "Hoài My (Nữ)"),
        ],
        format_func=lambda x: x[1], index=0
    )
    selected_voice = voice_option[0]

    if st.button("🎤 Test giọng đọc", width="stretch"):
        try:
            with st.spinner("Đang tạo âm thanh test..."):
                test_audio = generate_tts_sync(
                    "Xin chào, đây là bài kiểm tra giọng đọc AI.", selected_voice
                )
            play_audio_autoplay(test_audio)
            st.success("Đã phát âm thanh test!")
        except Exception as e:
            st.error(f"Lỗi: {e}")
            traceback.print_exc(file=sys.stderr)

    st.divider()

    col1, col2 = st.columns(2)
    with col1:
        if st.button("▶️ Bắt đầu", width="stretch"):
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
        if st.button("⏹️ Dừng", width="stretch"):
            if st.session_state.scraper:
                st.session_state.scraper.stop()
                st.session_state.scraper = None
                st.info("Đã dừng.")
                st.rerun()

    st.divider()
    st.caption("🔊 Nhấn nút dưới MỘT LẦN để trình duyệt cho phép autoplay.")
    if st.button("🔈 Kích hoạt Âm thanh", width="stretch"):
        st.session_state.audio_unlocked = True
        # Phát một âm thanh "im lặng" để mồi audio context
        try:
            silent = generate_tts_sync(" ", selected_voice)
            play_audio_autoplay(silent)
        except Exception:
            pass
        st.success("Đã kích hoạt!")

    if st.session_state.audio_unlocked:
        st.success("🔊 Âm thanh: ĐÃ MỞ KHÓA")
    else:
        st.warning("🔇 Âm thanh: CHƯA MỞ KHÓA")


# --- Tự động làm mới ---
st_autorefresh(interval=1500, key="tiktok_live_refresh")


# --- Xử lý Queue ---
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
                    "sketch_bytes": ev.get("avatar_sketch_bytes"),
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
                        st.session_state.audio_bytes = generate_tts_sync(
                            text_to_say, selected_voice
                        )
                        st.session_state.last_audio_text = text_to_say
                        st.session_state.audio_token = uuid.uuid4().hex
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
    st.success(f"🟢 Đang kết nối: **{tiktok_username}**")
else:
    st.info("🔴 Chưa kết nối. Nhấn **Bắt đầu** ở sidebar.")


# ============ BẢN CHIẾU FULL MÀN HÌNH ============
st.subheader("🖼️ Sân khấu Nghệ thuật")
gifter = st.session_state.latest_gifter

# Khung vẽ full width, tỷ lệ lớn
with st.container():
    if gifter and gifter.get("sketch_bytes"):
        st.markdown('<div class="sketch-frame">', unsafe_allow_html=True)
        st.image(gifter["sketch_bytes"], width="stretch")
        st.markdown('</div>', unsafe_allow_html=True)

        col_info, col_btn = st.columns([3, 1])
        with col_info:
            count = gifter.get("count", 1)
            gift_display = f"**{gifter['gift_name']}**" + (f" (x{count})" if count > 1 else "")
            st.success(f"🎁 Tác phẩm từ **{gifter['user']}** — đã tặng {gift_display}")
        with col_btn:
            if st.button("🔍 Phóng to", width="stretch"):
                show_avatar_dialog(gifter["sketch_bytes"])

        if gifter.get("error"):
            st.warning(f"⚠️ {gifter['error']}")
    else:
        st.info("Tác phẩm nghệ thuật từ người tặng quà sẽ xuất hiện tại đây.")
        if gifter and gifter.get("error"):
            st.warning(f"⚠️ Không thể tạo tác phẩm: {gifter['error']}")


# --- Tự động phát audio (không cần bấm) ---
if st.session_state.audio_bytes and st.session_state.audio_token:
    # Chỉ render player mới khi token thay đổi (mỗi lần có audio mới)
    token_slot = st.empty()
    with token_slot.container():
        play_audio_autoplay(st.session_state.audio_bytes)
    st.caption(f"🔊 Đã đọc: _{st.session_state.last_audio_text}_")


# ============ NHẬT KÝ SỰ KIỆN ============
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
