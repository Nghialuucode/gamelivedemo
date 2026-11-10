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


def create_artistic_sketch(image_bytes: bytes) -> bytes:
    """Chuyển đổi avatar thành bức ký họa nghệ thuật bằng OpenCV."""
    if not image_bytes:
        return None
    try:
        nparr = np.frombuffer(image_bytes, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        if img is None:
            raise ValueError("Không thể giải mã ảnh.")

        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        inverted_gray = 255 - gray
        blurred = cv2.GaussianBlur(inverted_gray, (21, 21), 0)
        inverted_blurred = 255 - blurred
        sketch = cv2.divide(gray, inverted_blurred, scale=256.0)

        _, buffer = cv2.imencode('.png', sketch)
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
            self.data_queue.put({
                "type": "system",
                "message": f"✅ Đã kết nối tới phòng live của @{event.unique_id}"
            })

        @self.client.on(CommentEvent)
        async def on_comment(event: CommentEvent):
            user_name = event.user.nickname if event.user else "Ẩn danh"
            self.data_queue.put({
                "type": "comment",
                "user": user_name,
                "text": event.comment or ""
            })

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

                if best_avatar is None:
                    avatar_error = "Người dùng không có avatar hợp lệ."
                else:
                    original_bytes = await self.client.web.fetch_image_data(image=best_avatar)
                    if original_bytes is None:
                        avatar_error = "fetch_image_data trả về None."
                    else:
                        avatar_sketch_bytes = create_artistic_sketch(original_bytes)
                        if avatar_sketch_bytes is None:
                            avatar_error = "Không thể tạo hiệu ứng sketch."
            except Exception as e:
                avatar_error = f"Lỗi tải/xử lý ảnh: {e}"
                logger.warning(f"Không thể xử lý avatar cho {user_name}: {e}")

            self.data_queue.put({
                "type": "gift",
                "user": user_name,
                "user_id": getattr(user, "unique_id", "unknown"),
                "gift_name": gift_name,
                "count": count,
                "avatar_sketch_bytes": avatar_sketch_bytes,
                "avatar_error": avatar_error
            })

        @self.client.on(DisconnectEvent)
        async def on_disconnect(event: DisconnectEvent):
            self.data_queue.put({
                "type": "system",
                "message": "⚠️ Đã ngắt kết nối khỏi TikTok Live."
            })

    def _run(self):
        try:
            self.client.run()
        except Exception as e:
            logger.exception("Lỗi trong quá trình chạy scraper:")
            self.data_queue.put({
                "type": "system",
                "message": f"❌ Lỗi scraper: {e}"
            })

    def start(self):
        if self._thread is None or not self._thread.is_alive():
            self._thread = threading.Thread(target=self._run, daemon=True)
            self._thread.start()

    def stop(self):
        logger.info("Yêu cầu dừng scraper.")
