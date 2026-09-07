from urllib import robotparser
from urllib.parse import urlparse
from urllib.request import Request, urlopen


class RobotsChecker:
    """Conservative robots.txt checker with injectable I/O for offline tests."""

    def __init__(self, fetcher=None, user_agent: str = "CrisisAgentResearchBot/0.1"):
        self.fetcher = fetcher or self._fetch
        self.user_agent = user_agent

    @staticmethod
    def _fetch(robots_url: str, timeout: float) -> str:
        request = Request(robots_url, headers={"User-Agent": "CrisisAgentResearchBot/0.1"})
        with urlopen(request, timeout=timeout) as response:  # nosec B310: URL is registry-controlled.
            return response.read(256 * 1024).decode("utf-8", errors="replace")

    def check(self, url: str, timeout: float = 10.0) -> tuple[bool, str | None]:
        parsed = urlparse(url)
        robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
        try:
            content = self.fetcher(robots_url, timeout)
            parser = robotparser.RobotFileParser()
            parser.parse(str(content).splitlines())
            if not parser.can_fetch(self.user_agent, url):
                return False, "robots_denied"
            return True, None
        except Exception as exc:
            return False, f"robots_fetch_failed:{exc.__class__.__name__}"
