(function () {

    /* ==============================
       STORAGE
       ============================== */

    const S = window.localStorage;

    const key = name => `mma_${name}`;

    function get(name, defaultValue) {
        try {
            const value = S.getItem(key(name));

            return value === null
                ? defaultValue
                : JSON.parse(value);

        } catch (error) {
            return defaultValue;
        }
    }

    function set(name, value) {
        S.setItem(
            key(name),
            JSON.stringify(value)
        );
    }


    /* ==============================
       HELPERS
       ============================== */

    function escapeHTML(value) {
        return String(value ?? "")
            .replace(/[&<>"']/g, character => ({
                "&": "&amp;",
                "<": "&lt;",
                ">": "&gt;",
                '"': "&quot;",
                "'": "&#39;"
            }[character]));
    }

    function today() {
        const date = new Date();
        date.setHours(0, 0, 0, 0);
        return date;
    }

    function tomorrow() {
        const date = today();
        date.setDate(date.getDate() + 1);
        return date;
    }

    function dateKey(date) {
        const year = date.getFullYear();
        const month = String(
            date.getMonth() + 1
        ).padStart(2, "0");

        const day = String(
            date.getDate()
        ).padStart(2, "0");

        return `${year}-${month}-${day}`;
    }

    function getCurrentUser() {

        const userId =
            get("currentUserId", "");

        return get("users", []).find(
            user =>
                String(user.id).toUpperCase() ===
                String(userId).toUpperCase()
        );
    }


    /* ==============================
       USER REQUESTS & FEEDBACK
       ============================== */

    function insertRequestSection() {

        const main =
            document.querySelector("main");

        if (
            !main ||
            document.getElementById(
                "clientRequests"
            )
        ) {
            return;
        }

        const section =
            document.createElement("section");

        section.id = "clientRequests";
        section.className = "screen";

        section.innerHTML = `
            <button
                class="back"
                onclick="openScreen('home')">
                ← Back
            </button>

            <div
                class="section-title"
                style="margin-top:0">
                Requests & Feedback
            </div>

            <div class="card">
                <div
                    class="request-list"
                    id="clientRequestList">
                </div>
            </div>

            <div class="section-title">
                New Request
            </div>

            <div class="card">

                <div class="field">
                    <label>Type</label>

                    <select id="reqType">
                        <option value="permission">
                            Meal permission
                        </option>

                        <option value="cancellation">
                            Meal cancellation
                        </option>

                        <option value="leave">
                            Hostel leave
                        </option>

                        <option value="complaint">
                            Complaint
                        </option>

                        <option value="suggestion">
                            Improvement suggestion
                        </option>
                    </select>
                </div>


                <div class="field">
                    <label>Meal</label>

                    <select id="reqMeal">
                        <option value="breakfast">
                            Breakfast
                        </option>

                        <option value="lunch">
                            Lunch
                        </option>

                        <option value="dinner">
                            Dinner
                        </option>

                        <option value="all">
                            All meals
                        </option>
                    </select>
                </div>


                <div class="field">
                    <label>From</label>

                    <input
                        id="reqFrom"
                        type="date">
                </div>


                <div class="field">
                    <label>To</label>

                    <input
                        id="reqTo"
                        type="date">
                </div>


                <div class="field">
                    <label>
                        Reason / message
                    </label>

                    <textarea
                        id="reqMessage"
                        rows="4"
                        placeholder="Explain your request">
                    </textarea>
                </div>


                <button
                    class="btn-primary"
                    onclick="submitClientRequest()">
                    Submit Request
                </button>

            </div>
        `;

        const more =
            document.getElementById("more");

        main.insertBefore(
            section,
            more
        );
    }


    /* ==============================
       RENDER REQUESTS
       ============================== */

    function renderRequests() {

        const box =
            document.getElementById(
                "clientRequestList"
            );

        if (!box) {
            return;
        }

        const currentUser =
            getCurrentUser();

        if (!currentUser) {

            box.innerHTML = `
                <div class="empty">
                    Login required.
                </div>
            `;

            return;
        }

        const requests =
            get("requests", [])
                .filter(
                    request =>
                        String(request.user)
                            .toUpperCase() ===
                        String(currentUser.id)
                            .toUpperCase()
                )
                .reverse();


        if (requests.length === 0) {

            box.innerHTML = `
                <div class="empty">
                    No requests yet.
                </div>
            `;

            return;
        }


        box.innerHTML =
            requests.map(request => `

                <div class="request-item">

                    <b>
                        ${escapeHTML(
                            request.type
                        )}
                    </b>

                    <span class="access-pill">
                        ${escapeHTML(
                            request.status ||
                            "Pending"
                        )}
                    </span>

                    <div class="meta">
                        ${escapeHTML(
                            request.meal || ""
                        )}
                        ·
                        ${escapeHTML(
                            request.from || ""
                        )}

                        ${
                            request.to
                                ? `→ ${escapeHTML(
                                    request.to
                                )}`
                                : ""
                        }
                    </div>

                    <p>
                        ${escapeHTML(
                            request.message || ""
                        )}
                    </p>

                </div>

            `).join("");
    }


    /* ==============================
       SUBMIT REQUEST
       ============================== */

    window.submitClientRequest =
        function () {

            const currentUser =
                getCurrentUser();

            if (!currentUser) {
                alert(
                    "Please login again."
                );
                return;
            }


            const type =
                document.getElementById(
                    "reqType"
                ).value;


            const request = {

                id:
                    "REQ" + Date.now(),

                user:
                    currentUser.id,

                name:
                    currentUser.name,

                room:
                    currentUser.room,

                type,

                meal:
                    document.getElementById(
                        "reqMeal"
                    ).value,

                from:
                    document.getElementById(
                        "reqFrom"
                    ).value,

                to:
                    document.getElementById(
                        "reqTo"
                    ).value,

                message:
                    document.getElementById(
                        "reqMessage"
                    ).value.trim(),

                status:
                    "pending",

                createdAt:
                    new Date().toISOString()
            };


            if (
                !request.message &&
                type !== "leave"
            ) {

                alert(
                    "Please enter a reason or message."
                );

                return;
            }


            const requests =
                get("requests", []);

            requests.push(request);

            set(
                "requests",
                requests
            );


            document.getElementById(
                "reqMessage"
            ).value = "";


            renderRequests();

            alert(
                "Request sent to admin / mess secretary."
            );
        };


    /* ==============================
       CHANGE PASSWORD
       ============================== */

    function addPasswordSection() {

        const settings =
            document.getElementById(
                "settings"
            );

        if (
            !settings ||
            document.getElementById(
                "changePasswordCard"
            )
        ) {
            return;
        }


        const card =
            document.createElement("div");

        card.className =
            "card password-box";

        card.id =
            "changePasswordCard";


        card.innerHTML = `

            <div class="field">

                <label>
                    Current password
                </label>

                <input
                    id="oldPw"
                    type="password">

            </div>


            <div class="field">

                <label>
                    New password
                </label>

                <input
                    id="newPw"
                    type="password"
                    minlength="6">

            </div>


            <div class="field">

                <label>
                    Confirm new password
                </label>

                <input
                    id="newPw2"
                    type="password"
                    minlength="6">

            </div>


            <button
                class="btn-primary"
                onclick="changeClientPassword()">

                Change Password

            </button>


            <div
                class="confirm-msg"
                id="pwChanged">

                Password changed successfully.

            </div>
        `;


        settings.appendChild(card);
    }


    window.changeClientPassword =
        function () {

            const currentUser =
                getCurrentUser();

            if (!currentUser) {
                return;
            }


            const oldPassword =
                document.getElementById(
                    "oldPw"
                ).value;

            const newPassword =
                document.getElementById(
                    "newPw"
                ).value;

            const confirmPassword =
                document.getElementById(
                    "newPw2"
                ).value;


            if (
                String(currentUser.pw ?? "") !==
                oldPassword
            ) {

                alert(
                    "Current password is incorrect."
                );

                return;
            }


            if (newPassword.length < 6) {

                alert(
                    "New password must be at least 6 characters."
                );

                return;
            }


            if (
                newPassword !==
                confirmPassword
            ) {

                alert(
                    "New passwords do not match."
                );

                return;
            }


            const users =
                get("users", []);

            const index =
                users.findIndex(
                    user =>
                        String(user.id)
                            .toUpperCase() ===
                        String(currentUser.id)
                            .toUpperCase()
                );


            if (index === -1) {
                return;
            }


            users[index].pw =
                newPassword;

            users[index]
                .lastPasswordChangeAt =
                new Date().toISOString();


            set(
                "users",
                users
            );


            document.getElementById(
                "oldPw"
            ).value = "";

            document.getElementById(
                "newPw"
            ).value = "";

            document.getElementById(
                "newPw2"
            ).value = "";


            const message =
                document.getElementById(
                    "pwChanged"
                );

            if (message) {
                message.style.display =
                    "block";
            }
        };


    /* ==============================
       REGISTRATION
       ============================== */

    function addRegistrationRoute() {

        const token =
            new URLSearchParams(
                location.search
            ).get("register");


        if (!token) {
            return;
        }


        const invitation =
            get("invites", [])
                .find(
                    item =>
                        item.token === token &&
                        item.active
                );


        if (!invitation) {
            return;
        }


        const login =
            document.getElementById(
                "login"
            );

        if (!login) {
            return;
        }


        login.innerHTML = `

            <div class="login-card">

                <div class="login-mark">
                    MH
                </div>

                <h1>
                    Join MMA Hostel Mount Road
                </h1>

                <p class="sub">
                    Registration request —
                    management approval required
                </p>


                <div class="field">
                    <label>
                        Room number
                    </label>

                    <input
                        id="regRoom"
                        type="text">
                </div>


                <div class="field">
                    <label>
                        Name
                    </label>

                    <input
                        id="regName"
                        type="text">
                </div>


                <div class="field">
                    <label>
                        Type
                    </label>

                    <select id="regType">

                        <option value="student">
                            Student
                        </option>

                        <option value="worker">
                            Worker
                        </option>

                    </select>
                </div>


                <div class="field">
                    <label>
                        Create password
                    </label>

                    <input
                        id="regPw"
                        type="password">
                </div>


                <div class="field">
                    <label>
                        Confirm password
                    </label>

                    <input
                        id="regPw2"
                        type="password">
                </div>


                <button
                    class="btn-primary"
                    onclick="submitClientRegistration(
                        '${escapeHTML(token)}'
                    )">

                    Send Registration Request

                </button>


                <div class="hint">
                    Your account becomes active
                    only after admin / mess
                    secretary approval.
                </div>

            </div>
        `;
    }


    /* ==============================
       USER ACTIVITY
       ============================== */

    function updateUserActivity() {

        const currentUser =
            getCurrentUser();

        if (!currentUser) {
            return;
        }


        const users =
            get("users", []);

        const index =
            users.findIndex(
                user =>
                    String(user.id)
                        .toUpperCase() ===
                    String(currentUser.id)
                        .toUpperCase()
            );


        if (index === -1) {
            return;
        }


        users[index].lastActivityAt =
            new Date().toISOString();


        set(
            "users",
            users
        );
    }


    /* ==============================
       INITIALIZATION
       ============================== */

    const oldInit =
        window.initApp;


    window.initApp =
        function () {

            if (
                typeof oldInit ===
                "function"
            ) {
                oldInit();
            }


            insertRequestSection();

            addPasswordSection();

            renderRequests();
        };


    /* ==============================
       SCREEN CHANGE
       ============================== */

    const oldOpenScreen =
        window.openScreen;


    window.openScreen =
        function (id) {

            if (
                typeof oldOpenScreen ===
                "function"
            ) {
                oldOpenScreen(id);
            }


            if (
                id ===
                "clientRequests"
            ) {
                renderRequests();
            }


            updateUserActivity();
        };


    /* ==============================
       PAGE LOAD
       ============================== */

    document.addEventListener(
        "DOMContentLoaded",
        () => {

            addRegistrationRoute();

            insertRequestSection();

            addPasswordSection();

        }
    );

})();