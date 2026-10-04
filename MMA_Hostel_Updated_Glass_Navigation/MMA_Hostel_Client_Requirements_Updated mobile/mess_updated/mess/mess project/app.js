/* =========================================================
   HOSTEL MESS - USER APP
   ========================================================= */

/* ==================== SHARED STORAGE ==================== */

const store = {
  get(key, defaultValue) {
    try {
      const value = localStorage.getItem("mma_" + key);
      return value !== null ? JSON.parse(value) : defaultValue;
    } catch (error) {
      console.error("Storage read error:", error);
      return defaultValue;
    }
  },

  set(key, value) {
    try {
      localStorage.setItem("mma_" + key, JSON.stringify(value));
    } catch (error) {
      console.error("Storage write error:", error);
    }
  }
};

/* ==================== ADMIN DATA ==================== */

function getUsers() {
  return store.get("users", []);
}

function getTodayMenu() {
  return store.get("todayMenu", {
    breakfast: "",
    lunch: "",
    dinner: ""
  });
}

function getWeekMenu() {
  return store.get("weekMenu", [
    { day: "Mon", b: "", l: "", d: "" },
    { day: "Tue", b: "", l: "", d: "" },
    { day: "Wed", b: "", l: "", d: "" },
    { day: "Thu", b: "", l: "", d: "" },
    { day: "Fri", b: "", l: "", d: "" },
    { day: "Sat", b: "", l: "", d: "" },
    { day: "Sun", b: "", l: "", d: "" }
  ]);
}

function getTomorrowEntries() {
  return store.get("tomorrowEntries", []);
}

function getBills() {
  return store.get("adminBills", []);
}

function getNotifications() {
  return store.get("notifHistory", []);
}

function getFeedback() {
  return store.get("feedback", []);
}

function getCutoffTime() {
  return store.get("cutoffTime", "06:00");
}

/* ==================== ENTRY HISTORY ==================== */

function getEntryHistory() {
  const history = store.get("messEntryHistory", []);
  return Array.isArray(history) ? history : [];
}

function saveEntryHistory(history) {
  store.set("messEntryHistory", history);
}

/* ==================== CURRENT USER ==================== */

let currentUser = null;

function findUser(userId) {
  return getUsers().find(function (user) {
    return String(user.id || "").toUpperCase() ===
      String(userId || "").toUpperCase();
  }) || null;
}

/* ==================== PASSWORD ==================== */

function togglePw() {
  const passwordInput = document.getElementById("pw");
  const button = document.getElementById("pwToggle");

  if (!passwordInput) return;

  if (passwordInput.type === "password") {
    passwordInput.type = "text";
    if (button) button.textContent = "Hide";
  } else {
    passwordInput.type = "password";
    if (button) button.textContent = "Show";
  }
}

/* ==================== LOGIN ==================== */

function doLogin() {
  const userInput = document.getElementById("uid");
  const passwordInput = document.getElementById("pw");
  const errorBox = document.getElementById("loginErr");

  if (!userInput || !passwordInput) return;

  const userId = userInput.value.trim().toUpperCase();
  const password = passwordInput.value.trim();
  const user = findUser(userId);

  function showLoginError(message) {
    if (errorBox) {
      errorBox.textContent = message;
      errorBox.style.display = "block";
    }
  }

  if (!user) {
    showLoginError("Invalid User ID or password.");
    return;
  }

  if (
    user.status &&
    String(user.status).toLowerCase() !== "active"
  ) {
    showLoginError("This user account is inactive.");
    return;
  }

  if (String(user.pw ?? "") !== password) {
    showLoginError("Invalid User ID or password.");
    return;
  }

  currentUser = user;

  store.set("currentUserId", user.id);

  if (errorBox) errorBox.style.display = "none";

  const loginScreen = document.getElementById("login");
  const app = document.getElementById("app");

  if (loginScreen) loginScreen.classList.remove("active");
  if (app) app.style.display = "block";

  initApp();
}

/* ==================== LOGOUT ==================== */

function doLogout() {
  currentUser = null;
  store.set("currentUserId", "");

  const app = document.getElementById("app");
  const login = document.getElementById("login");
  const uid = document.getElementById("uid");
  const pw = document.getElementById("pw");

  if (app) app.style.display = "none";
  if (login) login.classList.add("active");
  if (uid) uid.value = "";
  if (pw) pw.value = "";

  openScreen("home");
}

/* ==================== NAVIGATION ==================== */

function openScreen(id) {
  document.querySelectorAll("main .screen").forEach(function (screen) {
    screen.classList.remove("active");
  });

  const target = document.getElementById(id);
  if (target) target.classList.add("active");

  document.querySelectorAll("nav.bottom .navbtn").forEach(function (button) {
    button.classList.toggle("active", button.dataset.s === id);
  });

  if (id === "notifs") markNotifsRead();
  if (id === "settings") updateSettings();
}

function toggleSide() {
  const side = document.querySelector(".side");
  if (side) side.classList.toggle("open");
}

/* ==================== DATE FUNCTIONS ==================== */

function getDateKey(date) {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");

  return `${year}-${month}-${day}`;
}

function getTargetDate(daysFromToday) {
  const date = new Date();
  date.setHours(0, 0, 0, 0);
  date.setDate(date.getDate() + daysFromToday);
  return date;
}

function formatEntryDate(date) {
  return date.toLocaleDateString("en-IN", {
    weekday: "long",
    day: "numeric",
    month: "short"
  });
}

