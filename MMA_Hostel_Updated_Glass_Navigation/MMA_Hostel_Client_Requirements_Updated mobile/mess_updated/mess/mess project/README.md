# MMA Hostel Mount Road — Mess Management App

Mobile-first student-side prototype: login, today's/weekly menu, tomorrow's mess
entry, meal-eaten marking + feedback, mess bills, monthly entry history, notifications,
and settings.

## Run it
No build step needed — plain HTML/CSS/JS.

1. Open this folder in VS Code.
2. Install the **Live Server** extension (or any static server).
3. Right-click `index.html` → **Open with Live Server** (or just double-click
   `index.html` to open it directly in a browser).

## Demo login
- User ID: `STU101`
- Password: `demo123`

## Structure
```
index.html   markup
style.css    all styling (CSS variables at the top for the color theme)
app.js       mock data + app logic (login, nav, mess entry, feedback, bills, notifications)
```

## Notes
- All "backend" data (menu, bills, notifications, meal records) lives in the mock
  objects at the top of `app.js` — swap these for real API calls when the backend
  is ready.
- State (tomorrow's entry, meal-eaten status, feedback) persists via `localStorage`.
- Not yet implemented: admin side, real auth, password change, meal-time-based
  unlocking (dinner is currently hardcoded as "not yet served").
