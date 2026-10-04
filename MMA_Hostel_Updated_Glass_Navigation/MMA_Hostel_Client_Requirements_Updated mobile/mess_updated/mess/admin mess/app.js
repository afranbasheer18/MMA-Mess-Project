/* =========================================================
   HOSTEL MESS - ADMIN APP
   ========================================================= */


/* =========================================================
   SHARED STORAGE
   ========================================================= */

const store = {

  get(key, defaultValue) {

    try {

      const value =
        localStorage.getItem("mma_" + key);

      return value !== null
        ? JSON.parse(value)
        : defaultValue;

    } catch (error) {

      console.error("Storage read error:", error);

      return defaultValue;

    }

  },


  set(key, value) {

    try {

      localStorage.setItem(
        "mma_" + key,
        JSON.stringify(value)
      );

    } catch (error) {

      console.error("Storage write error:", error);

    }

  }

};


/* =========================================================
   ADMIN DATA
   ========================================================= */

let users = store.get("users", []);

let todayMenu = store.get(
  "todayMenu",
  {
    breakfast: "Idly + Sambar",
    lunch: "Chicken Biryani",
    dinner: "Chapati + Chicken Curry"
  }
);

let weekMenu = store.get(
  "weekMenu",
  [
    {
      day: "Mon",
      b: "Idly",
      l: "Veg Biryani",
      d: "Chapati+Paneer"
    },
    {
      day: "Tue",
      b: "Dosa",
      l: "Curd Rice",
      d: "Fried Rice"
    },
    {
      day: "Wed",
      b: "Poori",
      l: "Chicken Biryani",
      d: "Chapati+Curry"
    },
    {
      day: "Thu",
      b: "Upma",
      l: "Sambar Rice",
      d: "Veg Fried Rice"
    },
    {
      day: "Fri",
      b: "Idly+Sambar",
      l: "Mutton Biryani",
      d: "Chapati+Curry"
    },
    {
      day: "Sat",
      b: "Pongal",
      l: "Lemon Rice",
      d: "Parotta+Salna"
    },
    {
      day: "Sun",
      b: "Dosa",
      l: "Special Meals",
      d: "Chapati+Kurma"
    }
  ]
);

let cutoff =
  store.get("cutoffTime", "06:00");

let bills =
  store.get("adminBills", []);

let notifHistory =
  store.get("notifHistory", []);

let feedback =
  store.get("feedback", []);

let editingUserId = null;


/* =========================================================
   DATE HELPERS
   ========================================================= */

function getDateKey(date) {

  const year =
    date.getFullYear();

  const month =
    String(date.getMonth() + 1)
      .padStart(2, "0");

  const day =
    String(date.getDate())
      .padStart(2, "0");

  return (
    year +
    "-" +
    month +
    "-" +
    day
  );

}


function getTargetDate(daysFromToday) {

  const date = new Date();

  date.setHours(
    0,
    0,
    0,
    0
  );

  date.setDate(
    date.getDate() + daysFromToday
  );

  return date;

}


function formatDate(date) {

  return date.toLocaleDateString(
    "en-IN",
    {
      weekday: "long",
      day: "numeric",
      month: "short",
      year: "numeric"
    }
  );

}


/* =========================================================
   GET ALL MESS HISTORY
   ========================================================= */

function getEntryHistory() {

  return store.get(
    "messEntryHistory",
    []
  );

}


/* =========================================================
   GET ENTRIES FOR A SPECIFIC DATE
   ========================================================= */

function getEntriesForDate(dateKey) {

  const history =
    getEntryHistory();

  return history.filter(function(entry) {

    return entry.date === dateKey;

  });

}


/* =========================================================
   LOGIN
   ========================================================= */

function togglePw() {

  const password =
    document.getElementById("pw");

  const button =
    document.getElementById("pwToggle");

  if (!password) {
    return;
  }

  if (
    password.type === "password"
  ) {

    password.type = "text";

    if (button) {
      button.textContent = "Hide";
    }

  } else {

    password.type = "password";

    if (button) {
      button.textContent = "Show";
    }

  }

}


function doLogin() {

  const uid =
    document.getElementById("uid");

  const pw =
    document.getElementById("pw");

  const error =
    document.getElementById("loginErr");

  if (!uid || !pw) {
    return;
  }

  const userId =
    uid.value
      .trim()
      .toUpperCase();

  const password =
    pw.value.trim();

  if (
    userId === "ADMIN01" &&
    password === "admin123"
  ) {

    if (error) {
      error.style.display = "none";
    }

    document
      .getElementById("login")
      .classList.remove("active");

    document
      .getElementById("app")
      .style.display = "block";

    initApp();

  } else {

    if (error) {
      error.style.display = "block";
    }

  }

}


function doLogout() {

  document
    .getElementById("app")
    .style.display = "none";

  document
    .getElementById("login")
    .classList.add("active");

  document
    .getElementById("uid")
    .value = "";

  document
    .getElementById("pw")
    .value = "";

}


/* =========================================================
   NAVIGATION
   ========================================================= */

function openScreen(id) {

  document
    .querySelectorAll("main .screen")
    .forEach(function(screen) {

      screen.classList.remove("active");

    });


  const target =
    document.getElementById(id);


  if (target) {

    target.classList.add("active");

  }


  document
    .querySelectorAll(
      ".side .navbtn[data-s]"
    )
    .forEach(function(button) {

      button.classList.toggle(
        "active",
        button.dataset.s === id
      );

    });


  const side =
    document.querySelector(".side");

  if (side) {
    side.classList.remove("open");
  }

}


function toggleSide() {

  const side =
    document.querySelector(".side");

  if (side) {

    side.classList.toggle("open");

  }

}


/* =========================================================
   INITIALIZE APP
   ========================================================= */

function baseInitApp() {

  renderDashboard();

  renderUsers();

  renderMenu();

  renderEntries();

  renderRecords();

  renderBills();

  renderNotifHistory();

  renderFeedback();

}


/* =========================================================
   DASHBOARD
   ========================================================= */

