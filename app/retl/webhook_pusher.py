import json
from typing import Dict, Any, Optional
import urllib.request

class WebhookPusher:
    @staticmethod
    def send_alert(
        webhook_url: str,
        title: str,
        message: str,
        platform: str = "generic", # feishu, dingtalk, slack, generic
        extra_metrics: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Send operational alerts or insight summaries to Feishu, DingTalk, Slack, or generic webhooks.
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

        try:
            data_bytes = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(
                webhook_url,
                data=data_bytes,
                headers={"Content-Type": "application/json"}
            )
            with urllib.request.urlopen(req, timeout=5) as response:
                status_code = response.getcode()
                resp_text = response.read().decode("utf-8")
                return {"status": "SUCCESS", "http_code": status_code, "response": resp_text}
        except Exception as e:
            return {"status": "FAILED", "error": str(e), "simulated_payload": payload}
