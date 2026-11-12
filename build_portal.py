"""
build_portal.py  -  puts your three websites together into this ONE project.   Run it once:

    py build_portal.py

It COPIES (never changes or deletes your originals) these folders, which must be next to this one on the Desktop:
    quotation_pwa        ->  quotations/      (Sales)
    materials_site       ->  store/           (Project)
    SolarCleaningManager ->  cleaning/, templates/, static/   (Service)
and then makes the small changes that let the three live together (shared login, no clashing names, links under /sales/ /project/ /service/).
Run it again at any time: it starts from fresh copies each time, so it is safe.   Use  --check  to only test, without copying.

Options:  --quotation PATH  --materials PATH  --cleaning PATH   (when a folder is somewhere else)
"""
import argparse
import re
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
IGNORE = shutil.ignore_patterns("__pycache__", "*.pyc", "db.sqlite3", "venv", ".venv", ".git", "*.log")
problems = []
changes = []


def note(text):
    print("   ", text)
    changes.append(text)


def warn(text):
    print("  !!", text)
    problems.append(text)


def read(path):
    return path.read_text(encoding="utf-8")


def write(path, text):
    path.write_text(text, encoding="utf-8", newline="")


def replace_in(path, old, new, label, count=None):
    """Plain text replace; complains when the old text is not there (the file changed since this script was written)."""
    if not path.exists():
        warn("%s: file not found (%s)" % (label, path.relative_to(HERE)))
        return
    text = read(path)
    found = text.count(old)
    if not found or (count is not None and found != count):
        warn("%s: expected %s place(s) in %s, found %s" % (label, count if count is not None else "1+", path.relative_to(HERE), found))
        if not found:
            return
    write(path, text.replace(old, new))
    note("%s (%s)" % (label, path.relative_to(HERE)))


def regex_in_tree(root, pattern, repl, label, suffixes=(".py", ".html", ".js")):
    total = 0
    for path in sorted(root.rglob("*")):
        if path.is_file() and path.suffix in suffixes and "__pycache__" not in path.parts:
            text = read(path)
            new, n = re.subn(pattern, repl, text)
            if n:
                write(path, new)
                total += n
    if total:
        note("%s: %d place(s)" % (label, total))
    else:
        print("    (nothing to change for: %s)" % label)
    return total


def remove_path_entry(path, route):
    """Deletes the  path("<route>", ...)  line(s) from a urls.py, however many lines or brackets it has."""
    text = read(path)
    for quote in ('"', "'"):
        start = text.find("path(%s%s%s" % (quote, route, quote))
        if start != -1:
            break
    else:
        warn("%s: no path for %r found" % (path.relative_to(HERE), route))
        return
    depth, i = 0, start
    while i < len(text):
        if text[i] == "(":
            depth += 1
        elif text[i] == ")":
            depth -= 1
            if depth == 0:
                break
        i += 1
    end = i + 1
    if end < len(text) and text[end] == ",":
        end += 1
    while end < len(text) and text[end] in " \t":
        end += 1
    if text[end:end + 2] == "\r\n":
        end += 2
    elif text[end:end + 1] == "\n":
        end += 1
    line_start = text.rfind("\n", 0, start) + 1          # also take the indentation before it
    write(path, text[:line_start] + text[end:])
    note("%s: removed the %r page (the one site has its own)" % (path.relative_to(HERE), route))