function renderDashboard() {

  users =
    store.get("users", []);

  bills =
    store.get("adminBills", []);

  feedback =
    store.get("feedback", []);

  const activeUsers =
    users.filter(function(user) {

      return user.status === "active";

    }).length;


  const todayKey =
    getDateKey(
      getTargetDate(0)
    );

  const todayEntries =
    getEntriesForDate(
      todayKey
    );


  const statUsers =
    document.getElementById(
      "statUsers"
    );

  const statEntries =
    document.getElementById(
      "statEntries"
    );

  const statPending =
    document.getElementById(
      "statPending"
    );

  const statFb =
    document.getElementById(
      "statFb"
    );


  if (statUsers) {
    statUsers.textContent =
      activeUsers;
  }

  if (statEntries) {
    statEntries.textContent =
      todayEntries.length;
  }

  if (statPending) {
    statPending.textContent =
      bills.filter(function(bill) {

        return bill.status === "pending";

      }).length;
  }

  if (statFb) {
    statFb.textContent =
      feedback.length;
  }


  const dashMenu =
    document.getElementById(
      "dashMenu"
    );


  if (dashMenu) {

    dashMenu.innerHTML =
      Object.entries(todayMenu)
        .map(function(item) {

          const key = item[0];

          const value = item[1];

          return `
            <div class="fc">

              <div class="meal">
                ${key}
              </div>

              <div class="name">
                ${value}
              </div>

            </div>
          `;

        })
        .join("");

  }

}


/* =========================================================
   USERS
   ========================================================= */

function renderUsers() {

  users =
    store.get("users", []);

  const body =
    document.getElementById(
      "usersBody"
    );

  if (!body) {
    return;
  }


  body.innerHTML =
    users.map(function(user, index) {

      return `
        <tr>

          <td>
            ${user.id}
          </td>

          <td>
            ${user.name}
          </td>

          <td>
            ${user.room}
          </td>

          <td>
            ${user.branch}
          </td>

          <td>
            <span
              class="status-pill ${user.status}"
            >
              ${
                user.status === "active"
                  ? "Active"
                  : "Inactive"
              }
            </span>
          </td>

          <td>

            <button
              class="link-btn"
              onclick="toggleUserStatus(${index})"
            >
              ${
                user.status === "active"
                  ? "Deactivate"
                  : "Activate"
              }
            </button>

          </td>

        </tr>
      `;

    }).join("");

}

/* =========================================================
   MENU
   ========================================================= */

function renderMenu() {

  const todayForm =
    document.getElementById(
      "todayMenuForm"
    );


  if (todayForm) {

    todayForm.innerHTML =
      [
        "breakfast",
        "lunch",
        "dinner"
      ]
      .map(function(meal) {

        return `
          <div class="field">

            <label
              style="text-transform:capitalize"
            >
              ${meal}
            </label>

            <input
              id="tm_${meal}"
              type="text"
              value="${todayMenu[meal]}"
            >

          </div>
        `;

      })
      .join("");

  }


  const weekBody =
    document.getElementById(
      "weekBody"
    );


  if (weekBody) {

    weekBody.innerHTML =
      weekMenu.map(function(day, index) {

        return `
          <tr>

            <td>
              ${day.day}
            </td>

            <td>
              <input
                id="wb_${index}"
                value="${day.b}"
              >
            </td>

            <td>
              <input
                id="wl_${index}"
                value="${day.l}"
              >
            </td>

            <td>
              <input
                id="wd_${index}"
                value="${day.d}"
              >
            </td>

          </tr>
        `;

      }).join("");

  }


  const cutoffInput =
    document.getElementById(
      "cutoffTime"
    );

  if (cutoffInput) {
    cutoffInput.value = cutoff;
  }

}


function saveTodayMenu() {

  [
    "breakfast",
    "lunch",
    "dinner"
  ].forEach(function(meal) {

    todayMenu[meal] =
      document.getElementById(
        "tm_" + meal
      ).value;

  });


  store.set(
    "todayMenu",
    todayMenu
  );


  flash("menuConfirm");

  renderDashboard();

}


function saveWeekMenu() {

  weekMenu.forEach(function(day, index) {

    day.b =
      document.getElementById(
        "wb_" + index
      ).value;

    day.l =
      document.getElementById(
        "wl_" + index
      ).value;

    day.d =
      document.getElementById(
        "wd_" + index
      ).value;

  });


  store.set(
    "weekMenu",
    weekMenu
  );


  flash("weekConfirm");

}


function saveCutoff() {

  cutoff =
    document.getElementById(
      "cutoffTime"
    ).value;

  store.set(
    "cutoffTime",
    cutoff
  );

  flash("cutoffConfirm");

}


/* =========================================================
   MESS ENTRY TOTALS
   ========================================================= */

function calculateTotals(entries) {

  return entries.reduce(
    function(total, entry) {

      total.breakfast +=
        Number(entry.b || 0);

      total.lunch +=
        Number(entry.l || 0);

      total.dinner +=
        Number(entry.d || 0);

      return total;

    },
    {
      breakfast: 0,
      lunch: 0,
      dinner: 0
    }
  );

}


/* =========================================================
   RENDER TODAY + TOMORROW ENTRIES
   ========================================================= */

