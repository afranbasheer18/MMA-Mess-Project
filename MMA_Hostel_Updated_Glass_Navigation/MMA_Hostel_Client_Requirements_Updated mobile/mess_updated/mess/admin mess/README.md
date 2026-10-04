# MMA Hostel Mount Road — Admin / Management App

Desktop-first admin panel: dashboard, manage users, set today's & weekly food
menu, set the mess-entry cutoff time, view tomorrow's mess entries, generate
and track bills, send notifications, and review student feedback.

## Run it
Plain HTML/CSS/JS, no build step.

1. Open this `admin` folder in VS Code (as its own folder, or as a subfolder
   next to your student app folder — see project layout below).
2. Right-click `index.html` → **Open with Live Server**.

## Demo login
- Admin ID: `ADMIN01`
- Password: `admin123`

## Recommended project layout

```
mma-mess-project/
├── student/
│   ├── index.html
│   ├── style.css
│   └── app.js
└── admin/
    ├── index.html
    ├── style.css
    ├── app.js
    └── README.md
```

Two separate apps (students shouldn't be able to load admin's JS/HTML at all),
served as two separate sites/routes.

## How this connects to the student app

Right now **both apps are independent front-ends with their own mock data** —
there's no real connection yet. Two ways to actually connect them:

**1. Quick demo-only link (same browser, no backend)**
Both apps already read/write `localStorage` under the same `mma_` key prefix
(`mma_todayMenu`, `mma_weekMenu`, `mma_cutoffTime`, etc.). If you open both
apps from the **same origin** (e.g. both served from `localhost:5500`), the
admin app writing `mma_todayMenu` will be visible to the student app on its
next reload. This only works for one browser on one device — it's a demo
trick, not a real multi-user system.

**2. Real connection (what you actually want for production)**
Stand up a backend (this matches your Django project) with REST endpoints
that both apps call instead of using mock arrays/localStorage:

| Purpose | Endpoint (suggested) | Used by |
|---|---|---|
| Login | `POST /api/login/` | both |
| Today's & weekly menu | `GET/PUT /api/menu/` | admin writes, student reads |
| Cutoff time | `GET/PUT /api/settings/cutoff/` | admin writes, student reads |
| Submit tomorrow's entry | `POST /api/entries/` | student writes, admin reads |
| Mark meal eaten | `POST /api/entries/{id}/eaten/` | student |
| Feedback | `POST /api/feedback/`, `GET /api/feedback/` | student writes, admin reads |
| Bills | `GET /api/bills/`, `POST /api/bills/generate/` | admin generates, student reads own |
| Notifications | `POST /api/notifications/`, `GET /api/notifications/` | admin writes, student reads |
| Users | `GET/POST/PATCH /api/users/` | admin only |

In each app's `app.js`, replace the `let X = store.get(...)` mock-data lines
with a `fetch('/api/...')` call on load, and replace each `store.set(...)`
call with a `fetch(..., {method:'POST'/'PUT'})`. The data shapes (field names)
in both files already match, so the swap is mostly mechanical once the
Django REST views exist.

## Notes
- Not yet implemented: real authentication/sessions, role-based access control
  on the backend, per-student bill detail drill-down, editable meal timings.