/* ==================== INITIALIZE APP ==================== */

function initApp() {
  if (!currentUser) {
    const savedUserId = store.get("currentUserId", "");
    if (savedUserId) currentUser = findUser(savedUserId);
  }

  if (!currentUser) return;

  renderUserDetails();
  renderTodayMenu();
  renderWeekMenu();

  // Display entries for all three dates
  renderYesterdayEntry();
  renderTodayEntry();
  renderQty();

  renderMealStatus();
  renderMonthly();
  renderBills();
  renderNotifs();
  updateSettings();
}

/* ==================== USER DETAILS ==================== */

function renderUserDetails() {
  if (!currentUser) return;

  const name = currentUser.name || currentUser.id || "User";
  const firstName = name.split(" ")[0];

  const headerName = document.getElementById("hdrName");
  const greeting = document.getElementById("greetText");
  const date = document.getElementById("todayDate");

  if (headerName) headerName.textContent = name;
  if (greeting) greeting.textContent = "Good Morning, " + firstName;

  if (date) {
    date.textContent = new Date().toLocaleDateString("en-IN", {
      weekday: "long",
      day: "numeric",
      month: "long",
      year: "numeric"
    });
  }
}

/* ==================== TODAY MENU ==================== */

function renderTodayMenu() {
  const container = document.getElementById("todayFood");
  if (!container) return;

  const todayMenu = getTodayMenu();

  const emoji = {
    breakfast: "🥣",
    lunch: "🍚",
    dinner: "🍛"
  };

  container.innerHTML = Object.entries(todayMenu).map(function (item) {
    const meal = item[0];
    const food = item[1];

    return `
      <div class="food-card">
        <div class="emoji">${emoji[meal] || "🍽️"}</div>
        <div class="meal">${meal}</div>
        <div class="name">${food || "Not updated"}</div>
      </div>
    `;
  }).join("");
}

/* ==================== WEEKLY MENU ==================== */

function renderWeekMenu() {
  const container = document.getElementById("weekMenu");
  if (!container) return;

  const week = getWeekMenu();

  container.innerHTML = week.map(function (day) {
    return `
      <div class="day-card">
        <div class="day">${day.day || ""}</div>
        <div class="row"><span>Breakfast</span><b>${day.b || "-"}</b></div>
        <div class="row"><span>Lunch</span><b>${day.l || "-"}</b></div>
        <div class="row"><span>Dinner</span><b>${day.d || "-"}</b></div>
      </div>
    `;
  }).join("");
}

/* ==================== FIND USER ENTRY BY DATE ==================== */

function getMyEntryForDate(dateKey) {
  if (!currentUser) return null;

  const userId = String(currentUser.id || "").toUpperCase();

  return getEntryHistory().find(function (entry) {
    return (
      String(entry.user || "").toUpperCase() === userId &&
      entry.date === dateKey
    );
  }) || null;
}

/* ==================== COMMON ENTRY DISPLAY ==================== */

function renderEntryRows(container, entry) {
  if (!container) return;

  const meals = [
    ["Breakfast", Number(entry?.b || 0)],
    ["Lunch", Number(entry?.l || 0)],
    ["Dinner", Number(entry?.d || 0)]
  ];

  container.innerHTML = meals.map(function (meal) {
    return `
      <div class="qty-row">
        <div class="qty-label">${meal[0]}</div>
        <div class="qty-ctrl">
          <span class="val">${meal[1]}</span>
        </div>
      </div>
    `;
  }).join("");
}

/* ==================== YESTERDAY'S MESS ENTRY ==================== */

function renderYesterdayEntry() {
  const container = document.getElementById("yesterdayEntry");
  const dateLabel = document.getElementById("yesterdayEntryDate");

  if (!container) return;

  const yesterday = getTargetDate(-1);
  const yesterdayKey = getDateKey(yesterday);

  if (dateLabel) {
    dateLabel.textContent = "(" + formatEntryDate(yesterday) + ")";
  }

  const entry = getMyEntryForDate(yesterdayKey);

  renderEntryRows(container, entry);
}

/* ==================== TODAY'S SAVED MESS ENTRY ==================== */

function renderTodayEntry() {
  if (!currentUser) return;

  const container = document.getElementById("todayEntry");
  const dateLabel = document.getElementById("todayEntryDate");

  // These elements must exist in index.html.
  if (!container) return;

  const today = getTargetDate(0);
  const todayKey = getDateKey(today);

  if (dateLabel) {
    dateLabel.textContent = "(" + formatEntryDate(today) + ")";
  }

  const entry = getMyEntryForDate(todayKey);

  renderEntryRows(container, entry);
}

/* ==================== TOMORROW'S MESS ENTRY ==================== */

function getMyTomorrowEntry() {
  const tomorrowKey = getDateKey(getTargetDate(1));
  const entry = getMyEntryForDate(tomorrowKey);

  if (!entry) {
    return { breakfast: 0, lunch: 0, dinner: 0 };
  }

  return {
    breakfast: Number(entry.b || 0),
    lunch: Number(entry.l || 0),
    dinner: Number(entry.d || 0)
  };
}

let qty = getMyTomorrowEntry();
let submitted = false;
let tomorrowEditMode = false;

function checkSubmitted() {
  if (!currentUser) return false;

  const tomorrowKey = getDateKey(getTargetDate(1));
  return getMyEntryForDate(tomorrowKey) !== null;
}