function renderEntries() {

  const body =
    document.getElementById(
      "entriesBody"
    );

  const totalsBox =
    document.getElementById(
      "entriesTotals"
    );


  if (!body) {
    return;
  }


  /* IMPORTANT:
     Always read fresh data from localStorage.
     This allows the admin page to see
     new entries submitted by users.
  */

  const today =
    getTargetDate(0);

  const tomorrow =
    getTargetDate(1);


  const todayKey =
    getDateKey(today);

  const tomorrowKey =
    getDateKey(tomorrow);


  const todayEntries =
    getEntriesForDate(
      todayKey
    );


  const tomorrowEntries =
    getEntriesForDate(
      tomorrowKey
    );


  const todayTotals =
    calculateTotals(
      todayEntries
    );


  const tomorrowTotals =
    calculateTotals(
      tomorrowEntries
    );


  let html = "";


  /* =====================================================
     TODAY
     ===================================================== */

  html += `

    <tr>
      <td
        colspan="6"
        style="
          font-weight:700;
          font-size:16px;
          padding-top:18px;
        "
      >
        Today's Mess Entries
        <small style="opacity:.7;">
          (${formatDate(today)})
        </small>
      </td>
    </tr>

  `;


  if (todayEntries.length) {

    html +=
      todayEntries.map(function(entry) {

        const total =
          Number(entry.b || 0) +
          Number(entry.l || 0) +
          Number(entry.d || 0);


        return `

          <tr>

            <td>
              ${entry.user}
            </td>

            <td>
              ${entry.room || "-"}
            </td>

            <td>
              ${Number(entry.b || 0)}
            </td>

            <td>
              ${Number(entry.l || 0)}
            </td>

            <td>
              ${Number(entry.d || 0)}
            </td>

            <td>
              <b>${total}</b>
            </td>

          </tr>

        `;

      }).join("");

  } else {

    html += `

      <tr>

        <td
          colspan="6"
          style="text-align:center;"
        >
          No students submitted meals for today.
        </td>

      </tr>

    `;

  }


  /* =====================================================
     TOMORROW
     ===================================================== */

  html += `

    <tr>
      <td
        colspan="6"
        style="
          font-weight:700;
          font-size:16px;
          padding-top:25px;
        "
      >
        Tomorrow's Mess Entries
        <small style="opacity:.7;">
          (${formatDate(tomorrow)})
        </small>
      </td>
    </tr>

  `;


  if (tomorrowEntries.length) {

    html +=
      tomorrowEntries.map(function(entry) {

        const total =
          Number(entry.b || 0) +
          Number(entry.l || 0) +
          Number(entry.d || 0);


        return `

          <tr>

            <td>
              ${entry.user}
            </td>

            <td>
              ${entry.room || "-"}
            </td>

            <td>
              ${Number(entry.b || 0)}
            </td>

            <td>
              ${Number(entry.l || 0)}
            </td>

            <td>
              ${Number(entry.d || 0)}
            </td>

            <td>
              <b>${total}</b>
            </td>

          </tr>

        `;

      }).join("");

  } else {

    html += `

      <tr>

        <td
          colspan="6"
          style="text-align:center;"
        >
          No students submitted meals for tomorrow.
        </td>

      </tr>

    `;

  }


  body.innerHTML = html;


  /* =====================================================
     SEPARATE TOTALS
     ===================================================== */

  if (totalsBox) {

    totalsBox.innerHTML = `

      <div style="margin-bottom:18px;">

        <strong>
          Today's Meal Totals
        </strong>

        <div style="
          display:flex;
          gap:12px;
          flex-wrap:wrap;
          margin-top:8px;
        ">

          <span>
            Breakfast:
            <b>${todayTotals.breakfast}</b>
          </span>

          <span>
            Lunch:
            <b>${todayTotals.lunch}</b>
          </span>

          <span>
            Dinner:
            <b>${todayTotals.dinner}</b>
          </span>

        </div>

        <div style="
          margin-top:6px;
          opacity:.7;
        ">
          ${todayEntries.length}
          ${
            todayEntries.length === 1
              ? "student"
              : "students"
          }
          submitted for today.
        </div>

      </div>


      <div>

        <strong>
          Tomorrow's Meal Totals
        </strong>

        <div style="
          display:flex;
          gap:12px;
          flex-wrap:wrap;
          margin-top:8px;
        ">

          <span>
            Breakfast:
            <b>${tomorrowTotals.breakfast}</b>
          </span>

          <span>
            Lunch:
            <b>${tomorrowTotals.lunch}</b>
          </span>

          <span>
            Dinner:
            <b>${tomorrowTotals.dinner}</b>
          </span>

        </div>

        <div style="
          margin-top:6px;
          opacity:.7;
        ">
          ${tomorrowEntries.length}
          ${
            tomorrowEntries.length === 1
              ? "student"
              : "students"
          }
          submitted for tomorrow.
        </div>

      </div>

    `;

  }

}


/* =========================================================
   AUTO REFRESH MESS ENTRIES
   ========================================================= */

/* AUTO REFRESH MESS ENTRIES */

function refreshAdminEntries() {
  const app = document.getElementById("app");

  if (app && app.style.display !== "none") {
    renderEntries();
    renderRecords();
    renderDashboard();
  }
}

// Refresh entries every 2 seconds
setInterval(refreshAdminEntries, 2000);

// Refresh when returning to the admin tab
document.addEventListener("visibilitychange", function () {
  if (!document.hidden) {
    refreshAdminEntries();
  }
});

window.addEventListener("focus", refreshAdminEntries);


/* =========================================================
   BILLS
   ========================================================= */

/* Legacy bill functions removed: monthly billing is implemented below. */

/* =========================================================
   NOTIFICATIONS
   ========================================================= */

function renderNotifHistory() {

  notifHistory =
    store.get(
      "notifHistory",
      []
    );


  const container =
    document.getElementById(
      "notifHistory"
    );


  if (!container) {
    return;
  }


  container.innerHTML =
    notifHistory.length

      ? notifHistory.map(function(notification) {

          return `

            <div class="nh-item">

              <div class="nt">
                ${notification.t}
              </div>

              <div class="nm">
                ${notification.m}
              </div>

              <div class="nd">
                ${notification.d}
              </div>

            </div>

          `;

        }).join("")

      : `
          <div class="nh-item">
            No notifications sent yet.
          </div>
        `;

}


function sendNotif() {

  const title =
    document
      .getElementById(
        "notifTitle"
      )
      .value
      .trim();

  const message =
    document
      .getElementById(
        "notifMsg"
      )
      .value
      .trim();


  if (!title || !message) {
    return;
  }


  notifHistory.unshift({

    t: title,

    m: message,

    d: "Just now"

  });


  store.set(
    "notifHistory",
    notifHistory
  );


  document
    .getElementById(
      "notifTitle"
    )
    .value = "";

  document
    .getElementById(
      "notifMsg"
    )
    .value = "";


  renderNotifHistory();

  flash("notifConfirm");

}


/* =========================================================
   FEEDBACK
   ========================================================= */

