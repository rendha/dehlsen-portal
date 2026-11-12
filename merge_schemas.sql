-- merge_schemas.sql
-- The live database keeps three separate areas (schemas): public (quotations), cleaning (Cleaning Manager), materials (store).
-- The portal wants ALL tables in `public`.  This script moves them there and merges the three user lists
-- (matched by username, ignoring capital letters).  Run it ONCE, on a COPY of the live data, inside one transaction.
-- Nothing is deleted: the old `cleaning` and `materials` areas stay (with the old user lists) until you drop them yourself.
BEGIN;

-- 1. one list of people: for each username (ignoring case) the row used most recently wins
CREATE TEMP TABLE cand AS
SELECT 'public'::text AS sch, id, username, password, first_name, last_name, email, is_staff, is_superuser, is_active, date_joined, last_login, 0 AS pref FROM public.auth_user
UNION ALL SELECT 'cleaning', id, username, password, first_name, last_name, email, is_staff, is_superuser, is_active, date_joined, last_login, 1 FROM cleaning.auth_user
UNION ALL SELECT 'materials', id, username, password, first_name, last_name, email, is_staff, is_superuser, is_active, date_joined, last_login, 2 FROM materials.auth_user;

CREATE TEMP TABLE winner AS
SELECT DISTINCT ON (lower(username)) * FROM cand ORDER BY lower(username), last_login DESC NULLS LAST, pref;

-- 2. people who already exist in public keep their id (and take the winner's password); others get new ids
UPDATE public.auth_user p SET
    password = w.password,
    is_superuser = p.is_superuser OR w.is_superuser OR EXISTS (SELECT 1 FROM cand c WHERE lower(c.username) = lower(p.username) AND c.is_superuser),
    is_staff = p.is_staff OR w.is_staff,
    first_name = COALESCE(NULLIF(p.first_name, ''), (SELECT max(c.first_name) FROM cand c WHERE lower(c.username) = lower(p.username) AND c.first_name <> ''), ''),
    last_login = GREATEST(p.last_login, w.last_login)
FROM winner w WHERE lower(p.username) = lower(w.username);

SELECT setval('public.auth_user_id_seq', (SELECT max(id) FROM public.auth_user));
INSERT INTO public.auth_user (id, password, last_login, is_superuser, username, first_name, last_name, email, is_staff, is_active, date_joined)
SELECT nextval('public.auth_user_id_seq'), w.password, w.last_login, (SELECT bool_or(c.is_superuser) FROM cand c WHERE lower(c.username) = lower(w.username)),
       w.username, w.first_name, w.last_name, w.email,
       -- the Cleaning Manager's own owner/employee setting wins for people it knows (a director is a normal person there)
       COALESCE((SELECT c.is_staff FROM cand c WHERE c.sch = 'cleaning' AND lower(c.username) = lower(w.username)), w.is_staff),
       w.is_active, w.date_joined
FROM winner w WHERE NOT EXISTS (SELECT 1 FROM public.auth_user p WHERE lower(p.username) = lower(w.username));

-- old id in each area -> new id
CREATE TEMP TABLE usermap AS
SELECT c.sch, c.id AS old_id, p.id AS new_id FROM cand c JOIN public.auth_user p ON lower(p.username) = lower(c.username);

-- 3. the Cleaning tables point to people: point them to the merged list
ALTER TABLE cleaning.cleaning_cleaningjob DROP CONSTRAINT cleaning_cleaningjob_done_by_id_45b01648_fk_auth_user_id;
ALTER TABLE cleaning.cleaning_cleaningschedule DROP CONSTRAINT cleaning_cleaningsch_assigned_to_id_00bbfc4c_fk_auth_user;
ALTER TABLE cleaning.cleaning_schedulerequest DROP CONSTRAINT cleaning_schedulereq_requested_by_id_bc6fa1b3_fk_auth_user;
UPDATE cleaning.cleaning_cleaningjob t SET done_by_id = m.new_id FROM usermap m WHERE m.sch = 'cleaning' AND m.old_id = t.done_by_id;
UPDATE cleaning.cleaning_cleaningschedule t SET assigned_to_id = m.new_id FROM usermap m WHERE m.sch = 'cleaning' AND m.old_id = t.assigned_to_id;
UPDATE cleaning.cleaning_schedulerequest t SET requested_by_id = m.new_id FROM usermap m WHERE m.sch = 'cleaning' AND m.old_id = t.requested_by_id;

-- 4. groups of the Project app (Project, Store, Accounts, Boss)
INSERT INTO public.auth_group (name) SELECT name FROM materials.auth_group g WHERE NOT EXISTS (SELECT 1 FROM public.auth_group p WHERE p.name = g.name);
INSERT INTO public.auth_user_groups (user_id, group_id)
SELECT m.new_id, pg.id FROM materials.auth_user_groups ug
JOIN materials.auth_group g ON g.id = ug.group_id JOIN public.auth_group pg ON pg.name = g.name
JOIN usermap m ON m.sch = 'materials' AND m.old_id = ug.user_id
ON CONFLICT DO NOTHING;

-- 5. move the tables into public (their sequences, indexes and constraints move with them)
DO $$
DECLARE r record;
BEGIN
  FOR r IN SELECT schemaname, tablename FROM pg_tables
           WHERE (schemaname = 'cleaning' AND tablename LIKE 'cleaning\_%')
              OR (schemaname = 'materials' AND tablename LIKE 'store\_%')
  LOOP
    EXECUTE format('ALTER TABLE %I.%I SET SCHEMA public', r.schemaname, r.tablename);
  END LOOP;
END $$;

ALTER TABLE public.cleaning_cleaningjob ADD CONSTRAINT cleaning_cleaningjob_done_by_id_fk_auth_user FOREIGN KEY (done_by_id) REFERENCES public.auth_user(id) DEFERRABLE INITIALLY DEFERRED;
ALTER TABLE public.cleaning_cleaningschedule ADD CONSTRAINT cleaning_cleaningsch_assigned_to_id_fk_auth_user FOREIGN KEY (assigned_to_id) REFERENCES public.auth_user(id) DEFERRABLE INITIALLY DEFERRED;
ALTER TABLE public.cleaning_schedulerequest ADD CONSTRAINT cleaning_schedulereq_requested_by_id_fk_auth_user FOREIGN KEY (requested_by_id) REFERENCES public.auth_user(id) DEFERRABLE INITIALLY DEFERRED;

-- 6. tell Django which migrations of the Service and Project apps are already done
INSERT INTO public.django_migrations (app, name, applied)
SELECT app, name, applied FROM (
  SELECT app, name, applied FROM cleaning.django_migrations WHERE app = 'cleaning'
  UNION ALL SELECT app, name, applied FROM materials.django_migrations WHERE app = 'store') s
WHERE NOT EXISTS (SELECT 1 FROM public.django_migrations d WHERE d.app = s.app AND d.name = s.name);

COMMIT;
