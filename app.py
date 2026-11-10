import queue
import streamlit as st
import streamlit.components.v1 as components
from streamlit_autorefresh import st_autorefresh
from scraper import TikTokLiveScraper

# --- CẤU HÌNH TRANG ---
st.set_page_config(page_title="Live Art Stage", page_icon="🎨", layout="wide")

# --- CSS LÀM GIAO DIỆN TRONG SUỐT, ĐẸP, DÀNH CHO OBS ---
st.markdown("""
<style>
    /* Ẩn toàn bộ thanh công cụ Streamlit */
    #MainMenu {visibility: hidden;}
    header {visibility: hidden;}
    footer {visibility: hidden;}
    
    /* Nền tối sang trọng */
    .stApp {
        background-color: #0d1117; 
    }
    
    /* Khung chứa tác phẩm (Glassmorphism) */
    .art-card {
        background: rgba(255, 255, 255, 0.05);
        backdrop-filter: blur(10px);
        border-radius: 24px;
        padding: 30px;
        border: 2px solid rgba(255, 75, 75, 0.6);
        box-shadow: 0 0 40px rgba(255, 75, 75, 0.3);
        text-align: center;
        margin-top: 20px;
        transition: all 0.5s ease;
    }
    .art-image {
        border-radius: 16px;
        box-shadow: 0 8px 32px 0 rgba(0, 0, 0, 0.37);
        max-width: 100%;
        height: auto;
    }
    .gifter-name {
        font-size: 32px;
        font-weight: 800;
        color: #FF4B4B;
        margin-top: 20px;
        text-transform: uppercase;
        letter-spacing: 2px;
    }
    .gift-text {
        font-size: 24px;
        color: #ffffff;
    }
</style>
""", unsafe_allow_html=True)


# --- HÀM JAVASCRIPT ĐỌC TIẾNG VIỆT (0s Delay) ---
def auto_speak(text: str):
    """Sử dụng Web Speech API của trình duyệt để đọc ngay lập tức."""
    # Lưu ý: Trình duyệt của khách (hoặc OBS) phải hỗ trợ tiếng Việt.
    js_code = f"""
        <script>
            function speak() {{
                var msg = new SpeechSynthesisUtterance();
                msg.text = "{text}";
                msg.lang = 'vi-VN';
                msg.rate = 1.0; // Tốc độ đọc
                msg.pitch = 1.0; // Cao độ
                window.speechSynthesis.speak(msg);
            }}
            speak();
        </script>
    """
    components.html(js_code, height=0, width=0)


# --- KHỞI TẠO STATE ---
for key, default in [
    ("data_queue", queue.Queue()),
    ("scraper", None),
    ("latest_gifter", None),
    ("last_processed_gift", ""),
]:
    if key not in st.session_state:
        st.session_state[key] = default


# --- SIDEBAR ĐIỀU KHIỂN ---
with st.sidebar:
    st.header("⚙️ Streamer Panel")
    tiktok_username = st.text_input("TikTok Username", value="@tiktok")
    
    col1, col2 = st.columns(2)
    with col1:
        if st.button("▶️ Bắt đầu", use_container_width=True):
            if tiktok_username and not (st.session_state.scraper and st.session_state.scraper._thread.is_alive()):
                st.session_state.latest_gifter = None
                st.session_state.last_processed_gift = ""
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
    st.info("💡 **Mẹo OBS:** Thêm một 'Browser Source' trỏ đến link Streamlit này. Chỉnh kích thước 1080x1920 (dọc) hoặc 1920x1080 (ngang) để làm overlay.")

# --- TỰ ĐỘNG LÀM MỚI (Siêu nhanh 0.5s) ---
st_autorefresh(interval=500, key="refresh")

# --- XỬ LÝ HÀNG ĐỢI ---
def process_queue():
    q = st.session_state.data_queue
    while not q.empty():
        try:
            ev = q.get_nowait()
            if ev.get("type") == "gift":
                # Cập nhật state
                st.session_state.latest_gifter = {
                    "user": ev.get("user", "Ai đó"),
                    "sketch_bytes": ev.get("avatar_sketch_bytes"),
                    "gift_name": ev.get("gift_name", "quà"),
                    "count": ev.get("count", 1),
                }
                
                # Tạo câu đọc
                text_to_say = f"Cảm ơn {ev.get('user')} đã tặng {ev.get('count')} {ev.get('gift_name')}!"
                
                # Chỉ đọc nếu là quà mới (tránh đọc lại liên tục khi Streamlit refresh)
                if text_to_say != st.session_state.last_processed_gift:
                    auto_speak(text_to_say)
                    st.session_state.last_processed_gift = text_to_say
                    
        except queue.Empty:
            break

process_queue()

# --- KHU VỰC HIỂN THỊ (MÁY CHIẾU) ---
gifter = st.session_state.latest_gifter

if gifter and gifter.get("sketch_bytes"):
    # Giả lập HTML card bằng Streamlit
    st.markdown(f"""
    <div class="art-card">
        <p style="color: #a0a0a0; font-size: 18px; margin-bottom: 10px;">✨ TÁC PHẨM MỚI ✨</p>
    </div>
    """, unsafe_allow_html=True)
    
    # Chèn ảnh vào giữa
    _, col_img, _ = st.columns([1, 3, 1]) # Căn giữa ảnh
    with col_img:
        st.image(gifter["sketch_bytes"], use_container_width=True)
        
    st.markdown(f"""
    <div style="text-align: center; margin-top: 20px;">
        <div class="gifter-name">{gifter['user']}</div>
        <div class="gift-text">đã tặng <b>{gifter['count']} {gifter['gift_name']}</b></div>
    </div>
    """, unsafe_allow_html=True)
    
else:
    # Trạng thái chờ
    st.markdown("""
    <div style="text-align: center; margin-top: 100px;">
        <h1 style="color: #333;">🎨 Đang chờ quà tặng...</h1>
        <p style="color: #666;">Màn hình sẽ tự động cập nhật khi có người tặng quà.</p>
    </div>
    """, unsafe_allow_html=True)
