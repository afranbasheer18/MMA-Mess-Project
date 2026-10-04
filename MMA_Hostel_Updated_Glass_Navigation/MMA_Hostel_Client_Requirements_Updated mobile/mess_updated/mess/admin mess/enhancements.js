/* MMA Hostel admin/management enhancements - consolidated fixes */
(function(){
  "use strict";
  const P="mma_";
  const read=(k,f)=>{try{const r=localStorage.getItem(P+k);return r==null?f:JSON.parse(r);}catch(_){return f;}};
  const write=(k,v)=>{try{localStorage.setItem(P+k,JSON.stringify(v));}catch(_){}};
  const esc=v=>String(v??"").replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;","\"":"&quot;","'":"&#39;"}[c]));
  const adminSession=()=>read("adminSession",null);
  const now=()=>new Date().toLocaleString("en-IN");

  function applyTheme(){const t=read("adminTheme","light");document.documentElement.dataset.theme=t==="dark"?"dark":"light";const b=document.getElementById("adminThemeBtn");if(b)b.textContent=t==="dark"?"☀️ Light":"🌙 Dark";}
  function toggleTheme(){write("adminTheme",read("adminTheme","light")==="dark"?"light":"dark");applyTheme();}

  function adminNotifications(){const a=read("adminNotifications",[]);return Array.isArray(a)?a:[];}
  function adminRead(){return read("adminReadNotifications",[]);}
  function renderAdminBell(){
    const list=adminNotifications(), readIds=adminRead(), unread=list.filter(n=>!readIds.includes(n.id)).length;
    const badge=document.getElementById("adminNotifBadge");if(badge){badge.textContent=unread;badge.style.display=unread?"flex":"none";}
    const count=document.getElementById("adminUnreadCount");if(count)count.textContent=unread?`${unread} unread`:"All caught up";
  }
  function markAdminRead(id){const r=adminRead();if(!r.includes(id)){r.push(id);write("adminReadNotifications",r);}renderAdminBell();}
  function renderAdminNotifications(){
    const box=document.getElementById("adminBellPanelList");if(!box)return;
    const list=adminNotifications(), r=adminRead();
    box.innerHTML=list.length?list.slice(0,30).map(n=>`<button type="button" class="admin-notif-item ${r.includes(n.id)?"":"unread"}" data-id="${esc(n.id)}" data-target="${esc(n.target||"dash")}"><b>${esc(n.title||"Update")}</b><span>${esc(n.message||"")}</span><small>${esc(n.createdAt?new Date(n.createdAt).toLocaleString("en-IN"):now())}</small></button>`).join(""):'<div class="admin-empty">No new activity.</div>';
    box.querySelectorAll("button[data-id]").forEach(b=>b.addEventListener("click",()=>{markAdminRead(b.dataset.id);window.openScreen(b.dataset.target||"dash");closeAdminNotifPanel();}));
  }
  function markAllAdminRead(){write("adminReadNotifications",adminNotifications().map(n=>n.id));renderAdminBell();renderAdminNotifications();}
  function closeAdminNotifPanel(){document.getElementById("adminNotifPanel")?.classList.remove("open");}

  function addAdminActivity(title,message,target,dedupeKey){
    const list=adminNotifications();if(dedupeKey&&list.some(n=>n.dedupeKey===dedupeKey))return;
    list.unshift({id:"AN-"+Date.now()+"-"+Math.random().toString(36).slice(2,6),title,message,target:target||"dash",createdAt:new Date().toISOString(),dedupeKey:dedupeKey||null});write("adminNotifications",list);renderAdminBell();
  }
  window.mmaAdminNotify=addAdminActivity;

  function addUserNotification(title,message,target,userId,dedupeKey){
    const list=read("notifHistory",[]);const arr=Array.isArray(list)?list:[];if(dedupeKey&&arr.some(n=>n.dedupeKey===dedupeKey&&n.userId===userId))return;
    arr.unshift({id:"NTF-"+Date.now()+"-"+Math.random().toString(36).slice(2,6),t:title,m:message,d:now(),target:target||"home",userId:userId||null,audience:userId?"user":"users",dedupeKey:dedupeKey||null,createdAt:new Date().toISOString()});write("notifHistory",arr);
  }
  function allUsers(){return read("users",[]);}

  function ensureAdminUI(){
    const top=document.querySelector("header.top");
    if(top&&!document.getElementById("adminTools")){
      const tools=document.createElement("div");tools.id="adminTools";tools.className="admin-tools";
      tools.innerHTML='<button id="adminThemeBtn" class="top-tool" type="button" aria-label="Toggle theme">🌙 Dark</button><button id="adminBellBtn" class="top-tool bell-tool" type="button" aria-label="Notifications">🔔<span id="adminNotifBadge" class="admin-badge" style="display:none">0</span></button>';
      top.appendChild(tools);tools.querySelector("#adminThemeBtn").addEventListener("click",toggleTheme);tools.querySelector("#adminBellBtn").addEventListener("click",()=>{const p=document.getElementById("adminNotifPanel");p?.classList.toggle("open");renderAdminNotifications();});
      const panel=document.createElement("div");panel.id="adminNotifPanel";panel.className="admin-notif-panel";panel.innerHTML='<div class="admin-notif-head"><b>Notifications</b><button id="adminMarkAll" type="button">Mark all read</button></div><div id="adminUnreadCount" class="admin-unread-count"></div><div id="adminBellPanelList"></div>';document.body.appendChild(panel);panel.querySelector("#adminMarkAll").addEventListener("click",markAllAdminRead);
    }
    applyTheme();renderAdminBell();renderAdminNotifications();
  }

  function addBackButtons(){
    document.querySelectorAll("main .screen").forEach(section=>{
      if(section.id==="dash"||section.querySelector(".mma-admin-back"))return;
      const b=document.createElement("button");b.className="back mma-admin-back";b.type="button";b.textContent="← Back";b.addEventListener("click",()=>{window.__mmaAdminBack=true;window.openScreen("dash");});section.insertBefore(b,section.firstChild);
    });
  }
  function patchNavigation(){
    const original=window.openScreen;if(typeof original!=="function"||original.__mmaEnhanced)return;
    let prev=[];
    const wrapped=function(id){const current=document.querySelector("main .screen.active")?.id;if(!window.__mmaAdminBack&&current&&current!==id)prev.push(current);if(window.__mmaAdminBack)window.__mmaAdminBack=false;original(id);if(id==="notif")renderAdminNotifications();};wrapped.__mmaEnhanced=true;window.openScreen=wrapped;
    window.__mmaAdminPrev=prev;
  }

  function patchLogin(){
    const original=window.doLogin;if(typeof original!=="function"||original.__mmaEnhanced)return;
    const wrapped=function(){
      const id=(document.getElementById("uid")?.value||"").trim().toUpperCase();const pw=document.getElementById("pw")?.value||"";
      const accounts=read("adminAccounts",[{id:"ADMIN01",pw:"admin123",role:"admin",name:"Admin"},{id:"SECRETARY01",pw:"mess123",role:"secretary",name:"Mess Secretary"}]);
      const account=accounts.find(a=>String(a.id).toUpperCase()===id&&String(a.pw)===pw);
      if(account){
        write("adminSession",{id:account.id,role:account.role,name:account.name,lastLoginAt:new Date().toISOString()});
        const users=allUsers();
        users.forEach(u=>{if(String(u.role||"").toLowerCase()==="admin"||String(u.type||"").toLowerCase()==="admin")u.lastActivityAt=new Date().toISOString();});write("users",users);
        // Avoid the old hard-coded credentials check while keeping its UI.
        const login=document.getElementById("login"),app=document.getElementById("app");if(login)login.classList.remove("active");if(app)app.style.display="block";window.initApp();ensureAdminUI();addBackButtons();return;
      }
      original.apply(this,arguments);
    };wrapped.__mmaEnhanced=true;window.doLogin=wrapped;
  }

  function patchLogout(){
    const original=window.doLogout;if(typeof original!=="function"||original.__mmaEnhanced)return;window.doLogout=function(){write("adminSession",null);original.apply(this,arguments);};window.doLogout.__mmaEnhanced=true;
  }

  function restoreAdminSession(){
    const s=adminSession();if(!s)return false;const login=document.getElementById("login"),app=document.getElementById("app");if(login)login.classList.remove("active");if(app)app.style.display="block";window.initApp();return true;
  }

  function patchCutoff(){
    const original=window.saveCutoff;if(typeof original!=="function"||original.__mmaEnhanced)return;window.saveCutoff=function(){const input=document.getElementById("cutoffTime");const value=input?.value||"";if(!/^([01]\d|2[0-3]):[0-5]\d$/.test(value)){alert("Choose a valid cutoff time.");return;}write("cutoffTime",value);if(typeof cutoff!=="undefined")cutoff=value;const msg=document.getElementById("cutoffConfirm");if(msg){msg.textContent=`Cutoff saved: ${formatTime(value)}.`;msg.style.display="block";}addAdminActivity("Mess entry cutoff updated",`Tomorrow's mess entry now closes at ${formatTime(value)}.`,"menu","cutoff-"+value+"-"+new Date().toISOString().slice(0,10));allUsers().filter(u=>String(u.status||"").toLowerCase()==="active").forEach(u=>addUserNotification("Mess entry cutoff updated",`Tomorrow's mess entry closes at ${formatTime(value)}.`,"home",u.id,"cutoff-"+value+"-"+new Date().toISOString().slice(0,10)));};window.saveCutoff.__mmaEnhanced=true;}
  const formatTime=v=>{const p=String(v).split(":");let h=Number(p[0]||0);const m=p[1]||"00";const s=h>=12?"PM":"AM";h=h%12||12;return `${h}:${m} ${s}`;};

  function patchMenus(){
    const oldToday=window.saveTodayMenu;if(typeof oldToday==='function'&&!oldToday.__mmaEnhanced){window.saveTodayMenu=function(){oldToday.apply(this,arguments);const m=read("todayMenu",{});addAdminActivity("Today's menu updated","Breakfast, lunch and dinner were updated.","menu","today-menu-"+JSON.stringify(m));allUsers().filter(u=>String(u.status||"").toLowerCase()==="active").forEach(u=>addUserNotification("Today's menu updated","The mess menu has been updated.","home",u.id,"today-menu-"+new Date().toISOString().slice(0,10)));};window.saveTodayMenu.__mmaEnhanced=true;}
    const oldWeek=window.saveWeekMenu;if(typeof oldWeek==='function'&&!oldWeek.__mmaEnhanced){window.saveWeekMenu=function(){oldWeek.apply(this,arguments);addAdminActivity("Weekly menu updated","The weekly mess menu was updated.","menu","week-menu-"+new Date().toISOString().slice(0,10));allUsers().filter(u=>String(u.status||"").toLowerCase()==="active").forEach(u=>addUserNotification("Weekly menu updated","The weekly mess menu has been updated.","home",u.id,"week-menu-"+new Date().toISOString().slice(0,10)));};window.saveWeekMenu.__mmaEnhanced=true;}
  }

  function patchInvitation(){
    window.copyInvitation=function(code){
      const url=new URL("../mess project/index.html",window.location.href);
      url.searchParams.set("register",code);
      const text=url.href;
      if(navigator.clipboard&&navigator.clipboard.writeText){navigator.clipboard.writeText(text).then(()=>alert("Invitation link copied."),()=>prompt("Copy this invitation link:",text));}
      else prompt("Copy this invitation link:",text);
    };
  }

  function patchSendNotification(){
    const old=window.sendNotif;if(typeof old!=='function'||old.__mmaEnhanced)return;window.sendNotif=function(){const title=document.getElementById("notifTitle")?.value.trim(),msg=document.getElementById("notifMsg")?.value.trim();old.apply(this,arguments);if(title&&msg){const list=read("notifHistory",[]);if(Array.isArray(list)&&list[0]){list[0].id=list[0].id||("NTF-"+Date.now());list[0].target="home";list[0].audience="users";list[0].createdAt=new Date().toISOString();write("notifHistory",list);}addAdminActivity("Notification sent",title,"notif","manual-notif-"+title+"-"+msg);}};window.sendNotif.__mmaEnhanced=true;}

  function patchBills(){
    const old=window.generateBills;if(typeof old!=='function'||old.__mmaEnhanced)return;window.generateBills=function(){old.apply(this,arguments);const month=document.getElementById("billMonth")?.value;if(month){addAdminActivity("Monthly bills updated",`Bills were generated/updated for ${month}.`,"bills","billgen-"+month);allUsers().filter(u=>String(u.status||"").toLowerCase()==="active").forEach(u=>addUserNotification("Monthly bill updated",`Your monthly bill for ${month} is available.`,"bill",u.id,"bill-"+u.id+"-"+month));}};window.generateBills.__mmaEnhanced=true;}

  function renderRegistrationRequests(){
    const box=document.getElementById("registrationRequestsList");if(!box)return;const list=read("registrationRequests",[]).filter(r=>r.status==="pending");
    box.innerHTML=list.length?list.map(r=>`<div class="request-card"><b>${esc(r.name)}</b><span>${esc(r.type)} · Room ${esc(r.room)}</span><small>${esc(new Date(r.createdAt).toLocaleString("en-IN"))}</small><div class="request-actions"><button class="btn-primary small" onclick="approveRegistration('${esc(r.id)}')">Approve</button><button class="btn-secondary small" onclick="rejectRegistration('${esc(r.id)}')">Reject</button></div></div>`).join(""):'<div class="admin-empty">No pending registration requests.</div>';
  }
  window.approveRegistration=function(id){const regs=read("registrationRequests",[]),r=regs.find(x=>x.id===id);if(!r)return;const users=allUsers();let n=users.length+1, userId="";do{userId=(r.type==="worker"?"WRK":"STU")+String(n++).padStart(3,"0");}while(users.some(u=>String(u.id).toUpperCase()===userId));users.push({id:userId,name:r.name,pw:r.password,room:r.room,branch:"Mount Road",type:r.type,role:r.type,status:"active",lastLoginAt:null,lastActivityAt:null});write("users",users);r.status="approved";r.approvedAt=new Date().toISOString();r.userId=userId;write("registrationRequests",regs);addAdminActivity("Registration approved",`${r.name} approved as ${userId}.`,"users","reg-approved-"+r.id);addUserNotification("Registration approved",`Your account is approved. User ID: ${userId}.`,"home",userId,"reg-approved-user-"+r.id);renderRegistrationRequests();if(typeof renderUsers==='function')renderUsers();};
  window.rejectRegistration=function(id){const regs=read("registrationRequests",[]),r=regs.find(x=>x.id===id);if(!r)return;r.status="rejected";r.rejectedAt=new Date().toISOString();write("registrationRequests",regs);addAdminActivity("Registration rejected",`${r.name}'s registration was rejected.`,"requests","reg-rejected-"+r.id);renderRegistrationRequests();};

  function renderExtraSections(){
    const main=document.querySelector("main");if(!main)return;
    if(!document.getElementById("requests")){const s=document.createElement("section");s.id="requests";s.className="screen";s.innerHTML='<div class="section-title" style="margin-top:0">Requests & Registration</div><div class="card"><h3>Pending registration requests</h3><div id="registrationRequestsList"></div></div><div class="card"><h3>Student / worker requests</h3><div id="requestsList"></div></div>';main.appendChild(s);}
    if(!document.getElementById("userAccess")){const s=document.createElement("section");s.id="userAccess";s.className="screen";s.innerHTML='<div class="section-title" style="margin-top:0">User Access & Activity</div><div class="card"><div class="table-wrap"><table class="dtable"><thead><tr><th>ID</th><th>Name</th><th>Type</th><th>Room</th><th>Status</th><th>Last login</th><th>Last activity</th></tr></thead><tbody id="userAccessList"></tbody></table></div></div>';main.appendChild(s);}
    const side=document.querySelector(".side");if(side&&!side.querySelector('[data-extra="requests"]')){const refs=[['requests','📝 Requests'],['userAccess','🕒 User Activity']];refs.forEach(([id,label])=>{const b=document.createElement("button");b.className="navbtn";b.dataset.s=id;b.dataset.extra="requests";b.textContent=label;b.onclick=()=>window.openScreen(id);side.appendChild(b);});}
    renderRegistrationRequests();renderRequestList();renderAccess();addBackButtons();
  }
  function renderRequestList(){const box=document.getElementById("requestsList");if(!box)return;const rs=read("requests",[]).filter(r=>r.status==="pending");box.innerHTML=rs.length?rs.map(r=>`<div class="request-card"><b>${esc(r.type||"Request")}</b><span>${esc(r.user||r.userId||"")} · ${esc(r.room||"")}</span><small>${esc(r.message||r.date||"")}</small><div class="request-actions"><button class="btn-primary small" onclick="updateUserRequest('${esc(r.id)}','approved')">Approve</button><button class="btn-secondary small" onclick="updateUserRequest('${esc(r.id)}','rejected')">Reject</button></div></div>`).join(""):'<div class="admin-empty">No pending requests.</div>';}
  window.updateUserRequest=function(id,status){const rs=read("requests",[]),r=rs.find(x=>x.id===id);if(!r)return;r.status=status;r.reviewedAt=new Date().toISOString();write("requests",rs);addAdminActivity(`Request ${status}`,`${r.user||r.userId||"User"}: ${r.type||"request"}.`,"requests","request-"+id+"-"+status);if(r.user)addUserNotification(`Request ${status}`,`Your ${r.type||"request"} was ${status}.`,"clientRequests",r.user,"request-"+id+"-"+status);renderRequestList();};
  function renderAccess(){const box=document.getElementById("userAccessList");if(!box)return;box.innerHTML=allUsers().map(u=>`<tr><td>${esc(u.id)}</td><td>${esc(u.name)}</td><td>${esc(u.type||u.role||"student")}</td><td>${esc(u.room||"-")}</td><td>${esc(u.status||"active")}</td><td>${esc(u.lastLoginAt?new Date(u.lastLoginAt).toLocaleString("en-IN"):"-")}</td><td>${esc(u.lastActivityAt?new Date(u.lastActivityAt).toLocaleString("en-IN"):"-")}</td></tr>`).join("")||'<tr><td colspan="7">No users.</td></tr>';}

  function enforceRole(){const s=adminSession();if(!s)return;const secretary=s.role==="secretary";document.querySelectorAll('.side .navbtn').forEach(b=>{const id=b.dataset.s;if(secretary&&["users","bills","userAccess"].includes(id))b.style.display="none";});const name=document.querySelector(".admin-name");if(name)name.textContent=s.name||"Admin";}

  function init(){applyTheme();ensureAdminUI();patchNavigation();patchLogin();patchLogout();patchCutoff();patchMenus();patchInvitation();patchSendNotification();patchBills();renderExtraSections();enforceRole();const restored=restoreAdminSession();if(restored){ensureAdminUI();renderExtraSections();enforceRole();}setInterval(()=>{renderAdminBell();renderAdminNotifications();renderRequestList();renderRegistrationRequests();renderAccess();},5000);}
  document.addEventListener("DOMContentLoaded",init);
  window.addEventListener("storage",()=>{renderAdminBell();renderAdminNotifications();renderRequestList();renderRegistrationRequests();renderAccess();});
})();