function renderQty() {
  const container = document.getElementById("qtyRows");
  const dateLabel = document.getElementById("tomorrowEntryDate");

  if (!container) return;

  const tomorrow = getTargetDate(1);

  if (dateLabel) {
    dateLabel.textContent = "(" + formatEntryDate(tomorrow) + ")";
  }

  qty = getMyTomorrowEntry();

  const saved = checkSubmitted();
  submitted = saved && !tomorrowEditMode;

  container.innerHTML = ["breakfast", "lunch", "dinner"].map(function (meal) {
    return `
      <div class="qty-row">
        <div class="qty-label" style="text-transform:capitalize">${meal}</div>
        <div class="qty-ctrl">
          <button ${submitted ? "disabled" : ""}
            onclick="changeQty('${meal}', -1)">−</button>
          <span class="val" id="qv_${meal}">${qty[meal]}</span>
          <button ${submitted ? "disabled" : ""}
            onclick="changeQty('${meal}', 1)">+</button>
        </div>
      </div>
    `;
  }).join("");

  const confirmation = document.getElementById("entryConfirm");
  const submitButton = document.getElementById("tomorrowSubmitBtn");
  const editButton = document.getElementById("tomorrowEditBtn");

  if (confirmation) confirmation.style.display = submitted ? "block" : "none";
  if (submitButton) submitButton.style.display = submitted ? "none" : "block";
  if (editButton) editButton.style.display = submitted ? "block" : "none";
}

function changeQty(meal, difference) {
  if (submitted) return;

  if (qty[meal] === undefined) qty[meal] = 0;

  qty[meal] = Math.min(2, Math.max(0, Number(qty[meal]) + difference));

  const value = document.getElementById("qv_" + meal);
  if (value) value.textContent = qty[meal];
}

function editTomorrowEntry() {
  tomorrowEditMode = true;
  submitted = false;
  renderQty();
}

/* ==================== SAVE TOMORROW'S ENTRY ==================== */

function submitEntry() {
  if (!currentUser) return;

  const tomorrowKey = getDateKey(getTargetDate(1));
  const history = getEntryHistory();

  const newEntry = {
    user: currentUser.id,
    room: currentUser.room || "",
    date: tomorrowKey,
    b: Number(qty.breakfast || 0),
    l: Number(qty.lunch || 0),
    d: Number(qty.dinner || 0)
  };

  const existingIndex = history.findIndex(function (entry) {
    return (
      String(entry.user || "").toUpperCase() ===
        String(currentUser.id || "").toUpperCase() &&
      entry.date === tomorrowKey
    );
  });

  if (existingIndex >= 0) {
    history[existingIndex] = newEntry;
  } else {
    history.push(newEntry);
  }

  saveEntryHistory(history);

  /*
   * Keep the admin's tomorrowEntries list updated.
   * Preserve other users' entries.
   */
  const adminEntries = getTomorrowEntries();

  const adminIndex = adminEntries.findIndex(function (entry) {
    return String(entry.user || "").toUpperCase() ===
      String(currentUser.id || "").toUpperCase();
  });

  const adminEntry = {
    user: currentUser.id,
    room: currentUser.room || "",
    b: newEntry.b,
    l: newEntry.l,
    d: newEntry.d
  };

  if (adminIndex >= 0) {
    adminEntries[adminIndex] = adminEntry;
  } else {
    adminEntries.push(adminEntry);
  }

  store.set("tomorrowEntries", adminEntries);

  tomorrowEditMode = false;
  submitted = true;

  // Refresh every date-dependent section immediately.
  renderQty();
  renderYesterdayEntry();
  renderTodayEntry();
  renderMonthly();
}

/* ==================== TODAY'S MEAL STATUS ==================== */

function getDefaultMealStatus() {
  return {
    breakfast: { eaten: false, rating: 0, fb: "" },
    lunch: { eaten: false, rating: 0, fb: "" },
    dinner: { eaten: false, rating: 0, fb: "" }
  };
}

function getMealStatus() {
  if (!currentUser) return getDefaultMealStatus();

  return store.get(
    "mealStatus_" + currentUser.id,
    getDefaultMealStatus()
  );
}

let mealStatus = getMealStatus();

function saveMealStatus() {
  if (!currentUser) return;

  store.set("mealStatus_" + currentUser.id, mealStatus);
}

/* ==================== TODAY'S MEAL ENTRY (after eating) ====================
   The student saves how many portions they actually ate for each meal.
   Saved records go to localStorage key "mma_mealRecords" so the admin app
   (Meal Records screen) can compare them with the expected entry.

   Record shape:
   { user, date:"YYYY-MM-DD",
     meals:{ b:{q,t}|null, l:{q,t}|null, d:{q,t}|null },   // q = qty eaten, t = "HH:MM"
     confirmed:false, confirmedAt:"HH:MM"|null }
*/

// Meal opens for saving from this time (24h "HH:MM"). Change to suit the mess timings.
const MEAL_OPEN_TIME = { breakfast: "06:00", lunch: "11:00", dinner: "18:30" };

const MEAL_INFO = [
  { key: "breakfast", short: "b", label: "Breakfast", icon: "🍳", cls: "bf" },
  { key: "lunch",     short: "l", label: "Lunch",     icon: "🍛", cls: "ln" },
  { key: "dinner",    short: "d", label: "Dinner",    icon: "🌙", cls: "dn" }
];

