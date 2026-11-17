import time
from urllib.parse import urlsplit
from .robots import Robots
import httpx

class AccessError(RuntimeError):
    pass

class Client:
    def __init__(self, host, config):
        self.host, self.config = host, config
        self.client = httpx.Client(timeout=config["timeout"], follow_redirects=False,
                                   headers={"User-Agent": config["user_agent"]})
        self.last = 0.0
        self.robots = None
    def close(self):
        self.client.close()
    def raw(self, url):
        if urlsplit(url).netloc != self.host or urlsplit(url).scheme != "https":
            raise AccessError("Unexpected URL or redirect; request refused")
        for attempt in range(self.config["retries"]):
            time.sleep(max(0, self.config["interval_seconds"] - (time.monotonic()-self.last)))
            self.last = time.monotonic()
            try:
                r = self.client.get(url)
                if r.status_code in (401, 403, 429):
                    raise AccessError(f"HTTP {r.status_code}; access restricted, stopped")
                if r.status_code >= 500:
                    raise httpx.TransportError("Transient server error")
                if r.is_redirect:
                    raise AccessError("Redirect encountered; review destination before enabling")
                r.raise_for_status()
                return r.text
            except (httpx.TransportError, httpx.TimeoutException):
                if attempt + 1 == self.config["retries"]:
                    raise AccessError("Network failure after bounded retries") from None
                time.sleep(2 ** attempt)
    def get(self, url):
        if self.robots is None:
            text = self.raw(f"https://{self.host}/robots.txt")
            if "user-agent:" not in text.lower():
                raise AccessError("robots.txt unreadable; stopped conservatively")
            self.robots = Robots(text, self.config["user_agent"])
            delay = self.robots.delay
            if delay:
                self.config = dict(self.config, interval_seconds=max(delay, self.config["interval_seconds"]))
        if not self.robots.allows(url):
            raise AccessError("robots.txt disallows URL")
        text = self.raw(url)
        if any(s in text.lower() for s in ("verify you are human", "cf-chl-", "captcha challenge")):
            raise AccessError("Access challenge detected; stopped")
        return text
