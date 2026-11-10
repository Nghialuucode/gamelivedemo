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
    ("audio_text", "") # Lưu câu cần đọc
]:
    if key not in st.session_state:
        st.session_state[key] = default

# CSS TOÀN CỤC
# Ép giao diện tràn viền, ẩn mọi thành phần thừa của Streamlit
css = """
<style>
    @import url('https://fonts.googleapis.com/css2?family=Montserrat:wght@700;900&display=swap');
    
    /* Xóa lề mặc định */
    #MainMenu, header, footer {visibility: hidden;}
    .stApp {background-color: #0a0a0c;}
    .block-container {padding: 0 !important; margin: 0 !important; max-width: 100% !important;}
    
    /* Lưới bàn cờ 5x4 */
    .grid-container {
        display: grid;
        grid-template-columns: repeat(5, 1fr);
        grid-template-rows: repeat(4, 1fr);
        gap: 8px;
        padding: 8px;
        height: 100vh;
        width: 100vw;
        box-sizing: border-box;
        background: radial-gradient(circle at center, #1a1a24 0%, #0a0a0c 100%);
    }
    
    /* Từng ô ảnh */
    .grid-item {
        position: relative;
        border-radius: 12px;
        overflow: hidden;
        background: rgba(255, 255, 255, 0.05);
        border: 2px solid rgba(255, 75, 75, 0.5);
        box-shadow: 0 0 15px rgba(255, 75, 75, 0.2);
        animation: popIn 0.5s cubic-bezier(0.175, 0.885, 0.32, 1.275) forwards;
    }
    
    .grid-item.empty {
        border: 2px dashed rgba(255, 255, 255, 0.1);
        box-shadow: none;
        background: transparent;
        animation: none;
    }
    
    @keyframes popIn {
        0% { transform: scale(0.5); opacity: 0; }
        100% { transform: scale(1); opacity: 1; }
    }

    .grid-item img {
        width: 100%;
        height: 100%;
        object-fit: cover;
    }
    
    /* Tên người tặng */
    .gifter-name {
        position: absolute;
        bottom: 0;
        left: 0;
        width: 100%;
        background: linear-gradient(to top, rgba(0,0,0,0.9), transparent);
        padding: 30px 5px 10px 5px;
        text-align: center;
        font-family: 'Montserrat', sans-serif;
        font-weight: 800;
        font-size: 15px;
        color: #fff;
        text-shadow: 0 2px 5px #000;
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;
    }
    
    /* Nút dừng mờ */
    .stop-btn { position: fixed; bottom: 5px; right: 5px; z-index: 999; opacity: 0.1; transition: 0.3s; }
    .stop-btn:hover { opacity: 1; }
</style>
"""
st.markdown(css, unsafe_allow_html=True)


# ==========================================
# MÀN HÌNH CÀI ĐẶT
# ==========================================
if not st.session_state.is_streaming:
    st.markdown("<h1 style='text-align:center; margin-top:15vh; color:#FF4B4B; font-family:Montserrat;'>🎨 LIVE ART GRID</h1>", unsafe_allow_html=True)
    st.markdown("<p style='text-align:center; color:#888;'>Bàn cờ 20 ô - Tự động đọc tên</p>", unsafe_allow_html=True)
    
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        username = st.text_input("Nhập TikTok Username:", value="@tiktok")
        
        # Nút bấm này đồng thời đóng vai trò "kích hoạt" âm thanh trên iPhone/Safari
        if st.button("▶️ BẮT ĐẦU LIVE", type="primary", use_container_width=True):
            if username:
                st.session_state.scraper = TikTokLiveScraper(username, st.session_state.data_queue)
                st.session_state.scraper.start()
                st.session_state.is_streaming = True
                st.session_state.grid_items = []
                st.session_state.audio_text = "Hệ thống đã sẵn sàng" # Câu chào kích hoạt âm thanh
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
            # Cập nhật câu cần đọc
            st.session_state.audio_text = f"Cảm ơn {ev.get('user')} đã tặng {ev.get('count')} {ev.get('gift_name')}"
            
            # Thêm ảnh vào bàn cờ
            img_b64 = base64.b64encode(ev.get("art_bytes")).decode()
            st.session_state.grid_items.append({
                "name": ev.get("user"),
                "img_b64": img_b64
            })
            
            # Giữ tối đa 20 ô
            if len(st.session_state.grid_items) > 20:
                st.session_state.grid_items.pop(0)

    # 2. TẠO CHUỖI HTML (VIẾT LIỀN 1 DÒNG ĐỂ KHÔNG BỊ LỖI MARKDOWN)
    html_str = "<div class='grid-container'>"
    
    for i in range(20):
        if i < len(st.session_state.grid_items):
            item = st.session_state.grid_items[i]
            html_str += f"<div class='grid-item'><img src='data:image/png;base64,{item['img_b64']}'><div class='gifter-name'>{item['name']}</div></div>"
        else:
            html_str += "<div class='grid-item empty'></div>"
            
    html_str += "</div>"

    # 3. Hiển thị bàn cờ
    st.markdown(html_str, unsafe_allow_html=True)

    # 4. Âm thanh: Sử dụng Javascript (Web Speech API)
    # Đọc ngay lập tức bằng giọng có sẵn của máy, không cần chờ tải file
    if st.session_state.audio_text:
        js_speak = f"""
        <script>
            var msg = new SpeechSynthesisUtterance("{st.session_state.audio_text}");
            msg.lang = 'vi-VN';
            msg.rate = 1.1;
            window.speechSynthesis.speak(msg);
        </script>
        """
        st.markdown(js_speak, unsafe_allow_html=True)
        # Đọc xong thì xóa đi để không đọc lại khi Streamlit refresh
        st.session_state.audio_text = "" 

    # 5. Nút Dừng (làm mờ đi)
    st.markdown('<div class="stop-btn">', unsafe_allow_html=True)
    if st.button("🛑 Stop"):
        st.session_state.is_streaming = False
        st.session_state.grid_items = []
        st.rerun()
    st.markdown('</div>', unsafe_allow_html=True)