let mealDraft = {};        // unsaved counter values, per meal key
let mealEditing = {};      // meals currently being edited
let feedbackOpen = {};     // feedback panels currently open
let feedbackDraft = {};    // text typed in feedback boxes

function nowHHMM() {
  const d = new Date();
  return String(d.getHours()).padStart(2, "0") + ":" + String(d.getMinutes()).padStart(2, "0");
}

function formatTime12(hhmm) {
  if (!hhmm) return "";
  const parts = hhmm.split(":");
  let h = Number(parts[0]);
  const m = parts[1];
  const suffix = h >= 12 ? "PM" : "AM";
  h = h % 12 || 12;
  return String(h).padStart(2, "0") + ":" + m + " " + suffix;
}

function getMealRecords() {
  const records = store.get("mealRecords", []);
  return Array.isArray(records) ? records : [];
}

function getMyTodayRecord() {
  if (!currentUser) return null;
  const todayKey = getDateKey(getTargetDate(0));
  const uid = String(currentUser.id || "").toUpperCase();

  return getMealRecords().find(function (r) {
    return String(r.user || "").toUpperCase() === uid && r.date === todayKey;
  }) || null;
}

function saveMyTodayRecord(record) {
  const records = getMealRecords();
  const uid = String(record.user || "").toUpperCase();

  const index = records.findIndex(function (r) {
    return String(r.user || "").toUpperCase() === uid && r.date === record.date;
  });

  if (index >= 0) records[index] = record;
  else records.push(record);

  store.set("mealRecords", records);
}

function getOrCreateTodayRecord() {
  const existing = getMyTodayRecord();
  if (existing) return existing;

  return {
    user: currentUser.id,
    room: currentUser.room || "",
    date: getDateKey(getTargetDate(0)),
    meals: { b: null, l: null, d: null },
    confirmed: false,
    confirmedAt: null
  };
}

function isMealOpen(mealKey) {
  return nowHHMM() >= MEAL_OPEN_TIME[mealKey];
}

function getExpectedQty(short) {
  const entry = getMyEntryForDate(getDateKey(getTargetDate(0)));
  return Number(entry ? entry[short] : 0) || 0;
}

function renderMealStatus() {
  const container = document.getElementById("mealStatusCard");
  if (!container || !currentUser) return;

  // keep anything typed in feedback boxes across re-renders
  MEAL_INFO.forEach(function (m) {
    const box = document.getElementById("fb_" + m.key);
    if (box) feedbackDraft[m.key] = box.value;
  });

  mealStatus = getMealStatus();
  const todayMenu = getTodayMenu();
  const record = getMyTodayRecord();
  const today = getTargetDate(0);

  const dateText =
    today.toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" }) +
    " (" + today.toLocaleDateString("en-GB", { weekday: "long" }) + ")";

  const savedCount = MEAL_INFO.filter(function (m) {
    return record && record.meals[m.short];
  }).length;
  const allSaved = savedCount === MEAL_INFO.length;
  const confirmed = !!(record && record.confirmed);

  const mealsHTML = MEAL_INFO.map(function (m) {
    const saved = record ? record.meals[m.short] : null;
    const editing = !!mealEditing[m.key];
    const open = isMealOpen(m.key);
    const expected = getExpectedQty(m.short);

    if (mealDraft[m.key] === undefined) {
      mealDraft[m.key] = saved ? saved.q : expected;
    }
    const value = mealDraft[m.key];

    const canEdit = open && (!saved || editing) && !confirmed;
    const status = mealStatus[m.key] || { rating: 0, fb: "" };

    let chip = "";
    if (saved && !editing) {
      chip = `<span class="me-chip ok">✓ Saved at ${formatTime12(saved.t)}</span>`;
    } else if (!open) {
      chip = `<span class="me-chip lock">Opens at ${formatTime12(MEAL_OPEN_TIME[m.key])}</span>`;
    } else {
      chip = `<span class="me-chip todo">Not saved</span>`;
    }

    let actions = "";
    if (saved && !editing) {
      actions += `<button class="me-btn" ${confirmed ? "disabled" : ""}
        onclick="editMealEntry('${m.key}')">✎ Edit</button>`;
    } else if (open) {
      actions += `<button class="me-btn primary" onclick="saveMealEntry('${m.key}')">Save</button>`;
    }

    const canFeedback = saved && Number(saved.q) > 0;
    actions += `<button class="me-btn" ${canFeedback ? "" : "disabled"}
      onclick="toggleFeedback('${m.key}')">💬 Feedback</button>`;

    const feedbackHTML = feedbackOpen[m.key] && canFeedback ? `
      <div class="me-feedback">
        <div class="stars">
          ${[1, 2, 3, 4, 5].map(function (n) {
            return `<span class="star ${n <= status.rating ? "on" : ""}"
              onclick="rate('${m.key}', ${n})">★</span>`;
          }).join("")}
        </div>
        <textarea class="fb-input" rows="2" id="fb_${m.key}"
          placeholder="Write your feedback (optional)">${
            feedbackDraft[m.key] !== undefined ? feedbackDraft[m.key] : (status.fb || "")
          }</textarea>
        <button class="fb-submit" onclick="submitFeedback('${m.key}')">Submit Feedback</button>
      </div>` : "";

    return `
      <div class="me-card ${m.cls}">
        <div class="me-top">
          <div class="me-icon">${m.icon}</div>
          <div class="me-name">
            <div class="me-title">${m.label}</div>
            <div class="me-food">${todayMenu[m.key] || "Not available"}</div>
          </div>
          ${chip}
        </div>
        <div class="me-bottom">
          <div class="me-counter">
            <button ${canEdit ? "" : "disabled"} onclick="changeMealQty('${m.key}', -1)">−</button>
            <span class="val">${value}</span>
            <button ${canEdit ? "" : "disabled"} onclick="changeMealQty('${m.key}', 1)">+</button>
          </div>
          <div class="me-expected">Expected ${expected}</div>
          <div class="me-actions">${actions}</div>
        </div>
        ${feedbackHTML}
      </div>`;
  }).join("");

  const chipsHTML = MEAL_INFO.map(function (m) {
    const done = record && record.meals[m.short];
    return `<div class="dc-chip ${done ? "done" : ""}">
      <div class="n">${m.label}</div>
      <div class="s">${done ? "Saved ✓" : "Pending"}</div>
    </div>`;
  }).join("");

  let completeBtn;
  if (confirmed) {
    completeBtn = `<button class="dc-btn done" disabled>✓ Completed at ${formatTime12(record.confirmedAt)}</button>`;
  } else {
    completeBtn = `<button class="dc-btn" ${allSaved ? "" : "disabled"}
      onclick="completeTodayEntries()">Complete Today's Meal Entries</button>`;
  }

  container.innerHTML = `
    <div class="me-head">
      <div class="me-head-icon">📅</div>
      <div>
        <div class="me-head-title">Today's Meal Entry</div>
        <div class="me-head-date">${dateText}</div>
      </div>
    </div>
    ${mealsHTML}
    <div class="dc-box">
      <div class="dc-title">🛡️ Daily Meal Confirmation</div>
      <div class="dc-chips">${chipsHTML}</div>
      ${completeBtn}
      ${!allSaved && !confirmed ? `<div class="dc-note">Save all three meals (use 0 if you skipped one) to complete today.</div>` : ""}
    </div>
  `;
}

