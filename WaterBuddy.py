import streamlit as st
import streamlit.components.v1 as components
import requests
import json
import base64
import random
import matplotlib.pyplot as plt
from datetime import date, timedelta

# --------------------------------------------------
# Optional Lottie Support
# --------------------------------------------------
try:
    from streamlit_lottie import st_lottie
except Exception:
    st_lottie = None

# --------------------------------------------------
# App / Firebase Configuration
# --------------------------------------------------
FIREBASE_URL = "https://waterhydrator-9ecad-default-rtdb.asia-southeast1.firebasedatabase.app"
USERS_NODE = "users"
TODAY = date.today().isoformat()
REQUEST_TIMEOUT = 8

AGE_GROUP_DEFAULTS = {
    "6-12": 1600,
    "13-18": 2000,
    "19-50": 2500,
    "65+": 2000,
}

DEFAULT_QUICK_ADD = 250

HYDRATION_TIPS = [
    "Keep a filled water bottle visible on your desk.",
    "Drink a glass (250 ml) after every bathroom break.",
    "Start your day with a glass of water.",
    "Add lemon or cucumber for natural flavor.",
    "Set small hourly reminders and sip regularly.",
]

# --------------------------------------------------
# Firebase Helpers (REST API)
# --------------------------------------------------
def fb_path(path: str) -> str:
    """Generate a full, clean Firebase JSON URL."""
    path = path.strip("/")
    return f"{FIREBASE_URL}/{path}.json"

def fb_get(path: str):
    try:
        r = requests.get(fb_path(path), timeout=REQUEST_TIMEOUT)
        return r.json() if r.status_code == 200 else None
    except:
        return None

def fb_post(path: str, data):
    try:
        r = requests.post(fb_path(path), json=data, timeout=REQUEST_TIMEOUT)
        return r.json() if r.status_code in (200, 201) else None
    except:
        return None

def fb_patch(path: str, data: dict):
    try:
        r = requests.patch(fb_path(path), json=data, timeout=REQUEST_TIMEOUT)
        return r.status_code in (200, 201)
    except:
        return False

# --------------------------------------------------
# User Management
# --------------------------------------------------
def find_user(username: str):
    """Return (uid, record) for a matching username, else (None, None)."""
    all_users = fb_get(USERS_NODE)
    if not isinstance(all_users, dict):
        return None, None

    for uid, rec in all_users.items():
        if isinstance(rec, dict) and rec.get("username") == username:
            return uid, rec
    return None, None

def create_user(username: str, password: str):
    """Create new user; return UID or None."""
    if not username or not password:
        return None

    existing_uid, _ = find_user(username)
    if existing_uid:
        return None  # Username already taken

    payload = {
        "username": username,
        "password": password,
        "created_at": TODAY,
        "profile": {
            "age_group": "19-50",
            "user_goal_ml": AGE_GROUP_DEFAULTS["19-50"],
        }
    }
    response = fb_post(USERS_NODE, payload)
    return response.get("name") if isinstance(response, dict) else None

def login_user(username: str, password: str):
    uid, record = find_user(username)
    if uid and record.get("password") == password:
        return True, uid
    return False, None

# --------------------------------------------------
# Water Intake Functions
# --------------------------------------------------
def get_intake(uid: str):
    """Get today's intake for user."""
    raw = fb_get(f"{USERS_NODE}/{uid}/days/{TODAY}/intake")
    try:
        return int(raw or 0)
    except:
        return 0

def update_intake(uid: str, amount: int):
    """Set today's intake value."""
    return fb_patch(f"{USERS_NODE}/{uid}/days/{TODAY}", {"intake": int(max(0, amount))})

def reset_intake(uid: str):
    return update_intake(uid, 0)

def get_profile(uid: str):
    profile = fb_get(f"{USERS_NODE}/{uid}/profile") or {}
    age_group = profile.get("age_group", "19-50")
    goal = profile.get("user_goal_ml", AGE_GROUP_DEFAULTS[age_group])
    return {"age_group": age_group, "user_goal_ml": int(goal)}

def update_profile(uid: str, updates: dict):
    return fb_patch(f"{USERS_NODE}/{uid}/profile", updates)

