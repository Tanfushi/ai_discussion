import json
import time
from typing import Any
import requests
from tenacity import retry, stop_after_attempt, wait_fixed

from app.config import get_settings


class FeishuClient:
    def __init__(self) -> None:
        self.settings = get_settings()
        self._token = ""
        self._expires_at = 0

    def _get_tenant_token(self) -> str:
        now = int(time.time())
        if self._token and now < self._expires_at - 60:
            return self._token

        resp = requests.post(
            "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal",
            json={
                "app_id": self.settings.feishu_app_id,
                "app_secret": self.settings.feishu_app_secret,
            },
            timeout=20,
        )
        resp.raise_for_status()
        payload = resp.json()
        if payload.get("code") != 0:
            raise RuntimeError(f"Failed to get feishu token: {payload}")
        self._token = payload["tenant_access_token"]
        self._expires_at = now + int(payload.get("expire", 7200))
        return self._token

    @retry(stop=stop_after_attempt(3), wait=wait_fixed(1))
    def send_text(self, receive_id: str, text: str, receive_id_type: str = "chat_id") -> str:
        token = self._get_tenant_token()
        resp = requests.post(
            f"https://open.feishu.cn/open-apis/im/v1/messages?receive_id_type={receive_id_type}",
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
            json={
                "receive_id": receive_id,
                "msg_type": "text",
                "content": json.dumps({"text": text}, ensure_ascii=False),
            },
            timeout=20,
        )
        resp.raise_for_status()
        payload = resp.json()
        if payload.get("code") != 0:
            raise RuntimeError(f"Send text failed: {payload}")
        return payload["data"]["message_id"]

    @retry(stop=stop_after_attempt(3), wait=wait_fixed(1))
    def send_card(
        self, receive_id: str, card: dict[str, Any], receive_id_type: str = "chat_id"
    ) -> str:
        token = self._get_tenant_token()
        resp = requests.post(
            f"https://open.feishu.cn/open-apis/im/v1/messages?receive_id_type={receive_id_type}",
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
            json={
                "receive_id": receive_id,
                "msg_type": "interactive",
                "content": json.dumps(card, ensure_ascii=False),
            },
            timeout=20,
        )
        resp.raise_for_status()
        payload = resp.json()
        if payload.get("code") != 0:
            raise RuntimeError(f"Send card failed: {payload}")
        return payload["data"]["message_id"]

    @retry(stop=stop_after_attempt(3), wait=wait_fixed(1))
    def patch_message_card(self, message_id: str, card: dict[str, Any]) -> None:
        token = self._get_tenant_token()
        resp = requests.patch(
            f"https://open.feishu.cn/open-apis/im/v1/messages/{message_id}",
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
            json={"content": json.dumps(card, ensure_ascii=False)},
            timeout=20,
        )
        resp.raise_for_status()
        payload = resp.json()
        if payload.get("code") != 0:
            raise RuntimeError(f"Patch card failed: {payload}")


feishu_client = FeishuClient()