function changeMealQty(mealKey, diff) {
  const current = Number(mealDraft[mealKey] || 0);
  mealDraft[mealKey] = Math.max(0, Math.min(2, current + diff));
  renderMealStatus();
}

function saveMealEntry(mealKey) {
  if (!currentUser) return;
  const info = MEAL_INFO.find(function (m) { return m.key === mealKey; });
  if (!info || !isMealOpen(mealKey)) return;

  const record = getOrCreateTodayRecord();
  record.meals[info.short] = { q: Number(mealDraft[mealKey] || 0), t: nowHHMM() };
  record.confirmed = false;
  record.confirmedAt = null;
  saveMyTodayRecord(record);

  // keep the older per-student status flag in sync
  mealStatus = getMealStatus();
  if (mealStatus[mealKey]) {
    mealStatus[mealKey].eaten = record.meals[info.short].q > 0;
    saveMealStatus();
  }

  mealEditing[mealKey] = false;
  renderMealStatus();
}

function editMealEntry(mealKey) {
  const record = getMyTodayRecord();
  if (record && record.confirmed) return;
  mealEditing[mealKey] = true;
  renderMealStatus();
}

function toggleFeedback(mealKey) {
  feedbackOpen[mealKey] = !feedbackOpen[mealKey];
  renderMealStatus();
}

function completeTodayEntries() {
  const record = getMyTodayRecord();
  if (!record) return;

  const allSaved = MEAL_INFO.every(function (m) { return record.meals[m.short]; });
  if (!allSaved) return;

  record.confirmed = true;
  record.confirmedAt = nowHHMM();
  saveMyTodayRecord(record);
  renderMealStatus();
}

function rate(meal, rating) {
  mealStatus = getMealStatus();
  if (!mealStatus[meal]) return;

  mealStatus[meal].rating = rating;
  saveMealStatus();
  renderMealStatus();
}

/* ==================== FEEDBACK ==================== */

function submitFeedback(meal) {
  if (!currentUser) return;

  const textarea = document.getElementById("fb_" + meal);
  const comment = textarea ? textarea.value.trim() : "";

  mealStatus = getMealStatus();
  if (!mealStatus[meal]) return;

  mealStatus[meal].fb = comment;
  saveMealStatus();

  const feedback = getFeedback();
  const todayMenu = getTodayMenu();

  const newFeedback = {
    user: currentUser.id,
    meal: meal,
    food: todayMenu[meal] || "",
    rating: Number(mealStatus[meal].rating || 0),
    comment: comment,
    date: new Date().toLocaleString("en-IN")
  };

  const existingIndex = feedback.findIndex(function (item) {
    return (
      String(item.user || "").toUpperCase() ===
        String(currentUser.id || "").toUpperCase() &&
      String(item.meal || "").toLowerCase() === meal.toLowerCase()
    );
  });

  if (existingIndex >= 0) {
    feedback[existingIndex] = newFeedback;
  } else {
    feedback.unshift(newFeedback);
  }

  store.set("feedback", feedback);
  renderMealStatus();
}

/* ==================== MONTHLY MESS ENTRY ==================== */

