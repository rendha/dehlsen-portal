"""
sync_cleaning.py  -  brings ONLY the Service (cleaning) part of the portal up to date with your live SolarCleaningManager.

    py sync_cleaning.py            (run it inside dehlsen_portal, with SolarCleaningManager next to it on the Desktop)

It copies  SolarCleaningManager/cleaning, templates and static  into this project and repeats the same small changes that build_portal.py
makes for the Service part (shared login, no clashing names, links under /service/).
It does NOT touch quotations/, store/ or portal/ (your Leads work is safe) and never changes SolarCleaningManager.
Use  --check  to only look.   Afterwards:  git diff --stat   to see what changed.
"""
import argparse
import re
import sys
from pathlib import Path

import build_portal as bp

HERE = bp.HERE


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cleaning", default=str(HERE.parent / "SolarCleaningManager"))
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()
    c = Path(args.cleaning)
    if not (c / "cleaning").is_dir() or not (c / "templates").is_dir():
        print("SolarCleaningManager was not found at", c)
        return 1
    print("SolarCleaningManager found.")
    if args.check:
        return 0

    print("\n1. Copying")
    bp.copy(c / "cleaning", HERE / "cleaning", "Service (cleaning)")
    bp.copy(c / "templates", HERE / "templates", "Service pages (templates)")
    if (c / "static").is_dir():
        bp.copy(c / "static", HERE / "static", "Service static files")

    print("\n2. Service (cleaning) changes")
    cl = HERE / "cleaning"
    for route in ("login/", "logout/", "sw.js"):
        bp.remove_path_entry(cl / "urls.py", route)
    bp.replace_in(cl / "urls.py", "name='home'", "name='cleaning_home'", "renamed the Service home page", 1)
    bp.replace_in(HERE / "templates" / "base.html", "{% url 'home' %}", "{% url 'cleaning_home' %}", "Service top bar link")
    bp.replace_in(HERE / "templates" / "base.html", "{% static 'manifest.json' %}", "/manifest.webmanifest", "Service uses the site's one manifest")
    for pattern, repl, label in (
        (r"(?<![\w/])/(schedule/)", r"/service/\1", "links to /schedule/"),
        (r"(?<![\w/])/(my-jobs/)", r"/service/\1", "links to /my-jobs/"),
        (r"(?<![\w/])/(api/customer/)", r"/service/\1", "links to /api/customer/"),
        (r"(?<![\w/])/(api/schedule/)", r"/service/\1", "links to /api/schedule/"),
    ):
        bp.regex_in_tree(HERE / "templates", r"(?<=[`'\"])" + pattern, repl, "Service pages: " + label)
        bp.regex_in_tree(cl, r"(?<=[`'\"])" + pattern, repl, "Service code: " + label)
    bp.regex_in_tree(HERE / "static", r"(?<=[`'\"])(?<![\w/])/(schedule/|my-jobs/|api/customer/|api/schedule/|customers/|canvassing/)", r"/service/\1",
                     "Service script files: addresses", suffixes=(".js",))

    print("\n3. Python files that cannot be read")
    import ast
    for path in sorted(cl.rglob("*.py")):
        try:
            ast.parse(bp.read(path))
        except SyntaxError as error:
            if "management" in path.parts and "commands" in path.parts:
                path.unlink()
                bp.note("%s is unfinished already in your original (line %s) and was left out; it is only a helper command" % (path.relative_to(HERE), error.lineno))
            else:
                bp.warn("%s cannot be read by Python: %s" % (path.relative_to(HERE), error))
    (HERE / ".compile_test.pyc").unlink(missing_ok=True)

    print("\n4. Addresses still written out in full (check they work under /service/)")
    left = 0
    for root in (HERE / "templates", cl, HERE / "static"):
        for path in root.rglob("*"):
            if path.is_file() and path.suffix in (".html", ".js", ".py") and "__pycache__" not in path.parts:
                for number, line in enumerate(bp.read(path).splitlines(), 1):
                    if re.search(r"""(?:fetch\(|href=|action=|location(?:\.href)?\s*=)\s*[`'"]/(?!service/|static/|sales/|project/|admin/|logout/|login/|manifest|sw\.js)[a-z]""", line):
                        print("  ?? %s:%d  %s" % (path.relative_to(HERE), number, line.strip()[:110]))
                        left += 1
    print("\nDone. %d thing(s) to look at, %d address(es) to check." % (len(bp.problems), left))
    print("Next:  py manage.py check   then   py manage.py migrate   then   git diff --stat")
    return 2 if bp.problems else 0


if __name__ == "__main__":
    sys.exit(main())
