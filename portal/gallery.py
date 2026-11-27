"""Sales gallery: photos of our installations that a salesperson can show a customer.  Everyone logged in can look; directors add and remove."""
import io

from django.contrib import messages
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from .models import GalleryPhoto, GalleryProject

def _is_admin(user):
    """Only the admin (owner) adds, changes or removes gallery photos; everybody else can only look."""
    return bool(user.is_superuser or user.is_staff)

FULL_SIDE, THUMB_SIDE = 1600, 480
MAX_FILES, MAX_BYTES = 15, 20 * 1024 * 1024


def _shrink(raw, side, quality):
    """Turn any phone picture into a smaller JPEG (rotated the right way up)."""
    from PIL import Image, ImageOps
    im = ImageOps.exif_transpose(Image.open(io.BytesIO(raw)))
    im = im.convert("RGB")
    im.thumbnail((side, side))
    out = io.BytesIO()
    im.save(out, "JPEG", quality=quality, optimize=True, progressive=True)
    return out.getvalue()


WM_VERSION = "4"                     # change this number when the logo drawing changes: browsers then fetch the pictures again
_MARKED = {}                         # (photo id, size) -> the picture with the logo on it, so it is drawn once
_MARK_MAX = 120
LOGO = None


def _logo():
    global LOGO
    if LOGO is None:
        import os
        from PIL import Image
        LOGO = Image.open(os.path.join(os.path.dirname(__file__), "static", "portal", "dehlsen_logo_white.png")).convert("RGBA")
    return LOGO