function renderMonthly() {
  const container = document.getElementById("monthlyBody");
  if (!container) return;

  if (!currentUser) {
    container.innerHTML = "";
    return;
  }

  const userId = String(currentUser.id || "").toUpperCase();

  const history = getEntryHistory()
    .filter(function (entry) {
      return String(entry.user || "").toUpperCase() === userId;
    })
    .sort(function (a, b) {
      return b.date.localeCompare(a.date);
    });

  const daysElement = document.getElementById("monthlyDays");
  const mealsElement = document.getElementById("monthlyMeals");

  let totalMeals = 0;

  history.forEach(function (entry) {
    totalMeals +=
      Number(entry.b || 0) +
      Number(entry.l || 0) +
      Number(entry.d || 0);
  });

  if (daysElement) daysElement.textContent = history.length;
  if (mealsElement) mealsElement.textContent = totalMeals;

  if (!history.length) {
    container.innerHTML = `
      <tr>
        <td colspan="5">No meal entries available.</td>
      </tr>
    `;
    return;
  }

  container.innerHTML = history.map(function (entry) {
    const total =
      Number(entry.b || 0) +
      Number(entry.l || 0) +
      Number(entry.d || 0);

    const date = new Date(entry.date + "T00:00:00");

    const formattedDate = date.toLocaleDateString("en-IN", {
      day: "numeric",
      month: "short",
      year: "numeric"
    });

    return `
      <tr>
        <td>${formattedDate}</td>
        <td>${Number(entry.b || 0)}</td>
        <td>${Number(entry.l || 0)}</td>
        <td>${Number(entry.d || 0)}</td>
        <td>${total}</td>
      </tr>
    `;
  }).join("");
}

/* ==================== BILLS ==================== */

/* ==================== NOTIFICATIONS ==================== */

function getReadNotifications() {
  if (!currentUser) return [];

  return store.get("readNotifications_" + currentUser.id, []);
}

function renderNotifs() {
  const list = document.getElementById("notifList");
  const badge = document.getElementById("notifBadge");

  if (!list) return;

  const notifications = getNotifications();
  const readNotifications = getReadNotifications();

  const unreadCount = notifications.filter(function (_, index) {
    return !readNotifications.includes(index);
  }).length;

  if (badge) {
    badge.style.display = unreadCount > 0 ? "flex" : "none";
    badge.textContent = unreadCount;
  }

  if (!notifications.length) {
    list.innerHTML = `<div class="empty">No notifications available.</div>`;
    return;
  }

  list.innerHTML = notifications.map(function (notification, index) {
    const isUnread = !readNotifications.includes(index);

    return `
      <div class="notif-item">
        <div class="nt">
          ${isUnread ? '<span class="dot"></span>' : ""}
          ${notification.t || ""}
        </div>
        <div class="nm">${notification.m || ""}</div>
        <div class="nd">${notification.d || ""}</div>
      </div>
    `;
  }).join("");
}

function markNotifsRead() {
  if (!currentUser) return;

  const notifications = getNotifications();
  const indexes = notifications.map(function (_, index) {
    return index;
  });

  store.set("readNotifications_" + currentUser.id, indexes);
  renderNotifs();
}

/* ==================== SETTINGS ==================== */

function updateSettings() {
  if (!currentUser) return;

  const name = document.getElementById("settingsName");
  const userId = document.getElementById("settingsUserId");
  const room = document.getElementById("settingsRoom");
  const branch = document.getElementById("settingsBranch");
  const status = document.getElementById("settingsStatus");

  if (name) name.textContent = currentUser.name || "";
  if (userId) userId.textContent = currentUser.id || "";
  if (room) room.textContent = currentUser.room || "";
  if (branch) branch.textContent = currentUser.branch || "";

  if (status) {
    status.textContent =
      String(currentUser.status || "").toLowerCase() === "active"
        ? "Active"
        : (currentUser.status || "");
  }
}

/* ==================== CONFIRM MODAL ==================== */

let pendingAction = null;

function confirmAction(action) {
  pendingAction = action;

  const title = document.getElementById("modalTitle");
  const text = document.getElementById("modalText");
  const background = document.getElementById("modalBg");

  if (title) {
    title.textContent = action === "logout" ? "Log out?" : "Switch user?";
  }

  if (text) {
    text.textContent = action === "logout"
      ? "You will need your User ID and password to log back in."
      : "This will log you out so another authorized user can log in.";
  }

  if (background) background.classList.add("open");
}

function closeModal() {
  const background = document.getElementById("modalBg");
  if (background) background.classList.remove("open");
}

function doConfirm() {
  const action = pendingAction;
  closeModal();

  if (action === "logout" || action === "switch") {
    doLogout();
  }
}

/* ==================== PAGE LOAD ==================== */

document.addEventListener("DOMContentLoaded", function () {
  const savedUserId = store.get("currentUserId", "");

  if (savedUserId) {
    const savedUser = findUser(savedUserId);

    if (
      savedUser &&
      String(savedUser.status || "").toLowerCase() !== "inactive"
    ) {
      currentUser = savedUser;

      const login = document.getElementById("login");
      const app = document.getElementById("app");

      if (login) login.classList.remove("active");
      if (app) app.style.display = "block";

      initApp();
      return;
    }
  }

  const login = document.getElementById("login");
  if (login) login.classList.add("active");
});

/* ==================== AUTOMATIC DATE REFRESH ==================== */

function refreshMessEntryDates() {
  if (!currentUser) return;

  renderUserDetails();
  renderYesterdayEntry();
  renderTodayEntry();
  renderQty();
  renderMonthly();

  const active = document.activeElement;
  if (!(active && active.classList && active.classList.contains("fb-input"))) {
    renderMealStatus();
  }
}

setInterval(refreshMessEntryDates, 10000);

