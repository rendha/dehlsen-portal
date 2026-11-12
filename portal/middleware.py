"""Puts a small round "Home" button on the pages of Sales / Project / Service so a person can always get back to the four buttons.

It is added to the HTML of the page on its way out, so none of the three apps had to be changed for it.  It is hidden when printing."""
from django.urls import reverse

_BUTTON = (
    '<a href="%s" id="portal-home-btn" title="Home" aria-label="Home" '
    'style="position:fixed;right:14px;bottom:14px;z-index:2147483000;width:46px;height:46px;border-radius:50%%;'
    'background:#E8730C;color:#fff;display:flex;align-items:center;justify-content:center;font:700 20px/1 system-ui,sans-serif;'
    'text-decoration:none;box-shadow:0 3px 12px rgba(0,0,0,.28)">&#8962;</a>'
    '<style>@media print{#portal-home-btn{display:none!important}}</style>'
)
_AREAS = ("/sales/", "/project/", "/service/")


class HomeButtonMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        try:
            if (request.path.startswith(_AREAS) and request.user.is_authenticated and response.status_code == 200
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
