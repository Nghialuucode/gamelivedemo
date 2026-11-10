import queue
import threading
import logging
from TikTokLive import TikTokLiveClient
from TikTokLive.client.web.web_settings import WebDefaults
from TikTokLive.events import CommentEvent, GiftEvent, ConnectEvent, DisconnectEvent

logger = logging.getLogger(__name__)

# --- CẤU HÌNH API KEY EULERSTREAM ---
# CÁCH 1 (Khuyên dùng cho Streamlit Cloud): Đặt key trong phần "Secrets" với tên SIGN_API_KEY.
# Thư viện TikTokLive sẽ tự động đọc biến môi trường này, không cần dòng code nào ở đây.
#
# CÁCH 2 (Chạy local): Bỏ comment dòng dưới và dán key trực tiếp.
# WebDefaults.tiktok_sign_api_key = "YOUR_EULER_API_KEY_HERE"
# ------------------------------------


class TikTokLiveScraper:
    def __init__(self, unique_id: str, data_queue: queue.Queue):
        """
        Khởi tạo scraper.
        :param unique_id: Tên người dùng TikTok (vd: "@username")
        :param data_queue: Hàng đợi dùng chung để gửi sự kiện đến UI
        """
        self.unique_id = unique_id
        self.data_queue = data_queue
        self.client = TikTokLiveClient(unique_id=unique_id)
        self._thread = None
        self._register_handlers()

    def _register_handlers(self):
        """Đăng ký các hàm xử lý sự kiện từ TikTok Live."""

        @self.client.on(ConnectEvent)
        async def on_connect(event: ConnectEvent):
            logger.info(f"Đã kết nối tới @{event.unique_id} (Room ID: {self.client.room_id})")
            self.data_queue.put({
                "type": "system",
                "message": f"✅ Đã kết nối tới phòng live của @{event.unique_id}"
            })

        @self.client.on(CommentEvent)
        async def on_comment(event: CommentEvent):
            """Xử lý sự kiện bình luận."""
            user_name = event.user.nickname if event.user else "Ẩn danh"
            user_id = event.user.unique_id if event.user else "unknown"
            comment_text = event.comment or ""
            
            self.data_queue.put({
                "type": "comment",
                "user": user_name,
                "user_id": user_id,
                "text": comment_text
            })

        @self.client.on(GiftEvent)
        async def on_gift(event: GiftEvent):
            """Xử lý sự kiện tặng quà, bao gồm cả quà có streak."""
            user_name = event.user.nickname if event.user else "Ẩn danh"
            user_id = event.user.unique_id if event.user else "unknown"
            gift_name = event.gift.name if event.gift else "Quà tặng"
            
            # Xử lý quà có streak: chỉ thông báo khi streak kết thúc để tránh spam
            if event.gift and event.gift.streakable:
                if not event.streaking: # Streak đã kết thúc
                    self.data_queue.put({
                        "type": "gift",
                        "user": user_name,
                        "user_id": user_id,
                        "gift_name": gift_name,
                        "count": event.repeat_count
                    })
            else:
                # Quà không có streak (gửi một lần)
                self.data_queue.put({
                    "type": "gift",
                    "user": user_name,
                    "user_id": user_id,
                    "gift_name": gift_name,
                    "count": 1
                })

        @self.client.on(DisconnectEvent)
        async def on_disconnect(event: DisconnectEvent):
            logger.warning("Đã ngắt kết nối khỏi TikTok Live.")
            self.data_queue.put({
                "type": "system",
                "message": "⚠️ Đã ngắt kết nối khỏi TikTok Live."
            })

    def _run(self):
        """Phương thức chạy trong thread. Gọi client.run() (blocking)."""
        try:
            logger.info(f"Bắt đầu lắng nghe @{self.unique_id}...")
            self.client.run()  # Blocking call, chạy mãi cho đến khi dừng
        except Exception as e:
            logger.exception("Lỗi trong quá trình chạy scraper:")
            self.data_queue.put({
                "type": "system",
                "message": f"❌ Lỗi scraper: {e}"
            })

    def start(self):
        """Khởi chạy scraper trong một thread daemon riêng biệt."""
        if self._thread is None or not self._thread.is_alive():
            self._thread = threading.Thread(target=self._run, daemon=True)
            self._thread.start()
            logger.info("Đã khởi chạy thread scraper.")

    def stop(self):
        """Dừng scraper (nếu cần)."""
        logger.info("Yêu cầu dừng scraper. Thread sẽ tự kết thúc khi ứng dụng đóng.")
