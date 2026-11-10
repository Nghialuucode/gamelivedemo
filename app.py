import queue
import streamlit as st
from streamlit_autorefresh import st_autorefresh
from scraper import TikTokLiveScraper

# --- Cấu hình trang ---
st.set_page_config(page_title="TikTok Live Demo", page_icon="🎮", layout="wide")
st.title("🎮 TikTok Live Interactive Demo")
st.caption("Demo: Scraper Thread + Queue + Streamlit")

# --- Khởi tạo Session State (chỉ chạy một lần cho mỗi phiên) ---
if "data_queue" not in st.session_state:
    st.session_state.data_queue = queue.Queue()

if "scraper" not in st.session_state:
    st.session_state.scraper = None

if "events_log" not in st.session_state:
    st.session_state.events_log = []

# --- Sidebar: Nhập username và điều khiển ---
with st.sidebar:
    st.header("⚙️ Cấu hình")
    tiktok_username = st.text_input(
        "Tên người dùng TikTok (unique_id)",
        value="@tv_asahi_news",  # Tài khoản tin tức thường xuyên live, dùng để test
        help="Nhập username của tài khoản đang livestream, ví dụ: @username"
    )
    
    col1, col2 = st.columns(2)
    with col1:
        if st.button("▶️ Bắt đầu", use_container_width=True):
            # Kiểm tra xem scraper cũ có đang chạy không
            is_running = (
                st.session_state.scraper is not None 
                and st.session_state.scraper._thread is not None 
                and st.session_state.scraper._thread.is_alive()
            )
            if tiktok_username and not is_running:
                # Xóa log cũ khi bắt đầu phiên mới
                st.session_state.events_log = []
                # Tạo và khởi chạy scraper mới
                new_scraper = TikTokLiveScraper(
                    unique_id=tiktok_username,
                    data_queue=st.session_state.data_queue
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
                # Đặt lại scraper để có thể bắt đầu lại
                st.session_state.scraper = None
                st.info("Đã gửi yêu cầu dừng.")
                st.rerun()

    st.divider()
    st.caption("API Key EulerStream được cấu hình qua Secrets (SIGN_API_KEY) trên Cloud.")

# --- Tự động làm mới UI mỗi 2 giây để cập nhật dữ liệu mới ---
st_autorefresh(interval=2000, key="tiktok_live_refresh")

# --- Hàm hút dữ liệu từ Queue và cập nhật log ---
def drain_queue():
    q = st.session_state.data_queue
    while not q.empty():
        try:
            event = q.get_nowait()
            st.session_state.events_log.append(event)
            # Giới hạn log để tránh phình bộ nhớ (giữ 200 sự kiện gần nhất)
            if len(st.session_state.events_log) > 200:
                st.session_state.events_log = st.session_state.events_log[-200:]
        except queue.Empty:
            break

drain_queue()

# --- Hiển thị trạng thái ---
is_running = (
    st.session_state.scraper is not None 
    and st.session_state.scraper._thread is not None 
    and st.session_state.scraper._thread.is_alive()
)
if is_running:
    st.success(f"🟢 Đang kết nối và lắng nghe: **{tiktok_username}**")
else:
    st.info("🔴 Chưa kết nối. Nhấn **Bắt đầu** ở sidebar để bắt đầu.")

st.divider()

# --- Hiển thị các sự kiện đã nhận (mới nhất ở trên) ---
st.subheader("📨 Sự kiện nhận được")

if not st.session_state.events_log:
    st.write("Chưa có sự kiện nào. Hãy đảm bảo tài khoản đang livestream và có người tương tác.")
else:
    for ev in reversed(st.session_state.events_log):
        if ev.get("type") == "comment":
            st.chat_message("user").write(
                f"**{ev.get('user', 'Ai đó')}** (`@{ev.get('user_id', '?')}`): {ev.get('text', '')}"
            )
        elif ev.get("type") == "gift":
            count = ev.get('count', 1)
            gift_display = f"**{ev.get('gift_name')}**" 
            if count > 1:
                gift_display += f" (x{count})"
            st.success(
                f"🎁 **{ev.get('user', 'Ai đó')}** (`@{ev.get('user_id', '?')}`) đã tặng {gift_display}!"
            )
        elif ev.get("type") == "system":
            st.info(f"ℹ️ {ev.get('message', '')}")
        else:
            st.json(ev)