function renderFeedback() {

  feedback =
    store.get(
      "feedback",
      []
    );


  const container =
    document.getElementById(
      "feedbackList"
    );


  if (!container) {
    return;
  }


  container.innerHTML =
    feedback.length

      ? feedback.map(function(item) {

          return `

            <div class="fb-card">

              <div class="fb-head">

                <span>
                  ${item.user} · ${item.meal}
                </span>

                <span>
                  ${item.food}
                </span>

              </div>

              <div class="fb-stars">

                ${
                  "★".repeat(
                    Number(item.rating || 0)
                  )
                }

                ${
                  "☆".repeat(
                    5 -
                    Number(item.rating || 0)
                  )
                }

              </div>

              <div class="fb-comment">
                ${item.comment || "—"}
              </div>

              <div class="fb-meta">
                ${item.date}
              </div>

            </div>

          `;

        }).join("")

      : `
          <div class="fb-card">
            No feedback yet.
          </div>
        `;

}


/* =========================================================
   HELPER
   ========================================================= */

function flash(id) {

  const element =
    document.getElementById(id);

  if (!element) {
    return;
  }

  element.style.display =
    "block";


  setTimeout(function() {

    element.style.display =
      "none";

  }, 1800);

}


/* =========================================================
   PAGE LOAD
   ========================================================= */

document.addEventListener(
  "DOMContentLoaded",
  function() {

    const login =
      document.getElementById(
        "login"
      );

    if (login) {

      login.classList.add(
        "active"
      );

    }

  }
);

/* =========================================================
   MEAL RECORDS (what students actually ate vs expected)
   Reads "mma_mealRecords" written by the student app and
   "messEntryHistory" (the expected quantities).
   ========================================================= */

const REC_MEALS = ["b", "l", "d"];
const REC_MEAL_NAMES = { b: "Breakfast", l: "Lunch", d: "Dinner" };

function recSelectedDateKey() {
  const input = document.getElementById("recDate");
  if (input && !input.value) input.value = getDateKey(getTargetDate(0));
  return input && input.value ? input.value : getDateKey(getTargetDate(0));
}

function recFillSelect(id, values) {
  const select = document.getElementById(id);
  if (!select) return;

  const current = select.value;
  const wanted = [""].concat(values);
  const existing = Array.prototype.map.call(select.options, function (o) { return o.value; });
  if (wanted.join("|") === existing.join("|")) return;

  select.innerHTML = wanted.map(function (v) {
    return `<option value="${v}">${v === "" ? "All" : v}</option>`;
  }).join("");
  select.value = wanted.indexOf(current) >= 0 ? current : "";
}

function recBuildRow(user, dateKey, expectedEntry, record, onlyMeal) {
  const meals = onlyMeal ? [onlyMeal] : REC_MEALS;
  const cells = {};

  REC_MEALS.forEach(function (m) {
    const expected = Number(expectedEntry ? expectedEntry[m] : 0) || 0;
    const saved = record && record.meals ? record.meals[m] : null;
    cells[m] = {
      expected: expected,
      saved: saved ? Number(saved.q) : null,
      time: saved ? saved.t : ""
    };
  });

  const considered = meals.map(function (m) { return cells[m]; });
  const anySaved = considered.some(function (c) { return c.saved !== null; });
  const anyExpected = considered.some(function (c) { return c.expected > 0; });

  let status;
  if (!anySaved && !anyExpected) status = "No meals";
  else if (!anySaved) status = "Missing";
  else {
    const mismatch = considered.some(function (c) {
      return c.saved !== null && c.saved > 0 && c.saved !== c.expected;
    });
    const partial = considered.some(function (c) {
      return c.saved === null ? c.expected > 0 : (c.saved === 0 && c.expected > 0);
    });
    status = mismatch ? "Mismatch" : partial ? "Partial" : "Completed";
  }

  // remarks
  let remarks = "-";
  const allZeroConfirmed =
    record && record.confirmed && REC_MEALS.every(function (m) { return cells[m].saved === 0; });

  if (status === "Missing") {
    remarks = "No entries saved";
  } else if (allZeroConfirmed) {
    remarks = "All meals 0 (confirmed)";
  } else {
    const notes = [];
    meals.forEach(function (m) {
      const c = cells[m];
      const name = REC_MEAL_NAMES[m];
      if (c.saved === null) {
        if (c.expected > 0) notes.push(name + " not saved (expected " + c.expected + ")");
      } else if (c.saved === 0 && c.expected > 0) {
        notes.push(name + " 0 (missed) (expected " + c.expected + ")");
      } else if (c.saved !== c.expected) {
        notes.push(name + " " + c.saved + " (expected " + c.expected + ")");
      }
    });
    if (notes.length) remarks = notes.join("; ");
  }

  return { user: user, cells: cells, status: status, remarks: remarks };
}

function renderRecords() {
  const body = document.getElementById("recordsBody");
  if (!body) return;

  const dateKey = recSelectedDateKey();
  const allUsers = store.get("users", []).filter(function (u) {
    return u.status === "active";
  });

  recFillSelect("fBranch", Array.from(new Set(allUsers.map(function (u) { return u.branch || ""; }).filter(Boolean))).sort());
  recFillSelect("fRoom", Array.from(new Set(allUsers.map(function (u) { return String(u.room || ""); }).filter(Boolean))).sort());

  const fBranch = document.getElementById("fBranch").value;
  const fRoom = document.getElementById("fRoom").value;
  const fMeal = document.getElementById("fMeal").value;
  const fStatus = document.getElementById("fStatus").value;

  const history = getEntriesForDate(dateKey);
  const records = store.get("mealRecords", []).filter(function (r) { return r.date === dateKey; });

  function byUser(list, id) {
    return list.find(function (x) {
      return String(x.user || "").toUpperCase() === String(id || "").toUpperCase();
    }) || null;
  }

  let rows = allUsers
    .filter(function (u) {
      return (!fBranch || u.branch === fBranch) && (!fRoom || String(u.room) === fRoom);
    })
    .map(function (u) {
      return recBuildRow(u, dateKey, byUser(history, u.id), byUser(records, u.id), fMeal);
    });

  const counts = { Completed: 0, Partial: 0, Mismatch: 0, Missing: 0, "No meals": 0 };
  rows.forEach(function (r) { counts[r.status]++; });

  if (fStatus) rows = rows.filter(function (r) { return r.status === fStatus; });

  const cls = { Completed: "completed", Partial: "partial", Mismatch: "mismatch", Missing: "missing", "No meals": "nomeals" };

  const summary = document.getElementById("recSummary");
  if (summary) {
    summary.innerHTML = ["Completed", "Partial", "Mismatch", "Missing"].map(function (s) {
      return `<div class="card stat"><div class="num rs-${cls[s]}">${counts[s]}</div><div class="lbl">${s}</div></div>`;
    }).join("");
  }

  if (!rows.length) {
    body.innerHTML = `<tr><td colspan="15" style="text-align:center;color:var(--sub);padding:24px">No records for this filter.</td></tr>`;
    return;
  }

  const dateText = dateKey.split("-").reverse().join("-");

  body.innerHTML = rows.map(function (r) {
    const u = r.user;
    const mealCells = REC_MEALS.map(function (m) {
      const c = r.cells[m];
      let savedClass = "";
      let savedText = "-";
      if (c.saved !== null) {
        savedText = String(c.saved);
        savedClass = c.saved === c.expected ? "ok" : (c.saved === 0 ? "zero" : "diff");
      }
      return `<td class="c">${c.expected}</td>
              <td class="c sv ${savedClass}">${savedText}</td>
              <td class="c tm">${c.time || "-"}</td>`;
    }).join("");

    return `<tr>
      <td><b>${u.name || u.id}</b></td>
      <td>${u.id}</td>
      <td>${u.branch || "-"}</td>
      <td>${u.room || "-"}</td>
      ${mealCells}
      <td><span class="rs-pill ${cls[r.status]}">${r.status}</span></td>
      <td class="remarks">${r.remarks}</td>
    </tr>`;
  }).join("");
}



