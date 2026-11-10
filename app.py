import queue
import base64
import streamlit as st
import streamlit.components.v1 as components
from streamlit_autorefresh import st_autorefresh
from scraper import TikTokLiveScraper

st.set_page_config(page_title="Live Art Grid", layout="wide", initial_sidebar_state="collapsed")

# Khởi tạo State
for key, default in [
    ("data_queue", queue.Queue()),
    ("scraper", None),
    ("grid_images", []), # Mảng chứa tối đa 20 ảnh
    ("is_streaming", False),
    ("audio_unlocked", False),
    ("latest_speech", "") # Câu cần đọc
]:
    if key not in st.session_state:
        st.session_state[key] = default

# CSS TOÀN CỤC
css = """
<style>
    @import url('https://fonts.googleapis.com/css2?family=Montserrat:wght@400;800;900&display=swap');
    
    /* Ẩn mọi thứ của Streamlit */
    #MainMenu, header, footer {visibility: hidden;}
    .stApp {background-color: #0d1117;}
    .block-container {padding: 1rem !important; max-width: 100% !important;}
    
    /* Lưới bàn cờ */
    .grid-container {
        display: grid;
        grid-template-columns: repeat(5, 1fr); /* 5 cột */
        grid-template-rows: repeat(4, 1fr);    /* 4 hàng */
        gap: 15px;
        padding: 20px;
        height: 90vh;
        width: 100%;
    }
    
    /* Ô cờ */
    .grid-item {
        background: rgba(255, 255, 255, 0.05);
        border-radius: 16px;
        overflow: hidden;
        position: relative;
        display: flex;
        flex-direction: column;
        align-items: center;
        justify-content: flex-end;
        border: 2px solid rgba(255, 75, 75, 0.3);
        box-shadow: 0 0 15px rgba(255, 75, 75, 0.1);
        animation: popIn 0.6s cubic-bezier(0.175, 0.885, 0.32, 1.275) forwards;
    }
    
    /* Hiệu ứng xuất hiện */
    @keyframes popIn {
        0% { transform: scale(0.5); opacity: 0; }
        100% { transform: scale(1); opacity: 1; }
    }

    /* Ảnh bên trong ô */
    .grid-item img {
        width: 100%;
        height: 100%;
        object-fit: cover;
        position: absolute;
        top: 0; left: 0;
        z-index: 1;
    }
    
    /* Tên người tặng đè lên ảnh */
    .gifter-name {
        z-index: 2;
        background: linear-gradient(to top, rgba(0,0,0,0.9), transparent);
        width: 100%;
        text-align: center;
        padding: 20px 5px 10px 5px;
        font-family: 'Montserrat', sans-serif;
        font-weight: 800;
        font-size: 14px;
        color: #fff;
        text-shadow: 0 2px 4px #000;
    }
    
    /* Nút dừng */
    .stop-btn-container { position: fixed; bottom: 10px; right: 10px; z-index: 999; opacity: 0.1; }
    .stop-btn-container:hover { opacity: 1; }
</style>
"""
st.markdown(css, unsafe_allow_html=True)

# HÀM ĐỌC ÂM THANH BẰNG JAVASCRIPT (Không cần server)
def js_speak(text):
    if not text: return
    # Sử dụng Web Speech API của trình duyệt
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
# MÀN HÌNH CÀI ĐẶT
# ==========================================
if not st.session_state.is_streaming:
    st.markdown("<h2 style='text-align:center; margin-top:50px; color:white; font-family:Montserrat;'>🎨 THIẾT LẬP LIVE GRID</h2>", unsafe_allow_html=True)
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        username = st.text_input("Nhập TikTok Username:", value="@tiktok")
        
        # Nút Bắt đầu đóng vai trò "kích hoạt" âm thanh (User Gesture)
        if st.button("▶️ BẮT ĐẦU LIVE", type="primary", use_container_width=True):
            if username:
                # Kích hoạt âm thanh bằng 1 câu chào nhỏ để xin quyền trình duyệt
                js_speak("Hệ thống đã sẵn sàng")
                
                st.session_state.scraper = TikTokLiveScraper(username, st.session_state.data_queue)
                st.session_state.scraper.start()
                st.session_state.is_streaming = True
                st.session_state.grid_images = []
                st.rerun()

# ==========================================
# MÀN HÌNH LIVE (OVERLAY)
# ==========================================
else:
    st_autorefresh(interval=500, key="refresh")

    # Xử lý sự kiện
    while not st.session_state.data_queue.empty():
        ev = st.session_state.data_queue.get()
        if ev.get("type") == "gift":
            
            # Kiểm tra nếu bàn cờ đã đầy 20 ô
            if len(st.session_state.grid_images) >= 20:
                # Reset bàn cờ (Xóa ảnh cũ, nhường chỗ cho ảnh mới)
                st.session_state.grid_images = []
            
            # Thêm ảnh mới vào mảng
            if ev.get("art_bytes"):
                st.session_state.grid_images.append({
                    "user": ev.get("user"),
                    "img_b64": base64.b64encode(ev.get("art_bytes")).decode()
                })
            
            # Kích hoạt đọc tên
            text = f"Cảm ơn {ev.get('user')} đã tặng {ev.get('count')} {ev.get('gift_name')}"
            js_speak(text)

    # Vẽ bàn cờ HTML
    html_content = '<div class="grid-container">'
    
    # Nếu chưa có ảnh nào, hiện chữ chờ
    if len(st.session_state.grid_images) == 0:
         html_content += """
            <div style="grid-column: span 5; text-align:center; margin-top:30vh;">
                <h1 style="color:rgba(255,255,255,0.1); font-family:Montserrat; font-size:50px; font-weight:900;">
                    ĐANG CHỜ QUÀ...
                </h1>
            </div>
         """
    else:
        # Render từng ảnh trong bàn cờ
        for item in st.session_state.grid_images:
            html_content += f"""
            <div class="grid-item">
                <img src="data:image/png;base64,{item['img_b64']}">
                <div class="gifter-name">{item['user']}</div>
            </div>
            """
            
    html_content += '</div>'
    
    # Hiển thị toàn bộ bàn cờ
    st.markdown(html_content, unsafe_allow_html=True)

    # Nút dừng
    st.markdown('<div class="stop-btn-container">', unsafe_allow_html=True)
    if st.button("🛑 Dừng Live"):
        st.session_state.is_streaming = False
        st.session_state.grid_images = []
        st.rerun()
    st.markdown('</div>', unsafe_allow_html=True)
