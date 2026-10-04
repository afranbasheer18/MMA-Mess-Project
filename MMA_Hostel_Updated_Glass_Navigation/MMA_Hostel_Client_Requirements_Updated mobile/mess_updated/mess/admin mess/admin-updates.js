/* =========================================================
   1. STORAGE
   ========================================================= */

const STORAGE_PREFIX = "mma_";

function getData(key, defaultValue = []) {
    const data = localStorage.getItem(STORAGE_PREFIX + key);

    if (!data) {
        return defaultValue;
    }

    try {
        return JSON.parse(data);
    } catch (error) {
        console.error("Storage read error:", error);
        return defaultValue;
    }
}

function saveData(key, data) {
    localStorage.setItem(
        STORAGE_PREFIX + key,
        JSON.stringify(data)
    );
}


/* =========================================================
   2. HTML SECURITY
   ========================================================= */

function escapeHTML(value) {
    return String(value ?? "")
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#039;");
}


/* =========================================================
   3. CURRENT USER
   ========================================================= */

function getCurrentUser() {
    return getData("currentUser", null);
}


/* =========================================================
   4. ADMIN NAVIGATION
   ========================================================= */

function addAdminNavigation() {

    const navigation = document.querySelector(".sidebar");

    if (!navigation) {
        return;
    }

    navigation.innerHTML += `
        <button onclick="showSection('requests')">
            Requests
        </button>

        <button onclick="showSection('userAccess')">
            User Access
        </button>

        <button onclick="showSection('foodLimits')">
            Food Limits
        </button>

        <button onclick="showSection('invitations')">
            Invitations
        </button>
    `;
}


/* =========================================================
   5. ADMIN SECTIONS
   ========================================================= */

function createAdminSections() {

    const container = document.querySelector(".main-content");

    if (!container) {
        return;
    }

    container.innerHTML += `

        <section id="requests" class="admin-section">
            <h2>Requests</h2>
            <div id="requestsList"></div>
        </section>

        <section id="userAccess" class="admin-section">
            <h2>User Access</h2>
            <div id="userAccessList"></div>
        </section>

        <section id="foodLimits" class="admin-section">
            <h2>Food Limits</h2>
            <div id="foodLimitsList"></div>
        </section>

        <section id="invitations" class="admin-section">
            <h2>Invitations</h2>

            <button onclick="generateInvitation()">
                Generate Invitation
            </button>

            <div id="invitationList"></div>
        </section>
    `;
}


/* =========================================================
   6. REQUESTS
   ========================================================= */

function renderRequests() {

    const container = document.getElementById("requestsList");

    if (!container) {
        return;
    }

    const requests = getData("requests", []);

    if (requests.length === 0) {
        container.innerHTML = `
            <p>No pending requests.</p>
        `;
        return;
    }

    container.innerHTML = requests.map(request => `

        <div class="request-card">

            <h3>
                ${escapeHTML(request.type)}
            </h3>

            <p>
                User:
                ${escapeHTML(request.userId)}
            </p>

            <p>
                Date:
                ${escapeHTML(request.date)}
            </p>

            <button
                onclick="approveRequest('${request.id}')">
                Approve
            </button>

            <button
                onclick="rejectRequest('${request.id}')">
                Reject
            </button>

        </div>

    `).join("");
}


function approveRequest(requestId) {

    const requests = getData("requests", []);

    const request = requests.find(
        item => item.id === requestId
    );

    if (!request) {
        return;
    }

    request.status = "approved";

    saveData("requests", requests);

    renderRequests();
}


function rejectRequest(requestId) {

    const requests = getData("requests", []);

    const request = requests.find(
        item => item.id === requestId
    );

    if (!request) {
        return;
    }

    request.status = "rejected";

    saveData("requests", requests);

    renderRequests();
}


/* =========================================================
   7. USER ACCESS / ACTIVITY
   ========================================================= */

function renderUserAccess() {

    const container = document.getElementById("userAccessList");

    if (!container) {
        return;
    }

    const users = getData("users", []);

    if (users.length === 0) {
        container.innerHTML = `
            <p>No users found.</p>
        `;
        return;
    }

    container.innerHTML = `

        <div class="table-wrapper">

            <table>

                <thead>
                    <tr>
                        <th>User ID</th>
                        <th>Name</th>
                        <th>Type</th>
                        <th>Room</th>
                        <th>Status</th>
                        <th>Last Login</th>
                        <th>Last Activity</th>
                    </tr>
                </thead>

                <tbody>

                    ${users.map(user => `

                        <tr>

                            <td>
                                ${escapeHTML(user.id)}
                            </td>

                            <td>
                                ${escapeHTML(user.name)}
                            </td>

                            <td>
                                ${escapeHTML(user.type)}
                            </td>

                            <td>
                                ${escapeHTML(user.room)}
                            </td>

                            <td>
                                ${escapeHTML(user.status)}
                            </td>

                            <td>
                                ${user.lastLoginAt || "-"}
                            </td>

                            <td>
                                ${user.lastActivityAt || "-"}
                            </td>

                        </tr>

                    `).join("")}

                </tbody>

            </table>

        </div>
    `;
}


/* =========================================================
   8. FOOD LIMITS
   ========================================================= */