document.addEventListener("visibilitychange", function () {
  if (!document.hidden) refreshMessEntryDates();
});

window.addEventListener("focus", refreshMessEntryDates);

window.addEventListener("pageshow", function () {
  refreshMessEntryDates();
});


/* =========================================================
   DETAILED MONTHLY BILLS + PRINT/SAVE AS PDF
   ========================================================= */
function billText(value) {
  return String(value == null ? "" : value).replace(/[&<>"']/g, function(ch) {
    return ({ "&":"&amp;", "<":"&lt;", ">":"&gt;", '"':"&quot;", "'":"&#39;" })[ch];
  });
}
function billMoney(value) {
  const n = Number(value);
  return "₹" + (Number.isFinite(n) ? n : 0).toLocaleString("en-IN", {minimumFractionDigits:2, maximumFractionDigits:2});
}
function getMyBillsForDisplay() {
  if (!currentUser) return [];
  const userId = String(currentUser.id || "").toUpperCase();
  return getBills().filter(function(bill) {
    return String(bill.user || "").toUpperCase() === userId;
  }).sort(function(a,b) {
    return String(b.month || b.billingMonth || "").localeCompare(String(a.month || a.billingMonth || ""));
  });
}
function renderBills() {
  const container = document.getElementById("billList");
  if (!container) return;
  if (!currentUser) { container.innerHTML = ""; return; }
  const myBills = getMyBillsForDisplay();
  if (!myBills.length) {
    container.innerHTML = '<div class="card bill-card"><div class="empty">No monthly bills have been generated for your account yet.</div></div>';
    return;
  }
  container.innerHTML = myBills.map(function(bill,index) {
    const q = bill.quantities || {};
    const charges = bill.foodCharges || {};
    const fine = bill.fine || {};
    const other = bill.otherCharge || {};
    const discount = bill.discount || {};
    const rates = bill.rates || {};
    const subtotal = Number(bill.foodSubtotal !== undefined ? bill.foodSubtotal : bill.amount || 0);
    const finalAmount = Number(bill.finalTotal !== undefined ? bill.finalTotal : bill.amount || 0);
    const status = bill.status === "paid" ? "Paid" : "Pending";
    const adjustmentTotal = Number(fine.amount||0)+Number(bill.maintenanceFee||0)+Number(bill.cookingFee||0)+Number(other.amount||0)-Number(discount.amount||0);
    return '<div class="card bill-card">' +
      '<div class="bill-top" onclick="toggleBill(' + index + ')" style="cursor:pointer">' +
      '<div><div class="bill-month">' + billText(bill.month || bill.billingMonth || "Previous bill") + '</div>' +
      '<div class="bill-amt">' + billMoney(finalAmount) + '</div><small>' + billText(bill.generationStatus || "Generated bill") + (bill.revision > 1 ? ' · Updated v' + bill.revision : '') + '</small></div>' +
      '<span class="status-pill ' + (bill.status || "pending") + '">' + status + '</span></div>' +
      '<div class="bill-breakdown open" id="bd_' + index + '">' +
      '<h3>Bill details</h3>' +
      '<p><strong>Hostel:</strong> MMA Hostel Mount Road<br><strong>Name:</strong> ' + billText(bill.name || currentUser.name || currentUser.id) +
      '<br><strong>User ID:</strong> ' + billText(bill.user) + '<br><strong>Room:</strong> ' + billText(bill.room || currentUser.room || "-") +
      '<br><strong>Branch:</strong> ' + billText(bill.branch || currentUser.branch || "Mount Road") +
      '<br><strong>Billing month:</strong> ' + billText(bill.month || bill.billingMonth || "Previous bill") +
      '<br><strong>Saved entry days:</strong> ' + Number(bill.entryDays || bill.days || 0) + '</p>' +
      '<div class="bill-detail-row"><span>Breakfast: ' + Number(q.breakfast || 0) + ' × ' + billMoney(rates.breakfast || 0) + '</span><strong>' + billMoney(charges.breakfast || 0) + '</strong></div>' +
      '<div class="bill-detail-row"><span>Lunch: ' + Number(q.lunch || 0) + ' × ' + billMoney(rates.lunch || 0) + '</span><strong>' + billMoney(charges.lunch || 0) + '</strong></div>' +
      '<div class="bill-detail-row"><span>Dinner: ' + Number(q.dinner || 0) + ' × ' + billMoney(rates.dinner || 0) + '</span><strong>' + billMoney(charges.dinner || 0) + '</strong></div>' +
      '<div class="bill-detail-row total"><span>Food subtotal</span><strong>' + billMoney(subtotal) + '</strong></div>' +
      '<div class="bill-detail-row"><span>Fine' + (fine.reason ? ': ' + billText(fine.reason) : '') + '</span><strong>' + billMoney(fine.amount || 0) + '</strong></div>' +
      '<div class="bill-detail-row"><span>Maintenance fee</span><strong>' + billMoney(bill.maintenanceFee || 0) + '</strong></div>' +
      '<div class="bill-detail-row"><span>Cooking fee</span><strong>' + billMoney(bill.cookingFee || 0) + '</strong></div>' +
      '<div class="bill-detail-row"><span>Other charge' + (other.reason ? ': ' + billText(other.reason) : '') + '</span><strong>' + billMoney(other.amount || 0) + '</strong></div>' +
      '<div class="bill-detail-row"><span>Discount' + (discount.reason ? ': ' + billText(discount.reason) : '') + '</span><strong>−' + billMoney(discount.amount || 0) + '</strong></div>' +
      '<div class="bill-detail-row total"><span>Final total</span><strong>' + billMoney(finalAmount) + '</strong></div>' +
      '<p class="bill-generated">Generated: ' + billText(bill.generatedAt ? new Date(bill.generatedAt).toLocaleString("en-IN") : "-") +
      (bill.updatedAt ? '<br>Last updated: ' + billText(new Date(bill.updatedAt).toLocaleString("en-IN")) : '') + '</p>' +
      '<button class="btn-primary small" onclick="event.stopPropagation();downloadBillPDF(' + index + ')">⬇ Download PDF / Print</button>' +
      '</div></div>';
  }).join("");
}
function toggleBill(index) {
  const el = document.getElementById("bd_" + index);
  if (el) el.classList.toggle("open");
}
function downloadBillPDF(index) {
  const billsForUser = getMyBillsForDisplay();
  const bill = billsForUser[index];
  if (!bill || !currentUser || String(bill.user).toUpperCase() !== String(currentUser.id).toUpperCase()) {
    alert("This bill is not available for your account.");
    return;
  }
  const q = bill.quantities || {};
  const charges = bill.foodCharges || {};
  const rates = bill.rates || {};
  const fine = bill.fine || {};
  const other = bill.otherCharge || {};
  const discount = bill.discount || {};
  const total = Number(bill.finalTotal !== undefined ? bill.finalTotal : bill.amount || 0);
  const html = '<!doctype html><html><head><meta charset="utf-8"><title>MMA Hostel Bill</title><style>' +
    'body{font-family:Arial,sans-serif;color:#222;margin:32px;line-height:1.5}h1{margin-bottom:4px;color:#39246b}h2{margin-top:26px;border-bottom:1px solid #ddd;padding-bottom:6px}' +
    '.muted{color:#666}.row{display:flex;justify-content:space-between;gap:20px;border-bottom:1px solid #eee;padding:8px 0}.total{font-size:20px;font-weight:bold;border-top:2px solid #333;margin-top:10px;padding-top:12px}' +
    '.meta{display:grid;grid-template-columns:1fr 1fr;gap:6px 20px}.notice{margin-top:28px;color:#777;font-size:12px}@media print{button{display:none}body{margin:12mm}}' +
    '</style></head><body><h1>MMA Hostel Mount Road</h1><div class="muted">Monthly Mess Bill</div><h2>Resident details</h2><div class="meta">' +
    '<div><b>Name:</b> ' + billText(bill.name || currentUser.name || currentUser.id) + '</div><div><b>User ID:</b> ' + billText(bill.user) + '</div>' +
    '<div><b>Room:</b> ' + billText(bill.room || currentUser.room || "-") + '</div><div><b>Branch:</b> ' + billText(bill.branch || currentUser.branch || "Mount Road") + '</div>' +
    '<div><b>Billing month:</b> ' + billText(bill.month || bill.billingMonth || "-") + '</div><div><b>Generated:</b> ' + billText(bill.generatedAt ? new Date(bill.generatedAt).toLocaleString("en-IN") : "-") + '</div></div>' +
    '<h2>Food charges</h2>' +
    '<div class="row"><span>Breakfast (' + Number(q.breakfast||0) + ' units × ' + billMoney(rates.breakfast||0) + ')</span><b>' + billMoney(charges.breakfast||0) + '</b></div>' +
    '<div class="row"><span>Lunch (' + Number(q.lunch||0) + ' units × ' + billMoney(rates.lunch||0) + ')</span><b>' + billMoney(charges.lunch||0) + '</b></div>' +
    '<div class="row"><span>Dinner (' + Number(q.dinner||0) + ' units × ' + billMoney(rates.dinner||0) + ')</span><b>' + billMoney(charges.dinner||0) + '</b></div>' +
    '<div class="row"><span><b>Food subtotal</b></span><b>' + billMoney(bill.foodSubtotal||0) + '</b></div><h2>Other fees and adjustments</h2>' +
    '<div class="row"><span>Individual fine — ' + billText(fine.reason || "No reason provided") + '</span><b>' + billMoney(fine.amount||0) + '</b></div>' +
    '<div class="row"><span>Maintenance fee</span><b>' + billMoney(bill.maintenanceFee||0) + '</b></div>' +
    '<div class="row"><span>Cooking fee</span><b>' + billMoney(bill.cookingFee||0) + '</b></div>' +
    '<div class="row"><span>Other charge — ' + billText(other.reason || "None") + '</span><b>' + billMoney(other.amount||0) + '</b></div>' +
    '<div class="row"><span>Discount — ' + billText(discount.reason || "None") + '</span><b>−' + billMoney(discount.amount||0) + '</b></div>' +
    '<div class="row total"><span>Final amount payable</span><span>' + billMoney(total) + '</span></div>' +
    '<p class="notice">Generated by MMA Hostel Mount Road mess management. This bill reflects the saved calculation snapshot for the selected billing month.</p>' +
    '<button onclick="window.print()">Print / Save as PDF</button><script>window.onload=function(){setTimeout(function(){window.print()},300)};<\/script></body></html>';
  const win = window.open("", "_blank");
  if (!win) {
    alert("Your browser blocked the PDF window. Allow pop-ups for this local site, then try again.");
    return;
  }
  win.document.open();
  win.document.write(html);
  win.document.close();
}