def copy(src, dst, what):
    if not src.is_dir():
        warn("%s: folder not found: %s" % (what, src))
        return False
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(src, dst, ignore=IGNORE)
    note("copied %s" % what)
    return True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--quotation", default=str(HERE.parent / "quotation_pwa"))
    ap.add_argument("--materials", default=str(HERE.parent / "materials_site"))
    ap.add_argument("--cleaning", default=str(HERE.parent / "SolarCleaningManager"))
    ap.add_argument("--check", action="store_true", help="only look, copy nothing")
    args = ap.parse_args()
    q, m, c = Path(args.quotation), Path(args.materials), Path(args.cleaning)

    missing = [str(p) for p in (q / "quotations", m / "store", c / "cleaning", c / "templates") if not p.is_dir()]
    if missing:
        print("These folders were not found:\n  " + "\n  ".join(missing))
        print("Put this folder next to quotation_pwa, materials_site and SolarCleaningManager, or give the paths with --quotation / --materials / --cleaning.")
        return 1
    print("The three websites were found.")
    if args.check:
        return 0

    print("\n1. Copying")
    copy(q / "quotations", HERE / "quotations", "Sales (quotations)")
    copy(m / "store", HERE / "store", "Project (store)")
    copy(c / "cleaning", HERE / "cleaning", "Service (cleaning)")
    copy(c / "templates", HERE / "templates", "Service pages (templates)")
    if (c / "static").is_dir():
        copy(c / "static", HERE / "static", "Service static files")
    else:
        (HERE / "static").mkdir(exist_ok=True)

    print("\n2. Sales (quotations)")
    qu = HERE / "quotations"
    for route in ("login/", "logout/", "manifest.webmanifest", "sw.js", "offline/"):
        remove_path_entry(qu / "urls.py", route)

    print("\n3. Project (store)")
    st = HERE / "store"
    for route in ("manifest.webmanifest", "sw.js", "offline/", "login/", "logout/"):
        remove_path_entry(st / "urls.py", route)
    replace_in(st / "urls.py", 'name="home"', 'name="store_home"', "renamed the Project home page", 1)
    replace_in(st / "templates" / "store" / "base.html", "{% url 'home' %}", "{% url 'store_home' %}", "Project top bar link")
    # the Project app used to ask the quotation website over the internet; now it asks the Sales app directly
    write(st / "services.py", SERVICES_PY)
    note("store/services.py: reads quotations directly from the Sales app (no API address or key needed)")

    print("\n4. Service (cleaning)")
    cl = HERE / "cleaning"
    for route in ("login/", "logout/", "sw.js"):
        remove_path_entry(cl / "urls.py", route)
    replace_in(cl / "urls.py", "name='home'", "name='cleaning_home'", "renamed the Service home page", 1)
    replace_in(HERE / "templates" / "base.html", "{% url 'home' %}", "{% url 'cleaning_home' %}", "Service top bar link")
    replace_in(HERE / "templates" / "base.html", "{% static 'manifest.json' %}", "/manifest.webmanifest", "Service uses the site's one manifest")
    # the Service pages call addresses written out in full: they now live under /service/
    for pattern, repl, label in (
        (r"(?<![\w/])/(schedule/)", r"/service/\1", "links to /schedule/"),
        (r"(?<![\w/])/(my-jobs/)", r"/service/\1", "links to /my-jobs/"),
        (r"(?<![\w/])/(api/customer/)", r"/service/\1", "links to /api/customer/"),
        (r"(?<![\w/])/(api/schedule/)", r"/service/\1", "links to /api/schedule/"),
    ):
        regex_in_tree(HERE / "templates", r"(?<=[`'\"])" + pattern, repl, "Service pages: " + label)
        regex_in_tree(cl, r"(?<=[`'\"])" + pattern, repl, "Service code: " + label)
    regex_in_tree(HERE / "static", r"(?<=[`'\"])(?<![\w/])/(schedule/|my-jobs/|api/customer/|api/schedule/|customers/|canvassing/)", r"/service/\1",
                  "Service script files: addresses", suffixes=(".js",))

    print("\n5. Python files that cannot be read")
    import py_compile
    for root in (HERE / "quotations", HERE / "store", HERE / "cleaning"):
        for path in sorted(root.rglob("*.py")):
            try:
                py_compile.compile(str(path), cfile=str(HERE / ".compile_test.pyc"), doraise=True)
            except py_compile.PyCompileError as error:
                if "management" in path.parts and "commands" in path.parts:
                    path.unlink()
                    note("%s has a mistake already in your original and was left out (it is only a helper command): %s"
                         % (path.relative_to(HERE), str(error).strip().splitlines()[-1]))
                else:
                    warn("%s cannot be read by Python: %s" % (path.relative_to(HERE), str(error).strip().splitlines()[-1]))
    (HERE / ".compile_test.pyc").unlink(missing_ok=True)

    print("\n6. Leftover check")
    leftovers = 0
    for root in (HERE / "templates", HERE / "cleaning", HERE / "static"):
        for path in root.rglob("*"):
            if path.is_file() and path.suffix in (".html", ".js", ".py") and "__pycache__" not in path.parts:
                for number, line in enumerate(read(path).splitlines(), 1):
                    if re.search(r"""(?:fetch\(|href=|action=|location(?:\.href)?\s*=)\s*[`'"]/(?!service/|static/|sales/|project/|admin/|logout/|login/|manifest|sw\.js)[a-z]""", line):
                        print("  ?? %s:%d  %s" % (path.relative_to(HERE), number, line.strip()[:110]))
                        leftovers += 1
    if leftovers:
        warn("%d line(s) above still point to an address written out in full; check they work under /service/" % leftovers)

    print("\nDone: %d change(s), %d thing(s) to look at." % (len(changes), len(problems)))
    if problems:
        print("\nPlease read the lines marked !!  (send them to Claude if you are not sure).")
        return 2
    print("Next:  py -m venv venv  ->  venv\\Scripts\\activate  ->  pip install -r requirements.txt  ->  py manage.py check")
    return 0


SERVICES_PY = '''"""Gets quotations from the Sales app.  The Project app and the Sales app are one website now, so the quotation views are called directly:
no internet address and no API key are needed."""
import json
from decimal import Decimal, InvalidOperation

from django.http import Http404
from django.test import RequestFactory


class QuotationApiError(Exception):
    pass


def _get(params, path=""):
    from quotations import views as quotation_views
    import os
    view = quotation_views.materials_estimate if path.strip("/") == "estimate" else quotation_views.materials_api
    request = RequestFactory().get("/sales/api/materials/", params, HTTP_X_API_KEY=os.environ.get("MATERIALS_API_KEY", ""),
                                   HTTP_HOST="localhost")
    try:
        response = view(request)
    except Http404:
        raise QuotationApiError("The quotation was not found (or the Sales app refused the request).")
    except Exception as error:
        raise QuotationApiError("The Sales app could not answer: %s: %s" % (type(error).__name__, error))
    try:
        data = json.loads(response.content.decode("utf-8"))
    except Exception:
        raise QuotationApiError("The Sales app gave an answer that could not be read.")
    if response.status_code >= 400:
        raise QuotationApiError("The Sales app answered %s: %s" % (response.status_code, data.get("error", "")))
    return data


def search_quotations(query):
    return _get({"q": query}).get("quotations", [])


def estimate(specs):
    """The reverse of a quotation: the Sales app works out the material list (with ITS rates), the structure wage and the electrical
    work from the specifications only (panel brand / watts, inverter kW, phase, cable lengths ...)."""
    return _get({k: v for k, v in specs.items() if v not in ("", None)}, "estimate")


def get_quotation(quotation_id):
    return _get({"id": quotation_id})


def to_decimal(value, default=None):
    """'12', '12.5', '1,200' -> Decimal; anything else -> default."""
    try:
        number = Decimal(str(value).replace(",", "").strip())
    except (InvalidOperation, ValueError):
        return default
    return number if number.is_finite() else default
'''


if __name__ == "__main__":
    sys.exit(main())
