"""Read-only smoke check for this loopback-only development stack."""

import json
from html.parser import HTMLParser
from urllib.request import urlopen


class Assets(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.urls: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        url = values.get("src") if tag == "script" else values.get("href")
        if url and url.startswith("/_next/static/"):
            self.urls.append(url)


def main() -> None:
    for endpoint, expected in [("health", "ok"), ("ready", "ready")]:
        with urlopen(f"http://127.0.0.1:8000/{endpoint}", timeout=10) as response:
            assert response.status == 200
            assert json.loads(response.read()) == {"status": expected}
            print(f"API /{endpoint}: HTTP 200, {expected}")
    with urlopen("http://127.0.0.1:3000", timeout=10) as response:
        assert response.status == 200
        html = response.read().decode()
        assert "Application foundation" in html
    parser = Assets()
    parser.feed(html)
    assert parser.urls, "Frontend must serve its generated assets"
    for asset in parser.urls:
        with urlopen(f"http://127.0.0.1:3000{asset}", timeout=10) as response:
            assert response.status == 200
    print(
        f"Frontend: HTTP 200, expected heading, {len(parser.urls)} static assets served"
    )


if __name__ == "__main__":
    main()
