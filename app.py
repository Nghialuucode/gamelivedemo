import queue
import base64
import streamlit as st
from io import BytesIO
from gtts import gTTS
from streamlit_autorefresh import st_autorefresh
from scraper import TikTokLiveScraper

# Cấu hình trang
st.set_page_config(page_title="Live Art Grid", layout="wide", initial_sidebar_state="collapsed")

# Khởi tạo State
for key, default in [
    ("data_queue", queue.Queue()),
    ("scraper", None),
    ("grid_items", []), # Chứa tối đa 20 dicts {name, img_b64, audio_b64}
    ("is_streaming", False),
    ("new_gift_trigger", 0) # Cứ có quà mới, biến này tăng lên 1 để reset iframe audio
]:
    if key not in st.session_state:
        st.session_state[key] = default

# CSS TOÀN CỤC (Ẩn Streamlit UI, tạo Grid)
css = """
<style>
    @import url('https://fonts.googleapis.com/css2?family=Montserrat:wght@700;900&display=swap');
    
    /* Ẩn mọi thứ của Streamlit */
    #MainMenu, header, footer {visibility: hidden;}
    .stApp {background-color: #0a0a0c;}
    .block-container {padding: 0 !important; max-width: 100% !important;}
    
    /* Bàn cờ 5x4 */
    .grid-container {
        display: grid;
        grid-template-columns: repeat(5, 1fr); /* 5 cột */
        grid-template-rows: repeat(4, 1fr);    /* 4 hàng */
        gap: 10px;
        padding: 10px;
        height: 100vh;
        width: 100vw;
        box-sizing: border-box;
    }
    
    /* Từng ô */
    .grid-item {
        position: relative;
        border-radius: 12px;
        overflow: hidden;
        background: #1a1a24;
        border: 1px solid rgba(255, 75, 75, 0.3);
        box-shadow: 0 0 15px rgba(255, 75, 75, 0.1);
        animation: popIn 0.5s cubic-bezier(0.175, 0.885, 0.32, 1.275) forwards;
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
        padding: 20px 5px 5px 5px;
        text-align: center;
        font-family: 'Montserrat', sans-serif;
        font-weight: 700;
        font-size: 14px;
        color: #fff;
        text-shadow: 0 2px 4px #000;
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;
    }
    
    /* Nút dừng mờ ở góc */
    .stop-btn-container { position: fixed; bottom: 5px; right: 5px; z-index: 999; opacity: 0.1; }
    .stop-btn-container:hover { opacity: 1; }
</style>
"""
st.markdown(css, unsafe_allow_html=True)

# Hàm tạo âm thanh Base64
def get_audio_b64(text):
    try:
        tts = gTTS(text=text, lang='vi', slow=False)
        fp = BytesIO()
        tts.write_to_fp(fp)
        return base64.b64encode(fp.getvalue()).decode('utf-8')
    except Exception:
        return ""

# ==========================================
# MÀN HÌNH CÀI ĐẶT
# ==========================================
if not st.session_state.is_streaming:
    st.markdown("<h1 style='text-align:center; margin-top:15vh; color:#FF4B4B; font-family:Montserrat;'>🎨 LIVE ART GRID</h1>", unsafe_allow_html=True)
    
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        username = st.text_input("Nhập TikTok Username:", value="@tiktok")
        if st.button("▶️ BẮT ĐẦU LIVE", type="primary", use_container_width=True):
            if username:
                st.session_state.scraper = TikTokLiveScraper(username, st.session_state.data_queue)
                st.session_state.scraper.start()
                st.session_state.is_streaming = True
                st.session_state.grid_items = []
                st.rerun()

# ==========================================
# MÀN HÌNH LIVE
# ==========================================
else:
    # Tự động load lại 0.5s/lần để bắt sự kiện
    st_autorefresh(interval=500, key="refresh")

    # 1. Xử lý sự kiện từ Queue
    audio_to_play = ""
    while not st.session_state.data_queue.empty():
        ev = st.session_state.data_queue.get()
        if ev.get("type") == "gift":
            # Tạo âm thanh
            text = f"Cảm ơn {ev.get('user')} đã tặng {ev.get('count')} {ev.get('gift_name')}"
            audio_to_play = get_audio_b64(text)
            
            # Thêm vào bàn cờ
            img_b64 = base64.b64encode(ev.get("art_bytes")).decode()
            st.session_state.grid_items.append({
                "name": ev.get("user"),
                "img_b64": img_b64
            })
            
            # Nếu đầy 20 ô, xóa ô đầu tiên (tạo hiệu ứng trượt)
            if len(st.session_state.grid_items) > 20:
                st.session_state.grid_items.pop(0)

    # 2. Render giao diện HTML
    html = f"""
    <audio autoplay="true" src="data:audio/mp3;base64,{audio_to_play}"></audio>
    <div class="grid-container">
    """
    
    # Vẽ 20 ô
    for i in range(20):
        if i < len(st.session_state.grid_items):
            item = st.session_state.grid_items[i]
            html += f"""
            <div class="grid-item">
                <img src="data:image/png;base64,{item['img_b64']}">
                <div class="gifter-name">{item['name']}</div>
            </div>
            """
        else:
            # Ô trống
            html += '<div class="grid-item" style="opacity: 0.2; border: 1px dashed #333;"></div>'
            
    html += "</div>"
    
    # 3. Hiển thị toàn bộ (Dùng st.markdown để chạy HTML/CSS trực tiếp không qua iframe)
    st.markdown(html, unsafe_allow_html=True)

    # Nút dừng (Chỉ hiện khi hover)
    st.markdown('<div class="stop-btn-container">', unsafe_allow_html=True)
    if st.button("🛑 Stop"):
        st.session_state.is_streaming = False
        st.session_state.grid_items = []
        st.rerun()
    st.markdown('</div>', unsafe_allow_html=True)