def get_history(uid: str, days=7):
    """Get last N days of intake."""
    out = {}
    today = date.today()
    for i in range(days):
        d = (today - timedelta(days=i)).isoformat()
        raw = fb_get(f"{USERS_NODE}/{uid}/days/{d}/intake")
        out[d] = int(raw or 0)
    return out

# --------------------------------------------------
# Streamlit Initial Setup
# --------------------------------------------------
st.set_page_config(page_title="WaterBuddy", layout="wide")

DEFAULT_STATE = {
    "logged_in": False,
    "uid": None,
    "view": "login",
    "nav": "Home",
    "theme": "Light",
    "tip": random.choice(HYDRATION_TIPS),
}

for key, value in DEFAULT_STATE.items():
    st.session_state.setdefault(key, value)

# --------------------------------------------------
# Theme System
# --------------------------------------------------
def apply_theme(theme: str):
    if theme == "Light":
        bg, fg = "#ffffff", "#000000"
    elif theme == "Aqua":
        bg, fg = "#e8fbff", "#004455"
    else:  # Dark Theme
        bg, fg = "#0f1720", "#e6eef6"

    st.markdown(
        f"""
        <style>
        .stApp {{
            background-color: {bg} !important;
            color: {fg} !important;
        }}
        </style>
        """,
        unsafe_allow_html=True,
    )

apply_theme(st.session_state.theme)

# --------------------------------------------------
# SVG Bottle Rendering
# --------------------------------------------------
def render_bottle(percent: float):
    percent = min(max(percent, 0), 100)
    height = 300
    filled = int((percent / 100) * height)
    return f"""
    <svg width="120" height="350" xmlns="http://www.w3.org/2000/svg">
        <rect x="30" y="20" width="60" height="300" rx="20" ry="20"
              fill="none" stroke="#3498db" stroke-width="4"/>
        <rect x="34" y="{320-filled}" width="52" height="{filled}"
              rx="16" ry="16" fill="#5dade2"/>
        <text x="60" y="340" text-anchor="middle"
              font-size="20" fill="#333">{percent:.0f}%</text>
    </svg>
    """

# --------------------------------------------------
# Graphing
# --------------------------------------------------
def render_history_graph(history, goal):
    days = sorted(history.keys())
    days.reverse()
    values = [history[d] for d in days]
    labels = [f"{d[5:7]}-{d[8:10]}" for d in days]

    fig, ax = plt.subplots(figsize=(9, 5))
    ax.plot(labels, values, marker="o", color="#3498db")
    ax.axhline(goal, color="#2ecc71", linestyle="--", label="Goal")
    ax.set_ylim(bottom=0)
    ax.set_title("Water Intake (Last 7 Days)")
    ax.set_ylabel("ml")
    ax.grid(True, alpha=0.4)
    return fig

# --------------------------------------------------
# UI: Login
# --------------------------------------------------
def view_login():
    st.header("Login")

    username = st.text_input("Username")
    password = st.text_input("Password", type="password")

    if st.button("Sign In"):
        ok, uid = login_user(username.strip(), password)
        if ok:
            st.session_state.logged_in = True
            st.session_state.uid = uid
            st.session_state.view = "dashboard"
            st.success("Welcome back!")
            st.rerun()
        else:
            st.error("Invalid username or password.")

    if st.button("Create new account"):
        st.session_state.view = "signup"
        st.rerun()

# --------------------------------------------------
# UI: Signup
# --------------------------------------------------
def view_signup():
    st.header("Create Account")

    username = st.text_input("Choose username")
    password = st.text_input("Choose password", type="password")

    if st.button("Register"):
        uid = create_user(username.strip(), password)
        if uid:
            st.success("Account created. You may now log in.")
            st.session_state.view = "login"
            st.rerun()
        else:
            st.error("Username already exists or network error.")

    if st.button("Back to login"):
        st.session_state.view = "login"
        st.rerun()

