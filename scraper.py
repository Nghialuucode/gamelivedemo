import queue
import threading
import logging
import cv2
import numpy as np
from TikTokLive import TikTokLiveClient
from TikTokLive.events import GiftEvent, ConnectEvent, DisconnectEvent

logger = logging.getLogger(__name__)

def create_comic_art(image_bytes: bytes) -> bytes:
    """Nâng cấp ảnh cực nét bằng thuật toán Detail Enhance (Phong cách Comic)."""
    if not image_bytes:
        return None
    try:
        nparr = np.frombuffer(image_bytes, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        if img is None:
            return None

        # 1. Phóng to ảnh 4 lần để bù đắp độ phân giải thấp
        h, w = img.shape[:2]
        img = cv2.resize(img, (w * 4, h * 4), interpolation=cv2.INTER_LANCZOS4)

        # 2. Dùng Detail Enhance để làm nét các đường viền và màu sắc
        comic_img = cv2.detailEnhance(img, sigma_s=10, sigma_r=0.15)

        # 3. Mã hóa lại thành PNG
        _, buffer = cv2.imencode('.png', comic_img)
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

            # Bỏ qua nếu đang trong chuỗi streak
            if event.gift and getattr(event.gift, "streakable", False) and getattr(event, "streaking", False):
                return
            count = getattr(event, "repeat_count", 1) or 1

            art_bytes = None
            try:
                best_avatar = None
                # Ưu tiên ảnh lớn nhất có thể
                for attr in ("avatar_large", "avatar_medium", "avatar_thumb"):
                    av = getattr(event.user, attr, None)
                    if av and getattr(av, "url_list", None):
                        best_avatar = av
                        break
                
                if best_avatar:
                    original_bytes = await self.client.web.fetch_image_data(image=best_avatar)
                    if original_bytes:
                        art_bytes = create_comic_art(original_bytes)
            except Exception as e:
                logger.error(e)

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
