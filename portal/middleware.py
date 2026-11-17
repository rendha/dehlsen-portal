"""Puts a "Home" button (bottom left) on every page except the home page itself, so a person can always get back to the main dashboard.

It is added to the HTML of the page on its way out, so none of the three apps had to be changed for it.  It is hidden when printing."""
from django.urls import reverse

_BUTTON = (
    '<a href="%s" id="portal-home-btn" title="Back to the home page" aria-label="Home" '
    'style="position:fixed;left:12px;bottom:14px;z-index:2147483000;height:44px;padding:0 16px;border-radius:22px;'
    'background:#E8730C;color:#fff;display:flex;align-items:center;gap:7px;font:700 15px/1 system-ui,sans-serif;'
    'text-decoration:none;box-shadow:0 3px 12px rgba(0,0,0,.28)"><span style="font-size:19px">&#8962;</span> Home</a>'
    '<style>@media print{#portal-home-btn{display:none!important}}</style>'
)
_SKIP = ("/admin/", "/static/", "/login", "/logout", "/offline", "/manifest", "/sw.js", "/health", "/service/health")


class HomeButtonMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        try:
            if (request.path != "/" and not request.path.startswith(_SKIP) and request.user.is_authenticated and response.status_code == 200
                    and not response.streaming and "text/html" in response.get("Content-Type", "")
                    and "attachment" not in response.get("Content-Disposition", "")):
                body = response.content.decode(response.charset or "utf-8")
                marker = body.lower().rfind("</body>")
                if marker != -1 and "portal-home-btn" not in body:
                    body = body[:marker] + (_BUTTON % reverse("home")) + body[marker:]
                    response.content = body.encode(response.charset or "utf-8")
        except Exception:                                   # never let the button break a page
            pass
        return response