const DEFAULT_FOOD_LIMITS = {

    Puri: 4,
    Dosa: 4,
    Idly: 4,

    "Chicken Piece": 1,
    Egg: 1,
    "Fish Fry": 1,

    Banana: 1,
    Poriyal: 1
};


function loadFoodLimits() {

    const savedLimits = getData(
        "foodLimits",
        DEFAULT_FOOD_LIMITS
    );

    return savedLimits;
}


function renderFoodLimits() {

    const container = document.getElementById(
        "foodLimitsList"
    );

    if (!container) {
        return;
    }

    const limits = loadFoodLimits();

    container.innerHTML = Object.entries(limits)
        .map(([food, limit]) => `

            <div class="food-limit-row">

                <label>
                    ${escapeHTML(food)}
                </label>

                <input
                    type="number"
                    min="0"
                    value="${limit}"
                    data-food="${escapeHTML(food)}"
                >

            </div>

        `)
        .join("");
}


function saveFoodLimits() {

    const inputs = document.querySelectorAll(
        "#foodLimitsList input"
    );

    const limits = {};

    inputs.forEach(input => {

        const food = input.dataset.food;
        const limit = Number(input.value);

        limits[food] = limit;

    });

    saveData("foodLimits", limits);

    alert("Food limits saved.");
}


/* =========================================================
   9. INVITATION
   ========================================================= */

function generateInvitation() {

    const invitationCode =
        Math.random()
            .toString(36)
            .substring(2, 10)
            .toUpperCase();

    const invitations = getData(
        "invitations",
        []
    );

    const invitation = {

        id: Date.now(),

        code: invitationCode,

        createdAt: new Date().toISOString(),

        status: "active"

    };

    invitations.push(invitation);

    saveData(
        "invitations",
        invitations
    );

    renderInvitations();
}


function renderInvitations() {

    const container = document.getElementById(
        "invitationList"
    );

    if (!container) {
        return;
    }

    const invitations = getData(
        "invitations",
        []
    );

    container.innerHTML = invitations.map(
        invitation => `

        <div class="invitation-card">

            <p>
                Code:
                <strong>
                    ${escapeHTML(invitation.code)}
                </strong>
            </p>

            <button
                onclick="copyInvitation('${invitation.code}')">
                Copy
            </button>

        </div>

    `).join("");
}


function copyInvitation(code) {

    const url =
        `${window.location.origin}/register.html?invite=${code}`;

    navigator.clipboard.writeText(url);

    alert("Invitation link copied.");
}


/* =========================================================
   10. REGISTRATION REQUEST
   ========================================================= */

function submitRegistration(event) {

    event.preventDefault();

    const name =
        document.getElementById("name").value.trim();

    const room =
        document.getElementById("room").value.trim();

    const type =
        document.getElementById("type").value;

    const password =
        document.getElementById("password").value;

    const confirmPassword =
        document.getElementById("confirmPassword").value;


    if (password !== confirmPassword) {

        alert("Passwords do not match.");

        return;
    }


    const registrations =
        getData(
            "registrationRequests",
            []
        );


    registrations.push({

        id: Date.now(),

        name,

        room,

        type,

        password,

        status: "pending",

        createdAt:
            new Date().toISOString()

    });


    saveData(
        "registrationRequests",
        registrations
    );


    alert(
        "Registration submitted. Wait for admin approval."
    );

}


/* =========================================================
   11. APPROVE REGISTRATION
   ========================================================= */

function approveRegistration(registrationId) {

    const registrations =
        getData(
            "registrationRequests",
            []
        );


    const registration =
        registrations.find(
            item => item.id === registrationId
        );


    if (!registration) {
        return;
    }


    const users =
        getData("users", []);


    const prefix =
        registration.type === "student"
            ? "STU"
            : "WRK";


    const userId =
        prefix +
        String(users.length + 1)
            .padStart(3, "0");


    const newUser = {

        id: userId,

        name: registration.name,

        room: registration.room,

        type: registration.type,

        status: "active",

        lastLoginAt: null,

        lastActivityAt: null

    };


    users.push(newUser);

    saveData("users", users);


    registration.status = "approved";

    saveData(
        "registrationRequests",
        registrations
    );


    renderUserAccess();
}


/* =========================================================
   12. LOGIN ACTIVITY
   ========================================================= */

function recordLogin(userId) {

    const users =
        getData("users", []);


    const user =
        users.find(
            item => item.id === userId
        );


    if (!user) {
        return;
    }


    const now =
        new Date().toISOString();


    user.lastLoginAt = now;

    user.lastActivityAt = now;


    saveData("users", users);
}


/* =========================================================
   13. USER ACTIVITY
   ========================================================= */

function recordActivity(userId) {

    const users =
        getData("users", []);


    const user =
        users.find(
            item => item.id === userId
        );


    if (!user) {
        return;
    }


    user.lastActivityAt =
        new Date().toISOString();


    saveData("users", users);
}


/* =========================================================
   14. INITIALIZATION
   ========================================================= */

function initializeAdmin() {

    addAdminNavigation();

    createAdminSections();

    renderRequests();

    renderUserAccess();

    renderFoodLimits();

    renderInvitations();

}


/* =========================================================
   15. START
   ========================================================= */

document.addEventListener(
    "DOMContentLoaded",
    initializeAdmin
);