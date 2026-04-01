import asyncio
from playwright.async_api import Page

async def capture_post_interaction(page: Page) -> dict:
    """
    Sets up listeners to capture health metrics (JS errors, network counts) during a user session.
    Returns a mutable dictionary that listeners will update in real-time.
    """
    metrics = {
        "js_errors": 0,
        "network_requests": 0,
        "failed_requests": 0,
        "network_bytes_kb": 0
    }
    
    # 🛑 JS Errors
    page.on("pageerror", lambda err: metrics.__setitem__("js_errors", metrics["js_errors"] + 1))
    
    # 🌐 Network Traffic
    def track_request(request):
        metrics["network_requests"] += 1

    async def track_response(response):
        try:
            headers = await response.all_headers()
            size = int(headers.get("content-length", 0))
            metrics["network_bytes_kb"] += round(size / 1024, 2)
            if response.status >= 400:
                metrics["failed_requests"] += 1
        except:
            pass

    page.on("request", track_request)
    page.on("response", track_response)
    
    return metrics