def _watermark(jpeg, share=0.24, top=False):
    """The Dehlsen logo in the bottom-right corner, with a soft shadow so it reads on bright and dark pictures.
    It is drawn when the picture is shown, so the stored original stays clean and the logo can be changed later."""
    from PIL import Image, ImageFilter
    im = Image.open(io.BytesIO(jpeg)).convert("RGBA")
    w, h = im.size
    logo = _logo()
    lw = max(60, int(w * share))
    logo = logo.resize((lw, max(1, int(logo.height * lw / logo.width))), Image.LANCZOS)
    alpha = logo.getchannel("A").point(lambda v: int(v * 0.55))
    logo.putalpha(alpha)
    margin = int(w * 0.03)
    pos = (w - lw - margin, margin if top else h - logo.height - margin)      # grid thumbnails: top-right (the caption is at the bottom)
    shadow = Image.new("RGBA", im.size, (0, 0, 0, 0))
    dark = Image.new("RGBA", logo.size, (0, 0, 0, 255))
    dark.putalpha(logo.getchannel("A").point(lambda v: int(v * 0.35)))
    shadow.paste(dark, (pos[0] + 2, pos[1] + 2), dark)
    shadow = shadow.filter(ImageFilter.GaussianBlur(max(2, lw // 40)))
    im = Image.alpha_composite(im, shadow)
    im.alpha_composite(logo, pos)
    out = io.BytesIO()
    im.convert("RGB").save(out, "JPEG", quality=85, optimize=True, progressive=True)
    return out.getvalue()


def _square(raw, side=640):
    """The grid shows square pictures, so cut the centre square first - then the logo is drawn on what is really shown."""
    from PIL import Image
    im = Image.open(io.BytesIO(raw)).convert("RGB")
    w, h = im.size
    m = min(w, h)
    im = im.crop(((w - m) // 2, (h - m) // 2, (w - m) // 2 + m, (h - m) // 2 + m)).resize((side, side), Image.LANCZOS)
    out = io.BytesIO()
    im.save(out, "JPEG", quality=82, optimize=True, progressive=True)
    return out.getvalue()


def _tidy(project):
    """Keep the cover valid: if the cover photo is gone, the first photo takes its place; a project with no photos is removed."""
    first = project.photos.order_by("id").first()
    if first is None:
        project.delete()
        return
    if project.cover_id is None or not project.photos.filter(pk=project.cover_id).exists():
        project.cover = first
        project.save(update_fields=["cover"])


def home(request):
    kind = request.GET.get("kind") if request.GET.get("kind") in dict(GalleryProject.KINDS) else ""
    q = (request.GET.get("q") or "").strip()
    rows = GalleryProject.objects.all()
    if kind:
        rows = rows.filter(kind=kind)
    if q:
        from django.db.models import Q
        rows = rows.filter(Q(place__icontains=q) | Q(title__icontains=q) | Q(capacity__icontains=q))
    from django.db.models import Prefetch
    rows = rows.prefetch_related(Prefetch("photos", queryset=GalleryPhoto.objects.only("id", "project_id").order_by("id")))
    cards = []
    for r in rows:
        ids = [p.id for p in r.photos.all()]
        if not ids:
            continue
        cover = r.cover_id if r.cover_id in ids else ids[0]
        ids.remove(cover)
        ids.insert(0, cover)                                    # the cover photo is always the first one shown
        cards.append({"p": r, "cover": cover, "ids": ",".join(str(i) for i in ids), "n": len(ids)})
    counts = {k: GalleryProject.objects.filter(kind=k).count() for k, _l in GalleryProject.KINDS}
    chips = [(k, label, counts[k]) for k, label in GalleryProject.KINDS]
    return render(request, "portal/gallery.html", {
        "rows": cards, "kind": kind, "q": q, "kinds": GalleryProject.KINDS, "chips": chips,
        "total": sum(counts.values()), "manage": _is_admin(request.user), "v": WM_VERSION})


def photo(request, pk, size):
    p = get_object_or_404(GalleryPhoto, pk=pk)
    size = "thumb" if size == "thumb" else "full"
    data = _MARKED.get((pk, size))
    if data is None:
        raw = bytes(p.data)
        try:
            data = _watermark(_square(raw), 0.34, top=True) if size == "thumb" else _watermark(raw, 0.24)
        except Exception:                    # never lose the picture because of the logo
            import logging
            logging.getLogger(__name__).exception("Gallery logo could not be drawn on photo %s", pk)
            data = raw
        if len(_MARKED) >= _MARK_MAX:
            _MARKED.pop(next(iter(_MARKED)))
        _MARKED[(pk, size)] = data
    resp = HttpResponse(data, content_type="image/jpeg")
    resp["Cache-Control"] = "private, max-age=3600"
    resp["X-Content-Type-Options"] = "nosniff"
    return resp


def add(request):
    if not _is_admin(request.user):
        messages.warning(request, "Only the admin can add gallery photos.")
        return redirect("gallery")
    projects = GalleryProject.objects.all()
    if request.method == "POST":
        files = request.FILES.getlist("photos")
        P = request.POST
        existing = None
        if P.get("project"):
            existing = GalleryProject.objects.filter(pk=P.get("project") if P.get("project").isdigit() else 0).first()
        if not files:
            messages.warning(request, "Choose at least one photo.")
        elif len(files) > MAX_FILES:
            messages.warning(request, "Add up to %d photos at a time." % MAX_FILES)
        elif P.get("project") and existing is None:
            messages.warning(request, "That project was not found.")
        else:
            if existing is None:
                kind = P.get("kind") if P.get("kind") in dict(GalleryProject.KINDS) else "home"
                existing = GalleryProject.objects.create(
                    title=(P.get("title") or "").strip()[:120], place=(P.get("place") or "").strip()[:100],
                    capacity=(P.get("capacity") or "").strip()[:30], kind=kind)
            made, bad = 0, []
            for f in files:
                try:
                    if f.size > MAX_BYTES:
                        raise ValueError("too big")
                    raw = f.read()
                    ph = GalleryPhoto.objects.create(
                        project=existing, data=_shrink(raw, FULL_SIDE, 82), thumb=_shrink(raw, THUMB_SIDE, 75),
                        source=f.name[:200], uploaded_by=request.user)
                    made += 1
                    if existing.cover_id is None:
                        existing.cover = ph                      # the first photo is the cover until you choose a better one
                        existing.save(update_fields=["cover"])
                except Exception:
                    bad.append(f.name)
            if made:
                messages.success(request, "%d photo%s added to %s." % (made, "" if made == 1 else "s", existing.title or "the project"))
            else:
                _tidy(existing)
            if bad:
                messages.warning(request, "These could not be read as pictures: %s" % ", ".join(bad[:5]))
            if made:
                return redirect("gallery")
    return render(request, "portal/gallery_add.html", {"kinds": GalleryProject.KINDS, "projects": projects,
                                                         "chosen": request.GET.get("project", "")})


@require_POST
def delete(request, pk):
    """Remove a whole project and all its photos."""
    if not _is_admin(request.user):
        raise Http404()
    project = get_object_or_404(GalleryProject, pk=pk)
    ids = list(project.photos.values_list("id", flat=True))
    project.delete()
    for key in [k for k in _MARKED if k[0] in ids]:
        _MARKED.pop(key, None)
    messages.success(request, "Project removed.")
    return redirect("gallery")


@require_POST
def photo_delete(request, pk):
    """Remove one photo of a project (the project goes too if it was the last one)."""
    if not _is_admin(request.user):
        raise Http404()
    ph = get_object_or_404(GalleryPhoto, pk=pk)
    project = ph.project
    ph.delete()
    for key in [k for k in _MARKED if k[0] == pk]:
        _MARKED.pop(key, None)
    _tidy(project)
    messages.success(request, "Photo removed.")
    return redirect("gallery")


@require_POST
def photo_cover(request, pk):
    """Make this photo the one the grid shows for its project."""
    if not _is_admin(request.user):
        raise Http404()
    ph = get_object_or_404(GalleryPhoto, pk=pk)
    ph.project.cover = ph
    ph.project.save(update_fields=["cover"])
    messages.success(request, "That photo is now the cover.")
    return redirect("gallery")
