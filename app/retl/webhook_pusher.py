import json
import time
from typing import Dict, Any, Optional
from urllib.parse import urlparse
import urllib.request

_WECOM_PLATFORMS = {"wecom", "wechat", "weixin", "qywx", "wxwork", "wechat_work"}


def _validate_webhook_url(webhook_url: str) -> str:
    if not isinstance(webhook_url, str) or not webhook_url.strip():
        raise ValueError("webhook_url must be a non-empty http(s) URL")
    parsed = urlparse(webhook_url.strip())
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise ValueError(f"webhook_url must be an http(s) URL, got {webhook_url!r}")
    return webhook_url.strip()


class WebhookPusher:
    @staticmethod
    def build_payload(
        title: str,
        message: str,
        platform: str = "generic",
        extra_metrics: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Platform body for Feishu, DingTalk, Slack, WeCom, or a generic webhook."""
        platform_key = (platform or "generic").strip().lower()
        if platform_key == "feishu":
            content_elements = [{"tag": "text", "text": message + "\n\n"}]
            if extra_metrics:
                for key, value in extra_metrics.items():
                    content_elements.append({"tag": "text", "text": f"• {key}: {value}\n"})
            return {
                "msg_type": "post",
                "content": {
                    "post": {
                        "zh_cn": {
                            "title": title,
                            "content": [content_elements]
                        }
                    }
                }
            }
        if platform_key == "dingtalk":
            text = f"### {title}\n\n{message}\n\n"
            if extra_metrics:
                for key, value in extra_metrics.items():
                    text += f"- **{key}**: {value}\n"
            return {
                "msgtype": "markdown",
                "markdown": {"title": title, "text": text}
            }
        if platform_key == "slack":
            text = f"*{title}*\n{message}"
            if extra_metrics:
                for key, value in extra_metrics.items():
                    text += f"\n• {key}: {value}"
            return {"text": text}
        if platform_key in _WECOM_PLATFORMS:
            content = f"### {title}\n{message}"
            if extra_metrics:
                for key, value in extra_metrics.items():
                    content += f"\n> {key}: {value}"
            return {"msgtype": "markdown", "markdown": {"content": content}}
        return {
            "title": title,
            "message": message,
            "metrics": extra_metrics or {}
        }

    @staticmethod
    def send_alert(
        webhook_url: str,
        title: str,
        message: str,
        platform: str = "generic", # feishu, dingtalk, slack, wecom, generic
        extra_metrics: Optional[Dict[str, Any]] = None,
        max_retries: int = 3
    ) -> Dict[str, Any]:
        """
        Production Webhook Pusher with Exponential Backoff Retries.
        """
        payload = WebhookPusher.build_payload(title, message, platform, extra_metrics)
        webhook_url = _validate_webhook_url(webhook_url)
        if isinstance(max_retries, bool) or not isinstance(max_retries, int) or max_retries < 1:
            raise ValueError(f"max_retries must be a positive integer, got {max_retries!r}")

        last_error = None
        for attempt in range(1, max_retries + 1):
            try:
                data_bytes = json.dumps(payload, default=str).encode("utf-8")
                req = urllib.request.Request(
                    webhook_url,
                    data=data_bytes,
                    headers={"Content-Type": "application/json", "User-Agent": "MDS-DataAgent/1.0"}
                )
                with urllib.request.urlopen(req, timeout=5) as response:
                    status_code = response.getcode()
                    resp_text = response.read().decode("utf-8")
                    return {
                        "status": "SUCCESS",
                        "http_code": status_code,
                        "attempts": attempt,
                        "response": resp_text
                    }
            except Exception as e:
                last_error = str(e)
                if attempt < max_retries:
                    time.sleep(0.5 * (2 ** (attempt - 1))) # Exponential backoff: 0.5s, 1s, 2s

        return {
            "status": "FAILED",
            "attempts": max_retries,
            "error": last_error,
            "simulated_payload": payload
        }