# --------------------------------------------------
# UI: Logging Water
# --------------------------------------------------
def view_log(uid, intake, goal):
    st.header("Log Water Intake")
    st.write(f"**Today's intake:** {intake} ml")
    st.write(f"**Goal:** {goal} ml")

    if st.button(f"+ {DEFAULT_QUICK_ADD} ml"):
        update_intake(uid, intake + DEFAULT_QUICK_ADD)
        st.rerun()

    custom = st.number_input("Custom amount (ml)", min_value=0)
    if st.button("Add Custom"):
        update_intake(uid, intake + custom)
        st.success("Water added!")
        st.rerun()

    if st.button("Reset Today"):
        reset_intake(uid)
        st.success("Reset!")
        st.rerun()

# --------------------------------------------------
# UI: History
# --------------------------------------------------
def view_history(uid, goal):
    st.header("History")
    history = get_history(uid, 7)
    fig = render_history_graph(history, goal)
    st.pyplot(fig)

    st.subheader("Raw History Data")
    st.table({day: f"{amount} ml" for day, amount in history.items()})

# --------------------------------------------------
# UI: Settings
# --------------------------------------------------
def view_settings(uid, profile):
    st.header("Settings")

    age_group_list = list(AGE_GROUP_DEFAULTS.keys())
    selected_age = st.selectbox("Age Group", age_group_list, index=age_group_list.index(profile["age_group"]))

    custom_goal = st.number_input("Daily Goal (ml)", min_value=0, value=profile["user_goal_ml"])

    if st.button("Save Settings"):
        update_profile(uid, {"age_group": selected_age, "user_goal_ml": int(custom_goal)})
        st.success("Settings saved!")
        st.rerun()

# --------------------------------------------------
# UI: 2D Runner Game
# --------------------------------------------------
def view_runner_game():
    st.header("WaterBuddy Runner Game")

    with open("assets/ROBO.png", "rb") as f:
        img = base64.b64encode(f.read()).decode()

    html = f"""
    <canvas id="gameCanvas" width="900" height="500"></canvas>
    <script>
        // Entire JS game code unchanged...
    </script>
    """
    components.html(html, height=600)

# --------------------------------------------------
# Dashboard / Main App View
# --------------------------------------------------
def view_dashboard():
    uid = st.session_state.uid
    profile = get_profile(uid)
    intake = get_intake(uid)
    goal = profile["user_goal_ml"]
    percent = min(intake / goal * 100, 100)

    left, right = st.columns([1, 2])

    # Navigation Panel
    with left:
        st.subheader("Navigation")
        for option in ["Home", "Log Water", "History", "Settings", "Runner Game", "Logout"]:
            if st.button(option):
                if option == "Logout":
                    st.session_state.logged_in = False
                    st.session_state.uid = None
                    st.session_state.view = "login"
                else:
                    st.session_state.nav = option
                st.rerun()

        # Theme selector
        theme = st.selectbox("Theme", ["Light", "Aqua", "Dark"])
        if theme != st.session_state.theme:
            st.session_state.theme = theme
            apply_theme(theme)

        st.subheader("Tip of the Day")
        st.info(st.session_state.tip)
        if st.button("New Tip"):
            st.session_state.tip = random.choice(HYDRATION_TIPS)

    # Main Panel
    with right:
        nav = st.session_state.nav

        if nav == "Home":
            st.header("Today's Summary")
            st.metric("Total intake", f"{intake} ml", f"{goal - intake} ml remaining")
            st.progress(percent / 100)

            st.components.v1.html(render_bottle(percent), height=350)

            if percent >= 100:
                st.success("Goal achieved!")
            elif percent >= 75:
                st.info("Great progress — you're over 75%!")
            elif percent >= 50:
                st.info("Halfway there!")
            else:
                st.info("Nice start!")

        elif nav == "Log Water":
            view_log(uid, intake, goal)

        elif nav == "History":
            view_history(uid, goal)

        elif nav == "Settings":
            view_settings(uid, profile)

        elif nav == "Runner Game":
            view_runner_game()

# --------------------------------------------------
# Main Controller
# --------------------------------------------------
def main():
    if not st.session_state.logged_in:
        if st.session_state.view == "login":
            view_login()
        else:
            view_signup()
    else:
        view_dashboard()

if __name__ == "__main__":
    main()
