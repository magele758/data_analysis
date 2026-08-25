import json
import time
from typing import Dict, Any, Optional
import urllib.request
import urllib.error

class WebhookPusher:
    @staticmethod
    def send_alert(
        webhook_url: str,
        title: str,
        message: str,
        platform: str = "generic", # feishu, dingtalk, slack, generic
        extra_metrics: Optional[Dict[str, Any]] = None,
        max_retries: int = 3
    ) -> Dict[str, Any]:
        """
        Production Webhook Pusher with Exponential Backoff Retries.
        """
        payload = {}

        if platform == "feishu":
            content_elements = [{"tag": "text", "text": message + "\n\n"}]
            if extra_metrics:
                for k, v in extra_metrics.items():
                    content_elements.append({"tag": "text", "text": f"• {k}: {v}\n"})
            
            payload = {
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
        elif platform == "dingtalk":
            text = f"### {title}\n\n{message}\n\n"
            if extra_metrics:
                for k, v in extra_metrics.items():
                    text += f"- **{k}**: {v}\n"
            payload = {
                "msgtype": "markdown",
                "markdown": {"title": title, "text": text}
            }
        else:
            payload = {
                "title": title,
                "message": message,
                "metrics": extra_metrics or {}
            }

        last_error = None
        for attempt in range(1, max_retries + 1):
            try:
                data_bytes = json.dumps(payload).encode("utf-8")
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