/* =========================================================
   SAFE USER CRUD + MONTHLY BILLING (persistent mma_ storage)
   ========================================================= */
let userEditingId = null;
let billSettings = Object.assign({
  rates: { breakfast: 30, lunch: 50, dinner: 40 },
  maintenanceMode: "equal",
  maintenanceTotal: 0,
  cookingMode: "equal",
  cookingTotal: 0
}, store.get("billSettings", {}));
billSettings.rates = Object.assign({ breakfast: 30, lunch: 50, dinner: 40 }, billSettings.rates || {});

function money(value) {
  const n = Number(value);
  return (Number.isFinite(n) ? n : 0).toLocaleString("en-IN", {minimumFractionDigits: 2, maximumFractionDigits: 2});
}
function escBill(value) {
  return String(value == null ? "" : value).replace(/[&<>"']/g, function(ch) {
    return ({ "&":"&amp;", "<":"&lt;", ">":"&gt;", '"':"&quot;", "'":"&#39;" })[ch];
  });
}
function selectedBillMonth() {
  const input = document.getElementById("billMonth");
  if (input && /^\d{4}-\d{2}$/.test(input.value)) return input.value;
  const now = new Date();
  return now.getFullYear() + "-" + String(now.getMonth()+1).padStart(2,"0");
}
function activeBillUsers() {
  return store.get("users", []).filter(function(user) {
    return String(user.status || "active").toLowerCase() === "active";
  });
}
function getMonthEntryQuantities(month) {
  const entries = store.get("messEntryHistory", []);
  const unique = new Map();
  (Array.isArray(entries) ? entries : []).forEach(function(entry) {
    const uid = String(entry.user || "").toUpperCase();
    if (!uid || typeof entry.date !== "string" || !entry.date.startsWith(month + "-")) return;
    // One saved entry per user/day. If legacy duplicate rows exist, keep the last saved row.
    unique.set(uid + "|" + entry.date, entry);
  });
  const totals = {};
  unique.forEach(function(entry) {
    const uid = String(entry.user || "").toUpperCase();
    if (!totals[uid]) totals[uid] = { breakfast: 0, lunch: 0, dinner: 0, days: 0 };
    const vals = { breakfast: entry.b, lunch: entry.l, dinner: entry.d };
    Object.keys(vals).forEach(function(meal) {
      const q = Number(vals[meal]);
      if (Number.isInteger(q) && q >= 0 && q <= 2) totals[uid][meal] += q;
    });
    totals[uid].days += 1;
  });
  return totals;
}
function billAdjustmentKey(month, userId) {
  return month + "|" + String(userId || "").toUpperCase();
}
function getBillAdjustments(month, userId) {
  const all = store.get("billAdjustments", {});
  return Object.assign({
    fineAmount: 0, fineReason: "",
    maintenanceCustom: 0, cookingCustom: 0,
    otherAmount: 0, otherReason: "",
    discountAmount: 0, discountReason: ""
  }, all[billAdjustmentKey(month, userId)] || {});
}
function saveBillAdjustment(month, userId, field, value) {
  const all = store.get("billAdjustments", {});
  const key = billAdjustmentKey(month, userId);
  const row = Object.assign({
    fineAmount: 0, fineReason: "",
    maintenanceCustom: 0, cookingCustom: 0,
    otherAmount: 0, otherReason: "",
    discountAmount: 0, discountReason: ""
  }, all[key] || {});
  if (["fineReason", "otherReason", "discountReason"].includes(field)) {
    row[field] = String(value || "").slice(0, 300);
  } else {
    const amount = Number(value);
    if (!Number.isFinite(amount) || amount < 0) {
      alert("Enter a valid non-negative amount.");
      renderBillCalculator();
      return;
    }
    row[field] = Math.round(amount * 100) / 100;
  }
  all[key] = row;
  store.set("billAdjustments", all);
}
function readBillSettingsFromForm() {
  const val = function(id, fallback) {
    const el = document.getElementById(id);
    const n = el ? Number(el.value) : fallback;
    return Number.isFinite(n) && n >= 0 ? Math.round(n * 100) / 100 : fallback;
  };
  const selectVal = function(id, fallback) {
    const el = document.getElementById(id);
    return el ? el.value : fallback;
  };
  billSettings = {
    rates: {
      breakfast: val("rateBreakfast", billSettings.rates.breakfast),
      lunch: val("rateLunch", billSettings.rates.lunch),
      dinner: val("rateDinner", billSettings.rates.dinner)
    },
    maintenanceMode: selectVal("maintenanceMode", billSettings.maintenanceMode || "equal"),
    maintenanceTotal: val("maintenanceTotal", billSettings.maintenanceTotal || 0),
    cookingMode: selectVal("cookingMode", billSettings.cookingMode || "equal"),
    cookingTotal: val("cookingTotal", billSettings.cookingTotal || 0)
  };
  store.set("billSettings", billSettings);
}
function saveBillSettings() {
  readBillSettingsFromForm();
}
function calcBillForUser(user, month, quantities, activeCount) {
  const q = quantities[String(user.id || "").toUpperCase()] || {breakfast:0,lunch:0,dinner:0,days:0};
  const a = getBillAdjustments(month, user.id);
  const rates = billSettings.rates;
  const foodCharges = {
    breakfast: q.breakfast * rates.breakfast,
    lunch: q.lunch * rates.lunch,
    dinner: q.dinner * rates.dinner
  };
  const foodSubtotal = foodCharges.breakfast + foodCharges.lunch + foodCharges.dinner;
  const maintenance = billSettings.maintenanceMode === "equal"
    ? (activeCount ? billSettings.maintenanceTotal / activeCount : 0)
    : Number(a.maintenanceCustom || 0);
  const cooking = billSettings.cookingMode === "equal"
    ? (activeCount ? billSettings.cookingTotal / activeCount : 0)
    : Number(a.cookingCustom || 0);
  const fine = Number(a.fineAmount || 0);
  const other = Number(a.otherAmount || 0);
  const discount = Number(a.discountAmount || 0);
  const rawTotal = foodSubtotal + fine + maintenance + cooking + other - discount;
  const finalTotal = Math.max(0, Math.round(rawTotal * 100) / 100);
  return {
    user: user.id, name: user.name || user.id, room: user.room || "",
    branch: user.branch || "Mount Road", accountType: user.type || user.role || "student",
    month: month, quantities: {breakfast:q.breakfast,lunch:q.lunch,dinner:q.dinner},
    entryDays: q.days || 0, rates: Object.assign({}, rates),
    foodCharges: foodCharges, foodSubtotal: Math.round(foodSubtotal*100)/100,
    fine: {amount:fine, reason:String(a.fineReason || "")},
    maintenanceFee: Math.round(maintenance*100)/100,
    cookingFee: Math.round(cooking*100)/100,
    otherCharge: {amount:other, reason:String(a.otherReason || "")},
    discount: {amount:discount, reason:String(a.discountReason || "")},
    amount: finalTotal, finalTotal: finalTotal,
    status: "pending", generatedAt: new Date().toISOString(),
    revision: 1, calculationVersion: 2
  };
}
function updateBillPreviewMessage(message) {
  const el = document.getElementById("billPreviewMessage");
  if (el) el.textContent = message || "";
}
function renderBillCalculator() {
  const monthInput = document.getElementById("billMonth");
  if (monthInput && !monthInput.value) monthInput.value = selectedBillMonth();
  const month = selectedBillMonth();
  const usersNow = activeBillUsers();
  const quantities = getMonthEntryQuantities(month);
  const body = document.getElementById("billCalcBody");
  if (!body) return;
  if (!usersNow.length) {
    body.innerHTML = '<tr><td colspan="15">No active users found. Create or activate a user first.</td></tr>';
    return;
  }
  const fmtNum = n => String(Math.round((Number(n)||0)*100)/100);
  body.innerHTML = usersNow.map(function(user) {
    const uid = String(user.id || "").toUpperCase();
    const q = quantities[uid] || {breakfast:0,lunch:0,dinner:0,days:0};
    const a = getBillAdjustments(month, user.id);
    const preview = calcBillForUser(user, month, quantities, usersNow.length);
    const field = function(name, value, type, label) {
      const numeric = type === "number";
      return '<input class="bill-adjust-input" aria-label="' + escBill(label) + '" type="' + type + '" ' +
        (numeric ? 'min="0" step="0.01" ' : '') +
        'value="' + escBill(value) + '" onchange="saveBillAdjustment(\'' + escBill(month) + '\',\'' + escBill(uid) + '\',\'' + name + '\',this.value);renderBillCalculator()" />';
    };
    const maintenanceCell = billSettings.maintenanceMode === "custom"
      ? field("maintenanceCustom", a.maintenanceCustom, "number", "Custom maintenance fee") : money(preview.maintenanceFee) + '<small>equal share</small>';
    const cookingCell = billSettings.cookingMode === "custom"
      ? field("cookingCustom", a.cookingCustom, "number", "Custom cooking fee") : money(preview.cookingFee) + '<small>equal share</small>';
    return '<tr>' +
      '<td><strong>' + escBill(user.name || uid) + '</strong><small>' + escBill(uid) + '</small></td>' +
      '<td>' + escBill(user.room || "-") + '</td>' +
      '<td>' + q.breakfast + '</td><td>' + q.lunch + '</td><td>' + q.dinner + '</td>' +
      '<td>₹' + money(preview.foodSubtotal) + '<small>' + q.days + ' saved days</small></td>' +
      '<td>' + field("fineAmount", a.fineAmount, "number", "Individual fine") + '</td>' +
      '<td>' + field("fineReason", a.fineReason, "text", "Fine reason") + '</td>' +
      '<td>' + maintenanceCell + '</td><td>' + cookingCell + '</td>' +
      '<td>' + field("otherAmount", a.otherAmount, "number", "Other charge amount") + '</td>' +
      '<td>' + field("otherReason", a.otherReason, "text", "Other charge description") + '</td>' +
      '<td>' + field("discountAmount", a.discountAmount, "number", "Discount amount") + '</td>' +
      '<td>' + field("discountReason", a.discountReason, "text", "Discount description") + '</td>' +
      '<td><strong>₹' + money(preview.finalTotal) + '</strong></td>' +
      '</tr>';
  }).join("");
  const count = Object.keys(quantities).length;
  updateBillPreviewMessage("Preview for " + month + ": " + usersNow.length + " active user(s). Based on " + count + " user(s) with saved entries. No unsaved entries or random quantities are included.");
  renderBills();
}
function generateBills() {
  readBillSettingsFromForm();
  const month = selectedBillMonth();
  const usersNow = activeBillUsers();
  if (!usersNow.length) { alert("There are no active users to bill."); return; }
  if (!/^\d{4}-\d{2}$/.test(month)) { alert("Select a valid billing month."); return; }
  const existingBills = store.get("adminBills", []);
  const monthExisting = existingBills.filter(b => b.month === month || b.billingMonth === month);
  if (monthExisting.length && !confirm("Bills already exist for " + month + ". Update these bills using the latest saved entries and rates? Existing paid/pending status will be retained.")) return;
  const quantities = getMonthEntryQuantities(month);
  const stamp = new Date().toISOString();
  const generated = usersNow.map(function(user) {
    const fresh = calcBillForUser(user, month, quantities, usersNow.length);
    const oldIndex = existingBills.findIndex(b => String(b.user || "").toUpperCase() === String(user.id || "").toUpperCase() && (b.month === month || b.billingMonth === month));
    if (oldIndex >= 0) {
      const archive = store.get("adminBillHistory", []);
      const previous = Object.assign({}, existingBills[oldIndex], {
        archivedAt: stamp,
        archivedReason: "Previous snapshot before regeneration"
      });
      archive.push(previous);
      store.set("adminBillHistory", archive);
      fresh.status = existingBills[oldIndex].status || "pending";
      fresh.paidAt = existingBills[oldIndex].paidAt || null;
      fresh.revision = Number(existingBills[oldIndex].revision || 1) + 1;
      fresh.updatedAt = stamp;
      fresh.generationStatus = "Updated";
      existingBills[oldIndex] = Object.assign({}, existingBills[oldIndex], fresh);
    } else {
      fresh.generationStatus = "Generated";
      existingBills.push(fresh);
    }
    return fresh;
  });
  store.set("adminBills", existingBills);
  bills = existingBills;
  renderBills();
  renderDashboard();
  renderBillCalculator();
  updateBillPreviewMessage("Successfully generated/updated " + generated.length + " bill(s) for " + month + ". Each bill stores its own rates and fee breakdown.");
}
function renderBills() {
  bills = store.get("adminBills", []);
  const body = document.getElementById("billsBody");
  if (!body) return;
  const month = selectedBillMonth();
  const monthBills = bills.filter(function(b) { return b.month === month || b.billingMonth === month; });
  if (!monthBills.length) {
    body.innerHTML = '<tr><td colspan="9">No bills generated for ' + escBill(month) + ' yet.</td></tr>';
    return;
  }
  body.innerHTML = monthBills.map(function(bill) {
    const quantities = bill.quantities || {};
    const q = quantities.breakfast !== undefined
      ? [quantities.breakfast, quantities.lunch, quantities.dinner]
      : [0,0,0];
    const adjustmentTotal = Number(bill.fine && bill.fine.amount || 0) + Number(bill.maintenanceFee || 0) + Number(bill.cookingFee || 0) + Number(bill.otherCharge && bill.otherCharge.amount || 0) - Number(bill.discount && bill.discount.amount || 0);
    const status = bill.status === "paid" ? "Paid" : "Pending";
    return '<tr><td>' + escBill(bill.month || bill.billingMonth) + '</td>' +
      '<td><strong>' + escBill(bill.name || bill.user) + '</strong><small>' + escBill(bill.user) + '</small></td>' +
      '<td>' + q.join(" / ") + '</td><td>₹' + money(bill.foodSubtotal || 0) + '</td>' +
      '<td>₹' + money(adjustmentTotal) + '</td><td><strong>₹' + money(bill.finalTotal !== undefined ? bill.finalTotal : bill.amount) + '</strong></td>' +
      '<td><span class="status-pill ' + (bill.status || "pending") + '">' + status + '</span></td>' +
      '<td>' + escBill(bill.updatedAt ? "Updated " + new Date(bill.updatedAt).toLocaleString("en-IN") : (bill.generatedAt ? new Date(bill.generatedAt).toLocaleString("en-IN") : "-")) + ' <small>' + escBill(bill.generationStatus || "") + (bill.revision > 1 ? " · v" + bill.revision : "") + '</small></td>' +
      '<td>' + (bill.status !== "paid" ? '<button class="link-btn" onclick="markPaidByKey(\'' + escBill(bill.user) + '\',\'' + escBill(bill.month || bill.billingMonth) + '\')">Mark Paid</button>' : "—") + '</td></tr>';
  }).join("");
  const archiveBody = document.getElementById("billArchiveBody");
  if (archiveBody) {
    const archived = store.get("adminBillHistory", []).slice().reverse();
    archiveBody.innerHTML = archived.length ? archived.map(function(old) {
      return '<tr><td>' + escBill(old.archivedAt ? new Date(old.archivedAt).toLocaleString("en-IN") : "-") +
        '</td><td>' + escBill(old.month || old.billingMonth || "-") +
        '</td><td>' + escBill(old.name || old.user || "-") + '<small>' + escBill(old.user || "") +
        '</small></td><td>₹' + money(old.finalTotal !== undefined ? old.finalTotal : old.amount || 0) +
        '</td><td>v' + escBill(old.revision || 1) + '</td></tr>';
    }).join("") : '<tr><td colspan="5">No previous bill versions archived yet.</td></tr>';
  }
}
function markPaidByKey(userId, month) {
  const all = store.get("adminBills", []);
  const bill = all.find(b => String(b.user || "").toUpperCase() === String(userId).toUpperCase() && (b.month === month || b.billingMonth === month));
  if (!bill) return;
  bill.status = "paid";
  bill.paidAt = new Date().toISOString();
  store.set("adminBills", all);
  bills = all;
  renderBills();
  renderDashboard();
}
function markPaid(index) {
  const all = store.get("adminBills", []);
  const bill = all[index];
  if (bill) {
    bill.status = "paid";
    bill.paidAt = new Date().toISOString();
    store.set("adminBills", all);
    renderBills();
    renderDashboard();
  }
}

