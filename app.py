import queue
import streamlit as st
import streamlit.components.v1 as components
from streamlit_autorefresh import st_autorefresh
from scraper import TikTokLiveScraper

# --- CẤU HÌNH TRANG ---
st.set_page_config(page_title="Live Art Stage", page_icon="🎨", layout="wide")

# --- KHỞI TẠO STATE ---
for key, default in [
    ("data_queue", queue.Queue()),
    ("scraper", None),
    ("latest_gifter", None),
    ("last_processed_gift", ""),
    ("is_streaming", False), # Trạng thái: Đang live hay đang setup
]:
    if key not in st.session_state:
        st.session_state[key] = default


# --- HÀM JAVASCRIPT ĐỌC TIẾNG VIỆT (0s Delay) ---
def auto_speak(text: str):
    js_code = f"""
        <script>
            function speak() {{
                var msg = new SpeechSynthesisUtterance();
                msg.text = "{text}";
                msg.lang = 'vi-VN';
                msg.rate = 1.1; 
                window.speechSynthesis.speak(msg);
            }}
            speak();
        </script>
    """
    components.html(js_code, height=0, width=0)


# ==========================================
# MÀN HÌNH 1: CÀI ĐẶT (SETUP)
# ==========================================
if not st.session_state.is_streaming:
    st.markdown("<h1 style='text-align: center; margin-top: 50px; color: #FF4B4B;'>🎨 Thiết lập Live Art Stage</h1>", unsafe_allow_html=True)
    st.markdown("<p style='text-align: center; color: #888;'>Nhập username TikTok để bắt đầu nhận quà và vẽ tranh.</p>", unsafe_allow_html=True)
    
    # Đưa form cài đặt ra giữa màn hình
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        username = st.text_input("TikTok Username:", value="@tiktok")
        st.write("") # Tạo khoảng trống
        if st.button("▶️ BẮT ĐẦU LIVE", use_container_width=True, type="primary"):
            if username:
                # Khởi động scraper
                st.session_state.scraper = TikTokLiveScraper(username, st.session_state.data_queue)
                st.session_state.scraper.start()
                st.session_state.is_streaming = True
                st.session_state.latest_gifter = None
                st.session_state.last_processed_gift = ""
                st.rerun()
                
        st.info("💡 **Hướng dẫn OBS:** Bấm 'Bắt đầu', sau đó copy link trên thanh địa chỉ trình duyệt và dán vào Browser Source trong OBS. Khung hình sẽ tự động trong suốt.")

# ==========================================
# MÀN HÌNH 2: OBS OVERLAY (KHI ĐANG LIVE)
# ==========================================
else:
    # CSS ẩn toàn bộ giao diện Streamlit, nền trong suốt
    st.markdown("""
    <style>
        /* Ẩn thanh công cụ, menu, footer */
        #MainMenu {visibility: hidden;}
        header {visibility: hidden;}
        footer {visibility: hidden;}
        
        /* Nền trong suốt để chèn lên OBS */
        .stApp {background-color: transparent;} 
        .block-container {padding-top: 1rem; padding-bottom: 0rem;}
        
        /* Nút Dừng nhỏ ở góc dưới, mờ đi để không làm hỏng stream */
        .stop-btn {
            position: fixed;
            bottom: 10px;
            right: 10px;
            opacity: 0.1;
            transition: opacity 0.3s;
            z-index: 9999;
        }
        .stop-btn:hover { opacity: 1; }
        
        /* Khung viền phát sáng cho tác phẩm */
        .art-card {
            background: rgba(14, 17, 23, 0.7);
            backdrop-filter: blur(10px);
            border-radius: 24px;
            padding: 20px;
            border: 2px solid rgba(255, 75, 75, 0.6);
            box-shadow: 0 0 40px rgba(255, 75, 75, 0.3);
            text-align: center;
        }
        .gifter-name {
            font-size: 36px;
            font-weight: 900;
            color: #FF4B4B;
            text-transform: uppercase;
            text-shadow: 0 0 10px rgba(255, 75, 75, 0.5);
        }
        .gift-text {
            font-size: 24px;
            color: #ffffff;
            font-weight: bold;
        }
    </style>
    """, unsafe_allow_html=True)

    # Tự động làm mới siêu nhanh
    st_autorefresh(interval=500, key="refresh")

    # Xử lý hàng đợi
    q = st.session_state.data_queue
    while not q.empty():
        try:
            ev = q.get_nowait()
            if ev.get("type") == "gift":
                st.session_state.latest_gifter = {
                    "user": ev.get("user", "Ai đó"),
                    "sketch_bytes": ev.get("avatar_sketch_bytes"),
                    "gift_name": ev.get("gift_name", "quà"),
                    "count": ev.get("count", 1),
                }
                
                text_to_say = f"Cảm ơn {ev.get('user')} đã tặng {ev.get('count')} {ev.get('gift_name')}!"
                if text_to_say != st.session_state.last_processed_gift:
                    auto_speak(text_to_say)
                    st.session_state.last_processed_gift = text_to_say
        except queue.Empty:
            break

    # Hiển thị tác phẩm
    gifter = st.session_state.latest_gifter
    if gifter and gifter.get("sketch_bytes"):
        # Căn giữa ảnh
        _, col_img, _ = st.columns([1, 2, 1])
        with col_img:
            st.markdown('<div class="art-card">', unsafe_allow_html=True)
            st.image(gifter["sketch_bytes"], use_container_width=True)
            st.markdown('</div>', unsafe_allow_html=True)
            
        st.markdown(f"""
        <div style="text-align: center; margin-top: 20px;">
            <div class="gifter-name">{gifter['user']}</div>
            <div class="gift-text">đã tặng <b>{gifter['count']} {gifter['gift_name']}</b></div>
        </div>
        """, unsafe_allow_html=True)
    else:
        st.markdown("""
        <div style="text-align: center; margin-top: 20vh;">
            <h1 style="color: #333; font-size: 50px;">🎨 Đang chờ quà...</h1>
        </div>
        """, unsafe_allow_html=True)

    # Nút dừng (dành cho bạn, khi đưa lên OBS nó sẽ gần như tàng hình)
    st.markdown('<div class="stop-btn">', unsafe_allow_html=True)
    if st.button("🛑 Dừng Live"):
        if st.session_state.scraper:
            st.session_state.scraper.stop()
        st.session_state.is_streaming = False
        st.session_state.latest_gifter = None
        st.rerun()
    st.markdown('</div>', unsafe_allow_html=True)
