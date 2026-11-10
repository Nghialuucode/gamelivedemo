import queue
import threading
import logging
import cv2
import numpy as np
from TikTokLive import TikTokLiveClient
from TikTokLive.events import GiftEvent, ConnectEvent, DisconnectEvent

logger = logging.getLogger(__name__)

def create_square_art(image_bytes: bytes) -> bytes:
    if not image_bytes:
        return None
    try:
        nparr = np.frombuffer(image_bytes, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        if img is None:
            return None

        h, w = img.shape[:2]

        # BỘ LỌC 1: Nếu ảnh quá nhỏ (dưới 50px) => Đây là ảnh mặc định của TikTok, bỏ qua
        if w < 50 or h < 50:
            return None

        # BỘ LỌC 2: Phát hiện ảnh xám mặc định của TikTok (thường rất ít điểm ảnh hoặc trùng màu)
        if np.std(img) < 10: # Độ lệch chuẩn màu thấp => ảnh đơn sắc
            return None

        # 1. Cắt ảnh vuông (Center Crop)
        min_dim = min(h, w)
        top = (h - min_dim) // 2
        left = (w - min_dim) // 2
        img = img[top:top+min_dim, left:left+min_dim]

        # 2. Phóng to lên 400x400 (Chống vỡ hình)
        img = cv2.resize(img, (400, 400), interpolation=cv2.INTER_LANCZOS4)

        # 3. Dùng bộ lọc Stylization tạo hiệu ứng tranh vẽ Anime
        art_img = cv2.stylization(img, sigma_s=60, sigma_r=0.07)

        # 4. Mã hóa thành PNG
        _, buffer = cv2.imencode('.png', art_img)
        return buffer.tobytes()
    except Exception as e:
        logger.error(f"Lỗi tạo ảnh: {e}")
        return None

class TikTokLiveScraper:
    def __init__(self, unique_id: str, data_queue: queue.Queue):
        self.unique_id = unique_id
        self.data_queue = data_queue
        self.client = TikTokLiveClient(unique_id=unique_id)
        self._thread = None
        self._register_handlers()

    def _register_handlers(self):
        @self.client.on(ConnectEvent)
        async def on_connect(event: ConnectEvent):
            self.data_queue.put({"type": "system", "message": "Đã kết nối"})

        @self.client.on(GiftEvent)
        async def on_gift(event: GiftEvent):
            if not event.user: return
            user_name = event.user.nickname
            gift_name = event.gift.name if event.gift else "Quà"

            # Bỏ qua nếu đang trong chuỗi streak (chỉ hiện khi kết thúc)
            if event.gift and getattr(event.gift, "streakable", False) and getattr(event, "streaking", False):
                return
            count = getattr(event, "repeat_count", 1) or 1

            art_bytes = None
            try:
                best_avatar = None
                for attr in ("avatar_large", "avatar_medium", "avatar_thumb"):
                    av = getattr(event.user, attr, None)
                    if av and getattr(av, "url_list", None):
                        best_avatar = av
                        break
                
                if best_avatar:
                    original_bytes = await self.client.web.fetch_image_data(image=best_avatar)
                    if original_bytes:
                        art_bytes = create_square_art(original_bytes)
            except Exception as e:
                logger.error(e)

            if art_bytes:
                self.data_queue.put({
                    "type": "gift",
                    "user": user_name,
                    "gift_name": gift_name,
                    "count": count,
                    "art_bytes": art_bytes
                })

        @self.client.on(DisconnectEvent)
        async def on_disconnect(event: DisconnectEvent):
            self.data_queue.put({"type": "system", "message": "Đã ngắt kết nối"})

    def _run(self):
        try:
            self.client.run()
        except Exception as e:
            self.data_queue.put({"type": "system", "message": f"Lỗi: {e}"})

    def start(self):
        if self._thread is None or not self._thread.is_alive():
            self._thread = threading.Thread(target=self._run, daemon=True)
            self._thread.start()
            
    def stop(self):
        pass
