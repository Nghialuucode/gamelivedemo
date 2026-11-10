import queue
import threading
import logging
import cv2
import numpy as np
from TikTokLive import TikTokLiveClient
from TikTokLive.client.web.web_settings import WebDefaults
from TikTokLive.events import CommentEvent, GiftEvent, ConnectEvent, DisconnectEvent

logger = logging.getLogger(__name__)

# WebDefaults.tiktok_sign_api_key = "YOUR_EULER_API_KEY_HERE"

def create_beautiful_sketch(image_bytes: bytes) -> bytes:
    """Nâng cấp chất lượng ảnh và tạo hiệu ứng ký họa mềm mại."""
    if not image_bytes:
        return None
    try:
        nparr = np.frombuffer(image_bytes, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        if img is None:
            return None

        # 1. Upscale ảnh lên gấp 3 lần để chống vỡ hạt (nếu ảnh gốc nhỏ)
        h, w = img.shape[:2]
        if w < 500:
            img = cv2.resize(img, (w * 3, h * 3), interpolation=cv2.INTER_LANCZOS4)

        # 2. Dùng thuật toán pencilSketch tích hợp sẵn của OpenCV (mịn hơn nhiều)
        # dst_gray là ảnh trắng đen nét vẽ chì, dst_color là ảnh màu
        dst_gray, dst_color = cv2.pencilSketch(
            img, sigma_s=60, sigma_r=0.07, shade_factor=0.05
        )
        
        # Bạn có thể chọn trả về dst_gray (đen trắng) hoặc dst_color (có màu)
        # Ở đây mình chọn ảnh đen trắng vì nó giống tranh vẽ nhất
        final_img = dst_gray 

        # 3. Mã hóa lại thành PNG
        _, buffer = cv2.imencode('.png', final_img)
        return buffer.tobytes()
    except Exception as e:
        logger.error(f"Lỗi tạo sketch: {e}")
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
            self.data_queue.put({"type": "system", "message": f"✅ Đã kết nối @{event.unique_id}"})

        @self.client.on(CommentEvent)
        async def on_comment(event: CommentEvent):
            user_name = event.user.nickname if event.user else "Ẩn danh"
            self.data_queue.put({"type": "comment", "user": user_name, "text": event.comment or ""})

        @self.client.on(GiftEvent)
        async def on_gift(event: GiftEvent):
            if not event.user:
                return

            user_name = event.user.nickname
            gift_name = event.gift.name if event.gift else "Quà tặng"

            if event.gift and getattr(event.gift, "streakable", False):
                if getattr(event, "streaking", False):
                    return
                count = getattr(event, "repeat_count", 1) or 1
            else:
                count = 1

            avatar_sketch_bytes = None
            avatar_error = None
            user = event.user

            try:
                best_avatar = None
                for attr in ("avatar_large", "avatar_medium", "avatar_thumb"):
                    av = getattr(user, attr, None)
                    if av is not None and getattr(av, "url_list", None):
                        best_avatar = av
                        break

                if best_avatar:
                    original_bytes = await self.client.web.fetch_image_data(image=best_avatar)
                    if original_bytes:
                        avatar_sketch_bytes = create_beautiful_sketch(original_bytes)
            except Exception as e:
                avatar_error = str(e)

            self.data_queue.put({
                "type": "gift",
                "user": user_name,
                "gift_name": gift_name,
                "count": count,
                "avatar_sketch_bytes": avatar_sketch_bytes,
                "avatar_error": avatar_error
            })

        @self.client.on(DisconnectEvent)
        async def on_disconnect(event: DisconnectEvent):
            self.data_queue.put({"type": "system", "message": "⚠️ Đã ngắt kết nối."})

    def _run(self):
        try:
            self.client.run()
        except Exception as e:
            self.data_queue.put({"type": "system", "message": f"❌ Lỗi: {e}"})

    def start(self):
        if self._thread is None or not self._thread.is_alive():
            self._thread = threading.Thread(target=self._run, daemon=True)
            self._thread.start()

    def stop(self):
        pass
