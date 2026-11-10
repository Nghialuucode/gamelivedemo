import queue
import threading
import logging
from TikTokLive import TikTokLiveClient
from TikTokLive.client.web.web_settings import WebDefaults
from TikTokLive.events import CommentEvent, GiftEvent, ConnectEvent, DisconnectEvent

logger = logging.getLogger(__name__)

# API Key được cấu hình qua biến môi trường SIGN_API_KEY (trên Cloud) hoặc gán trực tiếp (local)
# WebDefaults.tiktok_sign_api_key = "YOUR_EULER_API_KEY_HERE"

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
            comment_text = event.comment or ""
            self.data_queue.put({
                "type": "comment",
                "user": user_name,
                "text": comment_text
            })

        @self.client.on(GiftEvent)
        async def on_gift(event: GiftEvent):
            if not event.user:
                return

            user_name = event.user.nickname
            gift_name = event.gift.name if event.gift else "Quà tặng"
            count = event.repeat_count if event.gift and event.gift.streakable else 1

            # Chỉ xử lý khi streak kết thúc (đối với quà có streak)
            if event.gift and event.gift.streakable and event.streaking:
                return

            # --- TẢI AVATAR ---
            avatar_bytes = None
            try:
                # Tải ảnh đại diện cỡ trung bình
                avatar_bytes = await self.client.web.fetch_image_data(
                    image=event.user.avatar_thumb
                )
            except Exception as e:
                logger.warning(f"Không thể tải avatar cho {user_name}: {e}")

            # Gửi sự kiện kèm dữ liệu ảnh (nếu có) đến giao diện
            self.data_queue.put({
                "type": "gift",
                "user": user_name,
                "user_id": event.user.unique_id,
                "gift_name": gift_name,
                "count": count,
                "avatar_bytes": avatar_bytes  # Dữ liệu nhị phân của ảnh
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
            self.data_queue.put({"type": "system", "message": f"❌ Lỗi scraper: {e}"})

    def start(self):
        if self._thread is None or not self._thread.is_alive():
            self._thread = threading.Thread(target=self._run, daemon=True)
            self._thread.start()

    def stop(self):
        logger.info("Yêu cầu dừng scraper.")
