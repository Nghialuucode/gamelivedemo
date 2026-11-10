import queue
import base64
import streamlit as st
from streamlit_autorefresh import st_autorefresh
from scraper import TikTokLiveScraper

# Cấu hình trang
st.set_page_config(page_title="Live Art Grid", layout="wide", initial_sidebar_state="collapsed")

# Khởi tạo State
for key, default in [
    ("data_queue", queue.Queue()),
    ("scraper", None),
    ("grid_items", []), 
    ("is_streaming", False),
    ("audio_text", "") 
]:
    if key not in st.session_state:
        st.session_state[key] = default

# CSS TOÀN CỤC
css = """
<style>
    @import url('https://fonts.googleapis.com/css2?family=Montserrat:wght@800;900&display=swap');
    
    /* Xóa lề mặc định của Streamlit */
    #MainMenu, header, footer {visibility: hidden;}
    .stApp {background-color: #0a0a0c;}
    .block-container {
        padding: 10px !important; 
        max-width: 100% !important;
    }
    
    /* Lưới bàn cờ 5x4 */
    .grid-container {
        display: grid;
        grid-template-columns: repeat(5, 1fr);
        gap: 12px; 
        width: 100%;
    }
    
    /* Từng ô ảnh vuông vức */
    .grid-item {
        position: relative;
        width: 100%;
        aspect-ratio: 1 / 1; /* Ép thành hình vuông tuyệt đối */
        border-radius: 12px;
        overflow: hidden;
        background: rgba(255, 255, 255, 0.05);
        border: 2px solid rgba(255, 75, 75, 0.4);
        box-shadow: 0 4px 15px rgba(0, 0, 0, 0.5);
        animation: popIn 0.5s cubic-bezier(0.175, 0.885, 0.32, 1.275) forwards;
    }
    
    /* Ô trống */
    .grid-item.empty {
        border: 2px dashed rgba(255, 255, 255, 0.1);
        box-shadow: none;
        background: #15151c;
        animation: none;
    }
    
    @keyframes popIn {
        0% { transform: scale(0.8); opacity: 0; }
        100% { transform: scale(1); opacity: 1; }
    }

    /* Ảnh lấp đầy ô */
    .grid-item img {
        width: 100%;
        height: 100%;
        object-fit: cover;
        object-position: center;
    }
    
    /* Tên người tặng */
    .gifter-name {
        position: absolute;
        bottom: 0;
        left: 0;
        width: 100%;
        background: linear-gradient(to top, rgba(0,0,0,0.95) 20%, transparent);
        padding: 25px 5px 8px 5px;
        text-align: center;
        font-family: 'Montserrat', sans-serif;
        font-weight: 900;
        font-size: 13px;
        color: #fff;
        text-shadow: 0 1px 3px #000, 0 0 5px #000;
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;
    }
    
    /* Nút dừng */
    .stop-btn { position: fixed; bottom: 10px; right: 10px; z-index: 999; opacity: 0.1; transition: 0.3s; }
    .stop-btn:hover { opacity: 1; }
</style>
"""
st.markdown(css, unsafe_allow_html=True)


# ==========================================
# MÀN HÌNH CÀI ĐẶT
# ==========================================
if not st.session_state.is_streaming:
    st.markdown("<h1 style='text-align:center; margin-top:15vh; color:#FF4B4B; font-family:Montserrat; font-weight:900;'>🎨 LIVE ART GRID</h1>", unsafe_allow_html=True)
    st.markdown("<p style='text-align:center; color:#888;'>Bàn cờ 20 ô - Tự động đọc tên</p>", unsafe_allow_html=True)
    
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        username = st.text_input("Nhập TikTok Username:", value="@tiktok")
        
        if st.button("▶️ BẮT ĐẦU LIVE", type="primary", width="stretch"):
            if username:
                st.session_state.scraper = TikTokLiveScraper(username, st.session_state.data_queue)
                st.session_state.scraper.start()
                st.session_state.is_streaming = True
                st.session_state.grid_items = []
                st.session_state.audio_text = "Hệ thống đã sẵn sàng" 
                st.rerun()

# ==========================================
# MÀN HÌNH LIVE (BÀN CỜ)
# ==========================================
else:
    st_autorefresh(interval=800, key="refresh")

    # 1. Xử lý sự kiện từ Queue
    while not st.session_state.data_queue.empty():
        ev = st.session_state.data_queue.get()
        if ev.get("type") == "gift":
            st.session_state.audio_text = f"Cảm ơn {ev.get('user')} đã tặng {ev.get('count')} {ev.get('gift_name')}"
            
            img_b64 = base64.b64encode(ev.get("art_bytes")).decode()
            st.session_state.grid_items.append({
                "name": ev.get("user"),
                "img_b64": img_b64
            })
            
            # Giới hạn 20 ô
            if len(st.session_state.grid_items) > 20:
                st.session_state.grid_items.pop(0)

    # 2. TẠO CHUỖI HTML (Bắt buộc phải nối liền, không xuống dòng)
    html_str = "<div class='grid-container'>"
    
    for i in range(20):
        if i < len(st.session_state.grid_items):
            item = st.session_state.grid_items[i]
            # Thêm cấu trúc HTML ko có khoảng trắng
            html_str += f"<div class='grid-item'><img src='data:image/png;base64,{item['img_b64']}'><div class='gifter-name'>{item['name']}</div></div>"
        else:
            html_str += "<div class='grid-item empty'></div>"
            
    html_str += "</div>"

    # 3. Hiển thị
    st.markdown(html_str, unsafe_allow_html=True)

    # 4. Âm thanh (Sử dụng Web Speech API - Không trễ)
    if st.session_state.audio_text:
        # Dùng JS để gọi giọng đọc của hệ điều hành
        js_speak = f"""
        <script>
            var msg = new SpeechSynthesisUtterance("{st.session_state.audio_text}");
            msg.lang = 'vi-VN';
            msg.rate = 1.1;
            window.speechSynthesis.speak(msg);
        </script>
        """
        st.markdown(js_speak, unsafe_allow_html=True)
        # Reset để không đọc lại
        st.session_state.audio_text = "" 

    # 5. Nút Dừng
    st.markdown('<div class="stop-btn">', unsafe_allow_html=True)
    if st.button("🛑 Stop"):
        st.session_state.is_streaming = False
        st.session_state.grid_items = []
        st.rerun()
    st.markdown('</div>', unsafe_allow_html=True)