/* User CRUD */
function renderUsers() {
  users = store.get("users", []);
  const body = document.getElementById("usersBody");
  if (!body) return;
  if (!users.length) {
    body.innerHTML = '<tr><td colspan="6">No users yet. Select Add User to create an account.</td></tr>';
    return;
  }
  body.innerHTML = users.map(function(user) {
    const id = String(user.id || "");
    const status = String(user.status || "active").toLowerCase();
    return '<tr><td>' + escBill(id) + '</td><td>' + escBill(user.name || "") + '<small>' + escBill(user.type || user.role || "student") + '</small></td><td>' + escBill(user.room || "-") + '</td><td>' + escBill(user.branch || "Mount Road") + '</td><td><span class="status-pill ' + status + '">' + (status === "active" ? "Active" : "Inactive") + '</span></td><td class="user-actions"><button class="link-btn" onclick="viewUser(\'' + escBill(id) + '\')">View</button><button class="link-btn" onclick="editUser(\'' + escBill(id) + '\')">Edit</button><button class="link-btn danger-link" onclick="deleteUser(\'' + escBill(id) + '\')">Delete</button><button class="link-btn" onclick="toggleUserStatusById(\'' + escBill(id) + '\')">' + (status === "active" ? "Deactivate" : "Activate") + '</button></td></tr>';
  }).join("");
}
function openUserForm() {
  userEditingId = null;
  ["nuId","nuName","nuPw","nuRoom"].forEach(id => { const el = document.getElementById(id); if (el) el.value = ""; });
  document.getElementById("nuBranch").value = "Mount Road";
  document.getElementById("nuType").value = "student";
  document.getElementById("nuStatus").value = "active";
  document.getElementById("nuId").disabled = false;
  document.getElementById("userModalTitle").textContent = "Create User";
  document.getElementById("saveUserButton").textContent = "Create User";
  document.getElementById("userModalBg").classList.add("open");
}
function editUser(id) {
  const user = store.get("users", []).find(u => String(u.id).toUpperCase() === String(id).toUpperCase());
  if (!user) return alert("User not found.");
  userEditingId = user.id;
  document.getElementById("nuId").value = user.id || "";
  document.getElementById("nuId").disabled = true;
  document.getElementById("nuName").value = user.name || "";
  document.getElementById("nuPw").value = "";
  document.getElementById("nuRoom").value = user.room || "";
  document.getElementById("nuBranch").value = user.branch || "Mount Road";
  document.getElementById("nuType").value = user.type || user.role || "student";
  document.getElementById("nuStatus").value = user.status || "active";
  document.getElementById("userModalTitle").textContent = "Edit User · " + user.id;
  document.getElementById("saveUserButton").textContent = "Update User";
  document.getElementById("userModalBg").classList.add("open");
}
function viewUser(id) {
  const user = store.get("users", []).find(u => String(u.id).toUpperCase() === String(id).toUpperCase());
  if (!user) return alert("User not found.");
  alert("User details\\n\\nName: " + (user.name || "-") + "\\nUser ID: " + user.id + "\\nType: " + (user.type || user.role || "student") + "\\nRoom: " + (user.room || "-") + "\\nBranch: " + (user.branch || "Mount Road") + "\\nStatus: " + (user.status || "active"));
}
function saveUser() {
  const id = document.getElementById("nuId").value.trim().toUpperCase();
  const name = document.getElementById("nuName").value.trim();
  const pw = document.getElementById("nuPw").value;
  const room = document.getElementById("nuRoom").value.trim();
  const branch = document.getElementById("nuBranch").value.trim();
  const type = document.getElementById("nuType").value;
  const status = document.getElementById("nuStatus").value;
  if (!id || !name || !branch) return alert("User ID, name, and branch are required.");
  if (!userEditingId && !pw.trim()) return alert("Set a password for the new account.");
  const all = store.get("users", []);
  if (!userEditingId && all.some(u => String(u.id).toUpperCase() === id)) return alert("That User ID already exists.");
  if (userEditingId) {
    const user = all.find(u => String(u.id).toUpperCase() === String(userEditingId).toUpperCase());
    if (!user) return alert("This account no longer exists.");
    user.name = name; user.room = room; user.branch = branch; user.type = type; user.role = type; user.status = status;
    if (pw.trim()) user.pw = pw;
  } else {
    all.push({id:id, name:name, pw:pw, room:room, branch:branch, type:type, role:type, status:status});
  }
  store.set("users", all);
  users = all;
  renderUsers(); renderDashboard(); closeUserForm();
}
function deleteUser(id) {
  const all = store.get("users", []);
  const user = all.find(u => String(u.id).toUpperCase() === String(id).toUpperCase());
  if (!user) return alert("User not found.");
  if (!confirm("Delete account " + user.id + " (" + (user.name || "user") + ")? This removes the login account. Existing generated bills and meal history will be retained.")) return;
  store.set("users", all.filter(u => String(u.id).toUpperCase() !== String(id).toUpperCase()));
  users = store.get("users", []);
  renderUsers(); renderDashboard(); renderBillCalculator();
}
function toggleUserStatusById(id) {
  const all = store.get("users", []);
  const user = all.find(u => String(u.id).toUpperCase() === String(id).toUpperCase());
  if (!user) return;
  user.status = String(user.status || "active").toLowerCase() === "active" ? "inactive" : "active";
  store.set("users", all);
  users = all; renderUsers(); renderDashboard(); renderBillCalculator();
}
function toggleUserStatus(index) {
  const all = store.get("users", []);
  if (!all[index]) return;
  toggleUserStatusById(all[index].id);
}
function closeUserForm() {
  const modal = document.getElementById("userModalBg");
  if (modal) modal.classList.remove("open");
  const id = document.getElementById("nuId");
  if (id) id.disabled = false;
  userEditingId = null;
}

/* Ensure the billing controls reflect persisted settings on initial render. */
const originalInitAppForBilling = baseInitApp;
function initApp() {
  billSettings = Object.assign({
    rates: {breakfast:30,lunch:50,dinner:40},
    maintenanceMode:"equal", maintenanceTotal:0,
    cookingMode:"equal", cookingTotal:0
  }, store.get("billSettings", {}));
  billSettings.rates = Object.assign({breakfast:30,lunch:50,dinner:40}, billSettings.rates || {});
  originalInitAppForBilling();
  const now = new Date();
  const monthEl = document.getElementById("billMonth");
  if (monthEl && !monthEl.value) monthEl.value = now.getFullYear() + "-" + String(now.getMonth()+1).padStart(2,"0");
  ["rateBreakfast","rateLunch","rateDinner"].forEach((id,i) => {
    const el = document.getElementById(id);
    if (el) el.value = [billSettings.rates.breakfast,billSettings.rates.lunch,billSettings.rates.dinner][i];
  });
  ["maintenanceMode","cookingMode","maintenanceTotal","cookingTotal"].forEach(id => {
    const el = document.getElementById(id);
    if (el && billSettings[id] !== undefined) el.value = billSettings[id];
  });
  renderBillCalculator();
}
