# Shared database connection

The current updated ZIP intentionally preserves the working localStorage mode. To make all users share data across phones, configure Supabase/PostgreSQL and replace the storage functions with authenticated database calls.

Recommended production model:
- Supabase Auth for passwords.
- profiles table linked to auth.users.
- roles: admin, mess_secretary, student/worker.
- RLS policies so users can read/write only their own records while admin/secretary can manage permitted hostel records.
- tables for invitations, registration_requests, meal_entries, meal_confirmations, food_limits, meal_rates, requests, feedback, leave, cancellations, notifications, activity_logs and bills.

Do not put real Supabase service-role keys in browser JavaScript.
