from urllib.parse import urlparse

from fastapi import Request


def get_request_domain(request: Request) -> str | None:
    """获取请求来源的域名"""
    # 优先从 Referer 获取
    referer = request.headers.get("referer") or request.headers.get("referrer")
    if referer:
        parsed = urlparse(referer)
        return parsed.hostname

    # 其次从 Origin 获取
    origin = request.headers.get("origin")
    if origin:
        parsed = urlparse(origin)
        return parsed.hostname

    # 最后从 Host 获取当前请求域名
    host = request.headers.get("host")
    if host:
        parsed = urlparse(f"https://{host}")
        return parsed.hostname

    return None
