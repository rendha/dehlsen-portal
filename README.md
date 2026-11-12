# Dehlsen Energy – one website (stage 1)

Sales (quotations) + Project (materials) + Service (cleaning manager) + Task, with ONE login and a home page with four buttons.
Your three old folders are never changed: `build_portal.py` only copies from them.

## Run it on your computer (PowerShell)
1. Put this folder `dehlsen_portal` on the Desktop, next to `quotation_pwa`, `materials_site` and `SolarCleaningManager`.
2. In this folder:
```
py build_portal.py
py -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
py manage.py check
py manage.py migrate
py manage.py setup_roles
py manage.py createsuperuser
py manage.py runserver
```
3. Open http://127.0.0.1:8000/ , sign in, and you see the four buttons. (This starts with an EMPTY database – your real data is moved in stage 3.)
   `py build_portal.py` prints lines marked `!!` if something needs a look: send them to Claude.

## Addresses
`/` home · `/sales/` quotations · `/project/` materials · `/service/` cleaning manager · `/task/` tasks · `/admin/`

## What the one site changed
* One login for everything (`/login/`). The old login pages of the three apps are not used any more.
* The Project app now reads quotations straight from the Sales app – no API address or key to set.
* One install-as-app (PWA) for the whole site. Time zone is India (Asia/Kolkata) everywhere.
* A small orange Home button floats at the bottom-right inside Sales, Project and Service.

## Stage 2: Task
After `py manage.py migrate` (it now also creates the task tables):
1. `/admin/` > **Task types** > add each task and choose **the people who do it** (these are the only people shown when somebody gives that task).
2. `/admin/` > **Users** > open a person > at the bottom put the **WhatsApp number** (with country code; a 10-digit number is taken as Indian).
3. Open `/task/`: the calendar shows the cleaning/service schedule and the tasks. Tap a day, then "+ Give a task for ...".
Each task shows who gave it, the day it was added and the due date ("due in 4 days" / "2 days overdue"). The Task button shows a red number of tasks waiting.

### Your six tasks and the people (one time)
```
py manage.py import_users      # copies the logins (with passwords) from your old apps' db.sqlite3 files; add --dry-run to only look
py manage.py setup_tasks       # creates Quotation, Site visit, Drawing, Payment Collection, Cleaning and Services, Leads and their people
```
Run `import_users` first so the people already exist. That reads the `db.sqlite3` files in your folders, which do not have people you added AFTER deploying.
To bring those too, give the live database address of each old site (Render > the database > **External Database URL**; for the quotation database add your IP address under the database's access list first, and remove it afterwards):
```
py manage.py import_users --dry-run --cleaning "postgresql://..." --materials "postgresql://..." --quotation "postgresql://..."
```
It only reads from the live databases; nothing there is changed. Or add the missing people by hand in `/admin/` > Users. Change anybody later in `/admin/` > **Task types**.

### Move your real data (stage 3, one time)
Order matters: `migrate` -> `import_users` -> `import_data`.
```
py manage.py import_data --dry-run     # counts only, nothing saved: look at the table
py manage.py import_data               # the real copy (uses the db.sqlite3 files in your three folders)
```
For the live data, give the live database addresses (Render > the database > External Database URL), exactly as for `import_users`:
```
py manage.py import_data --dry-run --quotation "postgresql://..." --materials "postgresql://..." --cleaning "postgresql://..."
```
It only READS the old databases. Every row keeps its number, so the Project app still points at the right quotations. An app that already has rows in the new site is skipped (use `--replace` to empty it first). Run it once for the final move, on the day you switch over.

### Phone alerts (optional, once)
```
pip install -r requirements.txt
py make_vapid_keys.py
```
Set the three values it prints (`VAPID_PUBLIC_KEY`, `VAPID_PRIVATE_KEY`, `VAPID_EMAIL`) as environment variables
(PowerShell on your computer: `$env:VAPID_PUBLIC_KEY="..."` before `runserver`; on the server in the host's Environment page).
Then each person opens **My tasks** on their phone and taps **Turn on alerts on this phone** (iPhone: add the site to the Home Screen first).

## Sales targets (places)

`py manage.py migrate`, then `py manage.py setup_tasks` (accounts, directors) and `py manage.py setup_targets` (places Kochi / Kannur / Kozhikode and others,
their people, the yearly and quarterly targets). Change numbers in `portal/management/commands/setup_targets.py` and run it again, or edit them in Admin
(Places, Sales targets). Financial year April-March. Finished quarters have a "fixed achieved" number; the running quarter is counted from confirmed customers.
A period longer than about 4 months counts as the "year". The quarter targets already carry any earlier shortfall; the year shows achieved against the yearly
target. Only the sales people (a place or a target) and the directors see the dashboard on the home page; only they (and nobody else who logs in) can open /targets/.
Achieved of a person = confirmed customers whose "Quotation For" name = his first name / username / (Admin -> user -> "name in Quotation For").
