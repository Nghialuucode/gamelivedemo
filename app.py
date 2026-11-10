import queue
import base64
import streamlit as st
from gtts import gTTS
from io import BytesIO
from streamlit_autorefresh import st_autorefresh
from scraper import TikTokLiveScraper

st.set_page_config(page_title="Live Art Stage", layout="wide", initial_sidebar_state="collapsed")

# Khởi tạo State
for key, default in [
    ("data_queue", queue.Queue()),
    ("scraper", None),
    ("gifter", None),
    ("is_streaming", False),
    ("audio_to_play", None),
    ("last_read_text", "")
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
    .block-container {padding: 0 !important;}
    
    /* Khung chứa tranh */
    .art-container {
        display: flex;
        flex-direction: column;
        align-items: center;
        justify-content: center;
        height: 100vh;
        font-family: 'Montserrat', sans-serif;
        background: radial-gradient(circle at center, #1a1f2e 0%, #0d1117 100%);
        position: relative;
        overflow: hidden;
    }
    
    /* Hiệu ứng phát sáng đằng sau */
    .glow {
        position: absolute;
        width: 600px;
        height: 600px;
        background: rgba(255, 75, 75, 0.15);
        border-radius: 50%;
        filter: blur(100px);
        z-index: 0;
        animation: pulse 4s infinite alternate;
    }
    
    @keyframes pulse {
        0% { transform: scale(0.8); opacity: 0.5; }
        100% { transform: scale(1.2); opacity: 1; }
    }

    /* Bức ảnh */
    .art-image {
        width: 500px;
        max-width: 90vw;
        border-radius: 30px;
        border: 4px solid rgba(255, 255, 255, 0.1);
        box-shadow: 0 20px 50px rgba(0,0,0,0.5);
        z-index: 1;
        transition: all 0.5s ease;
    }

    /* Chữ */
    .gifter-name {
        font-size: 48px;
        font-weight: 900;
        color: #fff;
        text-transform: uppercase;
        margin-top: 30px;
        letter-spacing: 2px;
        z-index: 1;
        text-shadow: 0 0 20px rgba(255, 75, 75, 0.8);
    }
    .gift-text {
        font-size: 24px;
        font-weight: 400;
        color: #a0a0a0;
        margin-top: 10px;
        z-index: 1;
    }
    .gift-text span { color: #FF4B4B; font-weight: 800; }
    
    /* Nút dừng */
    .stop-btn-container {
        position: fixed;
        bottom: 20px;
        right: 20px;
        z-index: 999;
        opacity: 0.2;
        transition: opacity 0.3s;
    }
    .stop-btn-container:hover { opacity: 1; }
</style>
"""
st.markdown(css, unsafe_allow_html=True)

# ==========================================
# MÀN HÌNH CÀI ĐẶT
# ==========================================
if not st.session_state.is_streaming:
    st.markdown("<h2 style='text-align:center; margin-top:50px; color:white; font-family:Montserrat;'>🎨 THIẾT LẬP LIVE ART</h2>", unsafe_allow_html=True)
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        username = st.text_input("Nhập TikTok Username:", value="@tiktok")
        if st.button("▶️ BẮT ĐẦU LIVE", type="primary", use_container_width=True):
            if username:
                st.session_state.scraper = TikTokLiveScraper(username, st.session_state.data_queue)
                st.session_state.scraper.start()
                st.session_state.is_streaming = True
                st.session_state.gifter = None
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
            st.session_state.gifter = ev
            
            # Tạo âm thanh bằng gTTS (Tốc độ cực nhanh)
            text = f"Cảm ơn {ev.get('user')} đã tặng {ev.get('count')} {ev.get('gift_name')}"
            if text != st.session_state.last_read_text:
                try:
                    tts = gTTS(text=text, lang='vi', slow=False)
                    fp = BytesIO()
                    tts.write_to_fp(fp)
                    st.session_state.audio_to_play = fp.getvalue()
                    st.session_state.last_read_text = text
                except Exception as e:
                    pass

    # Hiển thị HTML
    if st.session_state.gifter and st.session_state.gifter.get("art_bytes"):
        b64_img = base64.b64encode(st.session_state.gifter["art_bytes"]).decode()
        name = st.session_state.gifter.get("user")
        count = st.session_state.gifter.get("count")
        gift = st.session_state.gifter.get("gift_name")
        
        html = f"""
        <div class="art-container">
            <div class="glow"></div>
            <img src="data:image/png;base64,{b64_img}" class="art-image">
            <div class="gifter-name">{name}</div>
            <div class="gift-text">đã tặng <span>{count} {gift}</span></div>
        </div>
        """
        st.markdown(html, unsafe_allow_html=True)
    else:
        st.markdown("""
        <div class="art-container">
            <div class="glow"></div>
            <h1 style="color:rgba(255,255,255,0.1); font-family:Montserrat; font-size:60px; font-weight:900;">
                ĐANG CHỜ QUÀ...
            </h1>
        </div>
        """, unsafe_allow_html=True)

    # Phát âm thanh (st.audio ở đây sẽ chạy ngầm, không hiện UI)
    if st.session_state.audio_to_play:
        # Dùng CSS ẩn thẻ audio đi (nếu muốn) hoặc để nó hiện nhỏ ở góc
        st.audio(st.session_state.audio_to_play, format="audio/mp3", autoplay=True)
        st.session_state.audio_to_play = None # Phát xong thì xóa

    # Nút dừng (làm mờ đi)
    st.markdown('<div class="stop-btn-container">', unsafe_allow_html=True)
    if st.button("🛑 Dừng Live"):
        st.session_state.is_streaming = False
        st.session_state.gifter = None
        st.rerun()
    st.markdown('</div>', unsafe_allow_html=True)
