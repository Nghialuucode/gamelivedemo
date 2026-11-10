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

            # --- TẢI AVATAR (ĐÃ SỬA LỖI) ---
            avatar_bytes = None
            avatar_error = None
            
            # 1. Kiểm tra dữ liệu ảnh có tồn tại và có URL hợp lệ không
            user = event.user
            if user is None:
                avatar_error = "Không có dữ liệu người dùng."
            elif user.avatar_thumb is None:
                avatar_error = "Người dùng không có avatar_thumb."
            elif not hasattr(user.avatar_thumb, 'url_list') or not user.avatar_thumb.url_list:
                avatar_error = "avatar_thumb không có url_list."
            else:
                # 2. Chỉ tải ảnh khi dữ liệu đã hợp lệ
                try:
                    avatar_bytes = await self.client.web.fetch_image_data(
                        image=user.avatar_thumb
                    )
                    if avatar_bytes is None:
                        avatar_error = "fetch_image_data trả về None."
                except Exception as e:
                    avatar_error = f"Lỗi khi tải ảnh: {e}"
                    logger.warning(f"Không thể tải avatar cho {user_name}: {e}")

            # Gửi sự kiện kèm dữ liệu ảnh và thông tin lỗi (nếu có)
            self.data_queue.put({
                "type": "gift",
                "user": user_name,
                "user_id": user.unique_id,
                "gift_name": gift_name,
                "count": count,
                "avatar_bytes": avatar_bytes,
                "avatar_error": avatar_error  # Gửi lỗi để hiển thị lên UI
            })
