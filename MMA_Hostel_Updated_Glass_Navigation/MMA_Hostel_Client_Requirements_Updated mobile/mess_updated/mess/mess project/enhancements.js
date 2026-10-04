/* MMA Hostel user enhancements - consolidated fixes */
(function () {
  "use strict";

  const PREFIX = "mma_";
  const read = (key, fallback) => {
    try {
      const raw = localStorage.getItem(PREFIX + key);
      return raw == null ? fallback : JSON.parse(raw);
    } catch (_) { return fallback; }
  };
  const write = (key, value) => {
    try { localStorage.setItem(PREFIX + key, JSON.stringify(value)); } catch (_) {}
  };
  const uid = () => String(read("currentUserId", "") || "").toUpperCase();
  const escapeHTML = value => String(value ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;","\"":"&quot;","'":"&#39;"}[c]));
  const user = () => {
    const id = uid();
    return read("users", []).find(u => String(u.id || "").toUpperCase() === id) || null;
  };
  const pad = n => String(n).padStart(2, "0");
  const today = () => { const d = new Date(); d.setHours(0,0,0,0); return d; };
  const keyFor = d => `${d.getFullYear()}-${pad(d.getMonth()+1)}-${pad(d.getDate())}`;
  const target = n => { const d=today(); d.setDate(d.getDate()+n); return d; };
  const formatTime = value => {
    const parts = String(value || "06:00").split(":");
    let h = Number(parts[0] || 0); const m = parts[1] || "00";
    const suffix = h >= 12 ? "PM" : "AM"; h = h % 12 || 12;
    return `${h}:${m} ${suffix}`;
  };
  const nowMinutes = () => { const d=new Date(); return d.getHours()*60+d.getMinutes(); };
  const timeMinutes = value => { const p=String(value||"06:00").split(":"); return Number(p[0]||0)*60+Number(p[1]||0); };
  const isCutoffClosed = () => nowMinutes() >= timeMinutes(read("cutoffTime", "06:00"));

  function applyTheme() {
    const saved = read("theme", "system");
    document.documentElement.removeAttribute("data-theme");
    if (saved === "dark" || saved === "light") document.documentElement.dataset.theme = saved;
  }

  function toggleTheme() {
    const current = document.documentElement.dataset.theme || "light";
    const next = current === "dark" ? "light" : "dark";
    write("theme", next); applyTheme(); updateThemeButton();
  }
  function updateThemeButton() {
    const isDark = document.documentElement.dataset.theme === "dark";
    const text = isDark ? "☀️" : "🌙";
    const label = isDark ? "Switch to light mode" : "Switch to dark mode";
    const b = document.getElementById("themeToggleBtn");
    const hb = document.getElementById("themeHeaderBtn");
    if (b) {
      b.textContent = isDark ? "☀️ Light mode" : "🌙 Dark mode";
      b.setAttribute("aria-label", label);
    }
    if (hb) {
      hb.textContent = text;
      hb.setAttribute("aria-label", label);
      hb.setAttribute("title", label);
    }
  }
  window.toggleTheme = toggleTheme;

  function notificationAudience(n) {
    if (!n) return false;
    return !n.userId || String(n.userId).toUpperCase() === uid() || n.audience === "all" || n.audience === "users";
  }
  function getNotificationsForUser() {
    const all=read("notifHistory", []); return Array.isArray(all) ? all.filter(notificationAudience) : [];
  }
  function getRead() { return read("readNotifications_" + uid(), []); }
  function setRead(ids) { write("readNotifications_" + uid(), ids); }
  function markNotificationRead(id) {
    const ids=getRead(); if (!ids.includes(id)) { ids.push(id); setRead(ids); }
  }
  function addNotification(title, message, targetScreen, userId, dedupeKey) {
    const all=read("notifHistory", []);
    const list=Array.isArray(all)?all:[];
    if (dedupeKey && list.some(n => n.dedupeKey === dedupeKey && (!userId || n.userId === userId))) return;
    list.unshift({
      id: "NTF-" + Date.now() + "-" + Math.random().toString(36).slice(2,7),
      t:title, m:message, d:new Date().toLocaleString("en-IN"),
      target:targetScreen || "home", userId:userId || null, audience:userId ? "user" : "users",
      dedupeKey:dedupeKey || null, createdAt:new Date().toISOString()
    });
    write("notifHistory", list);
  }
  window.mmaAddNotification = addNotification;

  function renderNotifications() {
    const list=document.getElementById("notifList"); const badge=document.getElementById("notifBadge");
    if (!list) return;
    const notifications=getNotificationsForUser(); const read=getRead();
    const unread=notifications.filter(n => !read.includes(n.id || (n.d + n.t))).length;
    if (badge) { badge.textContent=unread; badge.style.display=unread ? "flex" : "none"; }
    const markAll=document.getElementById("markAllNotificationsBtn");
    if (markAll) markAll.disabled=!unread;
    if (!notifications.length) { list.innerHTML='<div class="empty">No notifications available.</div>'; return; }
    list.innerHTML=notifications.map((n, index) => {
      const id=n.id || (n.d + n.t + index); const isUnread=!read.includes(id);
      return `<button class="notif-item ${isUnread ? "is-unread" : ""}" data-notif-id="${id}" data-target="${n.target || "home"}" type="button">
        <div class="nt">${isUnread ? '<span class="dot"></span>' : ""}${escapeHTML(n.t || "Update")}</div>
        <div class="nm">${escapeHTML(n.m || "")}</div><div class="nd">${escapeHTML(n.d || "")}</div>
      </button>`;
    }).join("");
    list.querySelectorAll(".notif-item").forEach(btn => btn.addEventListener("click", function(){
      const id=this.dataset.notifId; markNotificationRead(id); renderNotifications();
      if (typeof window.openScreen === "function") window.openScreen(this.dataset.target || "home");
    }));
  }
  function markAllNotificationsRead() { const ids=getNotificationsForUser().map((n,i)=>n.id || (n.d+n.t+i)); setRead(ids); renderNotifications(); }
  window.markNotifsRead = renderNotifications;
  window.renderNotifs = renderNotifications;

  function ensureNotificationControls() {
    const section=document.getElementById("notifs");
    if (section && !document.getElementById("markAllNotificationsBtn")) {
      const title=section.querySelector(".section-title");
      if (title) {
        const b=document.createElement("button"); b.id="markAllNotificationsBtn"; b.className="btn-secondary small notif-mark-all"; b.type="button"; b.textContent="Mark all read";
        b.addEventListener("click", markAllNotificationsRead); title.appendChild(b);
      }
    }
  }

  function addBackButtons() {
    const targets={mess:"home",monthly:"more",bill:"home",notifs:"home",more:"home",settings:"more",clientRequests:"more"};
    Object.keys(targets).forEach(id=>{
      const s=document.getElementById(id); if (!s || s.querySelector(".mma-back")) return;
      const b=document.createElement("button"); b.className="back mma-back"; b.type="button"; b.textContent="← Back";
      b.addEventListener("click", () => { window.__mmaBack=true; window.openScreen(targets[id]); });
      s.insertBefore(b, s.firstChild);
    });
  }

  const baseOpenScreen=window.openScreen;
  let history=Array.isArray(window.__mmaScreenHistory) ? window.__mmaScreenHistory : [];
  window.openScreen=function(id){
    if (!id) return;
    const current=document.querySelector("main .screen.active")?.id;
    if (!window.__mmaBack && current && current !== id) history.push(current);
    if (window.__mmaBack) { history = history.filter((v,i,a)=>i===a.length-1 || v!==id); window.__mmaBack=false; }
    window.__mmaScreenHistory=history;
    if (typeof baseOpenScreen === "function") baseOpenScreen(id);
    if (id === "notifs") renderNotifications();
    if (id === "settings") { ensureThemeSetting(); updateThemeButton(); }
    updateUserActivity();
  };

  function updateUserActivity() {
    const id=uid(); if (!id) return; const users=read("users", []); const i=users.findIndex(u=>String(u.id||"").toUpperCase()===id);
    if (i<0) return; users[i].lastActivityAt=new Date().toISOString(); write("users",users);
  }

  function ensureThemeSetting() {
    const settings=document.getElementById("settings"); if (!settings || document.getElementById("themeSettingCard")) return;
    const card=document.createElement("div"); card.id="themeSettingCard"; card.className="card theme-card";
    card.innerHTML='<div><b>Appearance</b><div class="theme-help">Your theme preference is saved on this device.</div></div><button id="themeToggleBtn" class="btn-secondary small" type="button"></button>';
    settings.appendChild(card); card.querySelector("button").addEventListener("click",toggleTheme); updateThemeButton();
  }

  function updateCutoffUI() {
    const value=read("cutoffTime", "06:00");
    const display=document.getElementById("cutoffTimeDisplay"); if (display) display.textContent=formatTime(value);
    const closed=isCutoffClosed();
    const submit=document.getElementById("tomorrowSubmitBtn"); const edit=document.getElementById("tomorrowEditBtn"); const note=document.querySelector(".cutoff-note");
    if (note) note.innerHTML=closed ? `Mess entry closed at <span>${escapeHTML(formatTime(value))}</span>.` : `Mess entry closes at <span>${escapeHTML(formatTime(value))}</span>.`;
    if (submit && submit.dataset.mmaClosed !== "1") submit.disabled=closed;
    if (edit && edit.dataset.mmaClosed !== "1") edit.disabled=closed;
    if (note) note.classList.toggle("closed", closed);
  }

  function renderTomorrow() {
    if (!window.currentUser && typeof currentUser === "undefined") return;
    const c=document.getElementById("qtyRows"); if (!c) return;
    const d=target(1); const label=document.getElementById("tomorrowEntryDate"); if(label) label.textContent=`(${d.toLocaleDateString("en-IN",{weekday:"long",day:"numeric",month:"short"})})`;
    const hist=read("messEntryHistory", []); const u=user(); if(!u) return;
    const entry=hist.find(e=>String(e.user||"").toUpperCase()===String(u.id).toUpperCase() && e.date===keyFor(d));
    const q={breakfast:Number(entry?.b||0),lunch:Number(entry?.l||0),dinner:Number(entry?.d||0)};
    const closed=isCutoffClosed(); const submitted=!!entry;
    ["breakfast","lunch","dinner"].forEach(meal=>{ if (typeof qty !== "undefined") qty[meal]=q[meal]; });
    c.innerHTML=["breakfast","lunch","dinner"].map(meal=>`<div class="qty-row"><div class="qty-label" style="text-transform:capitalize">${meal}</div><div class="qty-ctrl"><button ${closed||submitted?"disabled":""} onclick="changeQty('${meal}',-1)">−</button><span class="val" id="qv_${meal}">${q[meal]}</span><button ${closed||submitted?"disabled":""} onclick="changeQty('${meal}',1)">+</button></div></div>`).join("");
    const confirmation=document.getElementById("entryConfirm"), submit=document.getElementById("tomorrowSubmitBtn"), edit=document.getElementById("tomorrowEditBtn");
    if(confirmation) confirmation.style.display=submitted?"block":"none";
    if(submit){submit.style.display=submitted?"none":"block";submit.disabled=closed;}
    if(edit){edit.style.display=submitted&&!closed?"block":"none";edit.disabled=closed;}
    updateCutoffUI();
  }

  window.renderQty=renderTomorrow;
  window.changeQty=function(meal,diff){ if(isCutoffClosed()) return; if(typeof qty==='undefined') return; qty[meal]=Math.max(0,Math.min(2,Number(qty[meal]||0)+diff)); const el=document.getElementById("qv_"+meal); if(el) el.textContent=qty[meal]; };
  window.editTomorrowEntry=function(){ if(isCutoffClosed()) return; if(typeof tomorrowEditMode!=='undefined') tomorrowEditMode=true; if(typeof submitted!=='undefined') submitted=false; renderTomorrow(); };
  window.submitEntry=function(){
    if(isCutoffClosed()){ updateCutoffUI(); alert("Mess entry is closed for today. The cutoff is " + formatTime(read("cutoffTime","06:00")) + "."); return; }
    const u=user(); if(!u) return; const tomorrowKey=keyFor(target(1)); let hist=read("messEntryHistory", []); if(!Array.isArray(hist)) hist=[];
    const entry={user:u.id,room:u.room||"",date:tomorrowKey,b:Number(qty?.breakfast||0),l:Number(qty?.lunch||0),d:Number(qty?.dinner||0)};
    const idx=hist.findIndex(e=>String(e.user||"").toUpperCase()===String(u.id).toUpperCase()&&e.date===tomorrowKey); if(idx>=0) hist[idx]=entry; else hist.push(entry); write("messEntryHistory",hist);
    let adminEntries=read("tomorrowEntries",[]); if(!Array.isArray(adminEntries)) adminEntries=[]; const ai=adminEntries.findIndex(e=>String(e.user||"").toUpperCase()===String(u.id).toUpperCase()); const ae={user:u.id,room:u.room||"",b:entry.b,l:entry.l,d:entry.d}; if(ai>=0) adminEntries[ai]=ae; else adminEntries.push(ae); write("tomorrowEntries",adminEntries);
    if(typeof tomorrowEditMode!=='undefined') tomorrowEditMode=false; if(typeof submitted!=='undefined') submitted=true; renderTomorrow(); if(typeof renderMonthly==='function') renderMonthly();
    addAdminActivityNotification(u, entry);
  };
  function addAdminActivityNotification(u,e){
    const all=read("adminNotifications",[]); const list=Array.isArray(all)?all:[]; const key="entry-"+u.id+"-"+e.date; if(list.some(n=>n.dedupeKey===key)) return;
    list.unshift({id:"AN-"+Date.now(),title:"New mess entry",message:`${u.name||u.id} submitted tomorrow's entry.`,target:"entries",createdAt:new Date().toISOString(),dedupeKey:key}); write("adminNotifications",list);
  }

  function patchLoginActivity(){
    const original=window.doLogin; if(typeof original!=="function" || original.__mmaWrapped) return;
    const wrapped=function(){ original.apply(this,arguments); const u=user(); if(u){const users=read("users",[]); const i=users.findIndex(x=>String(x.id||"").toUpperCase()===String(u.id).toUpperCase()); if(i>=0){users[i].lastLoginAt=new Date().toISOString();users[i].lastActivityAt=new Date().toISOString();write("users",users);}} applyTheme(); }; wrapped.__mmaWrapped=true; window.doLogin=wrapped;
  }

  function registerRoute(){
    const token=new URLSearchParams(location.search).get("register"); if(!token) return;
    const invitations=read("invitations",[]); const invite=(Array.isArray(invitations)?invitations:[]).find(i=>String(i.code)===String(token)&&i.status!=="used"); if(!invite) return;
    const login=document.getElementById("login"); if(!login) return;
    login.innerHTML=`<div class="login-card"><div class="login-mark">MH</div><h1>Join MMA Hostel Mount Road</h1><p class="sub">Registration request — management approval required</p><div class="field"><label>Name</label><input id="regName" type="text"></div><div class="field"><label>Room number</label><input id="regRoom" type="text"></div><div class="field"><label>Type</label><select id="regType"><option value="student">Student</option><option value="worker">Worker</option></select></div><div class="field"><label>Create password</label><input id="regPw" type="password"></div><div class="field"><label>Confirm password</label><input id="regPw2" type="password"></div><button class="btn-primary" id="regSubmit">Send Registration Request</button><div class="hint">Your account becomes active only after admin / mess secretary approval.</div></div>`;
    document.getElementById("regSubmit").onclick=function(){
      const name=document.getElementById("regName").value.trim(), room=document.getElementById("regRoom").value.trim(), type=document.getElementById("regType").value, pw=document.getElementById("regPw").value, pw2=document.getElementById("regPw2").value;
      if(!name||!room||!pw||pw!==pw2||pw.length<6){alert("Enter all details and a matching password of at least 6 characters.");return;}
      const reqs=read("registrationRequests",[]); const list=Array.isArray(reqs)?reqs:[]; list.push({id:"REG-"+Date.now(),name,room,type,password:pw,inviteCode:token,status:"pending",createdAt:new Date().toISOString()}); write("registrationRequests",list);
      const invs=read("invitations",[]); const ii=invs.findIndex(i=>String(i.code)===String(token)); if(ii>=0){invs[ii].status="used";invs[ii].usedAt=new Date().toISOString();write("invitations",invs);} addNotification("Registration request received","Your registration request is waiting for management approval.","home",null,"reg-user-"+Date.now());
      login.innerHTML='<div class="login-card"><div class="login-mark">✓</div><h1>Request submitted</h1><p class="sub">Management will approve your account and provide your User ID.</p></div>';
      const admins=read("adminNotifications",[]); admins.unshift({id:"AN-"+Date.now(),title:"New registration request",message:`Registration request from ${name}.`,target:"requests",createdAt:new Date().toISOString()}); write("adminNotifications",admins);
    };
  }

  function enhanceInit(){
    applyTheme(); addBackButtons(); ensureNotificationControls(); ensureThemeSetting(); updateCutoffUI(); renderNotifications(); patchLoginActivity(); registerRoute();
    const root=document.getElementById("app"); if(root && uid()){root.style.display="block";document.getElementById("login")?.classList.remove("active");}
    const u=user(); if(u && typeof window.initApp === "function" && !window.__mmaInitialised){window.__mmaInitialised=true; window.initApp();}
  }

  document.addEventListener("DOMContentLoaded", enhanceInit);
  window.addEventListener("storage",()=>{applyTheme();updateCutoffUI();renderNotifications();});
  window.addEventListener("focus",()=>{updateCutoffUI();renderNotifications();});
  setInterval(updateCutoffUI,30000);
})();
