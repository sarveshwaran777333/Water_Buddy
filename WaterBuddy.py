# WaterBuddy.py
"""
WaterBuddy - Streamlit app combining all features:
1. Secure Password Hashing (using hashlib).
2. Theme Persistence (saves choice to profile).
3. Robust Data Handling (Fixed NameError and safer Firebase access).
4. 7-Day History Trend (Line Chart, Matplotlib).
5. 7-Day History Comparison (Bar Chart, Matplotlib).
"""

import streamlit as st
import requests
import json
from datetime import date, timedelta, datetime
import random
import time
import os
import matplotlib.pyplot as plt
import hashlib

# Optional Lottie support
try:
    from streamlit_lottie import st_lottie
except ImportError:
    st_lottie = None

# -----------------------
# Configuration
# -----------------------
FIREBASE_URL = "https://waterhydrator-9ecad-default-rtdb.asia-southeast1.firebasedatabase.app"
USERS_NODE = "users"
DATE_STR = date.today().isoformat()

AGE_GOALS_ML = {
    "6-12": 1600,
    "13-18": 2000,
    "19-50": 2500,
    "65+": 2000,
}

DEFAULT_QUICK_LOG_ML = 250
CUPS_TO_ML = 236.588
REQUEST_TIMEOUT = 10 

TIPS = [
    "Keep a filled water bottle visible on your desk.",
    "Drink a glass (250 ml) after every bathroom break.",
    "Start your day with a glass of water.",
    "Add lemon or cucumber for natural flavor.",
    "Set small hourly reminders and sip regularly.",
    "Carry a lightweight bottle whenever you go outside.",
    "Refill your bottle every time it becomes half empty",
    "Use a bottle with measurement markings to track progress.",
    "Drink water before meals to stay hydrated and support digestion.",
]

# -----------------------
# Security Helper
# -----------------------
def hash_password(password: str) -> str:
    """Hashes a plaintext password using SHA-256."""
    return hashlib.sha256(password.encode('utf-8')).hexdigest()

# -----------------------
# Firebase REST helpers (Robust Error Handling)
# -----------------------
def firebase_url(path: str) -> str:
    path = path.strip("/")
    return f"{FIREBASE_URL}/{path}.json"

def firebase_get(path: str):
    url = firebase_url(path)
    try:
        r = requests.get(url, timeout=REQUEST_TIMEOUT)
        r.raise_for_status() 
        try:
            return r.json()
        except requests.exceptions.JSONDecodeError:
            return None
    except requests.exceptions.RequestException as e:
        print(f"Firebase GET Error on {path}: {e}")
        return None

def firebase_post(path: str, value):
    url = firebase_url(path)
    try:
        r = requests.post(url, data=json.dumps(value), timeout=REQUEST_TIMEOUT)
        r.raise_for_status()
        try:
            return r.json()
        except requests.exceptions.JSONDecodeError:
            return None
    except requests.exceptions.RequestException as e:
        print(f"Firebase POST Error on {path}: {e}")
        return None

def firebase_patch(path: str, value_dict: dict):
    url = firebase_url(path)
    try:
        r = requests.patch(url, data=json.dumps(value_dict), timeout=REQUEST_TIMEOUT)
        r.raise_for_status()
        return True
    except requests.exceptions.RequestException as e:
        print(f"Firebase PATCH Error on {path}: {e}")
        return False

# -----------------------
# User & Intake helpers
# -----------------------
def find_user_by_username(username: str):
    data = firebase_get(USERS_NODE)
    if not isinstance(data, dict):
        return None, None
    for uid, rec in data.items():
        if isinstance(rec, dict) and rec.get("username") == username:
            return uid, rec
    return None, None

def create_user(username: str, password: str):
    if not username or not password:
        return None
    uid, _ = find_user_by_username(username)
    if uid:
        return None
    
    hashed_pass = hash_password(password)
    
    payload = {
        "username": username,
        "password": hashed_pass,
        "created_at": DATE_STR,
        "profile": {
            "age_group": "19-50",
            "user_goal_ml": AGE_GOALS_ML["19-50"],
            "theme": "Light"
        }
    }
    res = firebase_post(USERS_NODE, payload)
    if isinstance(res, dict) and "name" in res:
        return res["name"]
    return None

def validate_login(username: str, password: str):
    uid, rec = find_user_by_username(username)
    if uid and isinstance(rec, dict):
        hashed_input = hash_password(password)
        if rec.get("password") == hashed_input:
            return True, uid
    return False, None

def get_today_intake(uid: str):
    if not uid:
        return 0
    path = f"{USERS_NODE}/{uid}/days/{DATE_STR}/intake"
    val = firebase_get(path)
    if isinstance(val, (int, float)):
        return int(val)
    user_root = firebase_get(f"{USERS_NODE}/{uid}")
    if isinstance(user_root, dict):
        legacy = user_root.get("todays_intake_ml")
        if isinstance(legacy, (int, float)):
            return int(legacy)
    return 0

def set_today_intake(uid: str, ml_value: int):
    if not uid:
        return False
    ml = int(max(0, ml_value))
    path = f"{USERS_NODE}/{uid}/days/{DATE_STR}"
    return firebase_patch(path, {"intake": ml})

def reset_today_intake(uid: str):
    return set_today_intake(uid, 0)

def get_user_profile(uid: str):
    if not uid:
        return {"age_group": "19-50", "user_goal_ml": AGE_GOALS_ML["19-50"], "theme": "Light"}
    profile = firebase_get(f"{USERS_NODE}/{uid}/profile")
    if isinstance(profile, dict):
        user_goal = profile.get("user_goal_ml", AGE_GOALS_ML["19-50"])
        try:
            user_goal = int(user_goal)
        except Exception:
            user_goal = AGE_GOALS_ML["19-50"]
        theme = profile.get("theme", "Light")
        return {"age_group": profile.get("age_group", "19-50"), "user_goal_ml": user_goal, "theme": theme}
    return {"age_group": "19-50", "user_goal_ml": AGE_GOALS_ML["19-50"], "theme": "Light"}

def update_user_profile(uid: str, updates: dict):
    if not uid:
        return False
    return firebase_patch(f"{USERS_NODE}/{uid}/profile", updates)

def get_username_by_uid(uid: str):
    rec = firebase_get(f"{USERS_NODE}/{uid}")
    if isinstance(rec, dict):
        return rec.get("username", "user")
    return "user"

def get_past_intake(uid: str, days_count: int = 7):
    """Fetches intake data for the last N days (including today), returns sorted by date."""
    intake_data = {}
    today = date.today()
    for i in range(days_count):
        day = (today - timedelta(days=i)).isoformat()
        path = f"{USERS_NODE}/{uid}/days/{day}/intake"
        intake_value = firebase_get(path)
        try:
            intake_data[day] = int(intake_value) if intake_value is not None else 0
        except Exception:
            intake_data[day] = 0
    
    # Return sorted data (oldest to newest)
    sorted_days = sorted(intake_data.keys())
    return {day: intake_data[day] for day in sorted_days}

# -----------------------
# UI helpers (SVG & Matplotlib)
# -----------------------
def generate_bottle_svg(percent: float, width:int=140, height:int=360) -> str:
    """Simple bottle SVG with dynamic fill height."""
    pct = max(0.0, min(100.0, float(percent)))
    inner_w = width - 36
    inner_h = height - 80
    fill_h = (pct / 100.0) * inner_h
    empty_h = inner_h - fill_h

    svg = f"""
<svg width="{width}" height="{height}" viewBox="0 0 {width} {height}" xmlns="http://www.w3.org/2000/svg">
    <rect x="12" y="12" rx="20" ry="20" width="{width-24}" height="{height-24}" fill="none" stroke="#5dade2" stroke-width="3"/>
    <rect x="18" y="18" width="{inner_w}" height="{inner_h}" rx="12" ry="12" fill="#f3fbff"/>
    <rect x="18" y="{18 + empty_h}" width="{inner_w}" height="{fill_h}" rx="12" ry="12" fill="#67b3df"/>
    <rect x="{(width/2)-18}" y="0" width="36" height="18" rx="4" ry="4" fill="#3498db"/>
    <text x="{width/2}" y="{height-8}" font-size="14" text-anchor="middle" fill="#023047" font-family="Arial">{pct:.0f}%</text>
</svg>
"""
    return svg

# RENAME: Existing Line Chart (Trend)
def plot_daily_intake_trend(intake_data: dict, goal: int):
    """Generate a Matplotlib line chart showing daily water intake trend."""
    sorted_days = list(intake_data.keys())
    intakes = [intake_data[day] for day in sorted_days]
    labels = [d[5:] for d in sorted_days]
    
    fig, ax = plt.subplots(figsize=(10, 6))
    ax.plot(labels, intakes, marker='o', color='#3498db', label="Water Intake (ml)", linewidth=2)
    ax.axhline(y=goal, color='#2ecc71', linestyle='--', label=f'Goal ({goal} ml)')

    ax.set_title("Daily Water Intake Trend Over the Last 7 Days", fontsize=16)
    ax.set_xlabel("Date (MM-DD)", fontsize=12)
    ax.set_ylabel("Water Intake (ml)", fontsize=12)
    ax.tick_params(axis='x', rotation=45)
    ax.grid(True, linestyle=':', alpha=0.7)
    ax.legend()
    fig.set_tight_layout(True)
    return fig

# NEW FUNCTION: Weekly Bar Chart (Comparison)
def plot_weekly_bar_chart(intake_data: dict, goal: int):
    """Generate a Matplotlib bar chart showing the last 7 days' intake for comparison."""
    if not intake_data:
        # Return a warning figure if no data is present
        fig, ax = plt.subplots(figsize=(10, 4))
        ax.text(0.5, 0.5, 'No data available for the bar chart.', ha='center', va='center', transform=ax.transAxes)
        ax.axis('off')
        fig.set_tight_layout(True)
        return fig

    # intake_data is already sorted oldest to newest
    days = list(intake_data.keys())
    intakes = list(intake_data.values())
    
    # Format labels to be short days of the week (Mon, Tue, etc.)
    day_labels = []
    for d_str in days:
        # Use datetime.fromisoformat for robust conversion
        d_obj = date.fromisoformat(d_str) 
        day_labels.append(d_obj.strftime("%a")) 
    
    fig, ax = plt.subplots(figsize=(10, 4))
    
    # Use bar chart for weekly comparison
    bars = ax.bar(day_labels, intakes, color='#67b3df', edgecolor='#3498db')
    
    # Add goal line 
    ax.axhline(y=goal, color='#2ecc71', linestyle='--', label=f'Goal ({goal} ml)')

    # Add intake values on top of bars
    for bar in bars:
        yval = bar.get_height()
        # Only label non-zero bars
        if yval > 0:
            ax.text(bar.get_x() + bar.get_width()/2, yval + max(20, goal * 0.02), 
                    f'{yval}', ha='center', va='bottom', fontsize=9)

    # Customize the plot
    ax.set_title("Water Intake by Day (Last 7 Days)", fontsize=16)
    ax.set_xlabel("Day of the Week", fontsize=12)
    ax.set_ylabel("Water Intake (ml)", fontsize=12)
    # Set y-limit to slightly above the max intake or goal for better visualization
    ax.set_ylim(0, max(max(intakes) * 1.2, goal * 1.1)) 
    ax.grid(axis='y', linestyle=':', alpha=0.7)
    ax.legend()
    fig.set_tight_layout(True)
    
    return fig


# -----------------------
# Theme CSS (Well-implemented, kept for completeness)
# -----------------------
def apply_theme(theme_name: str):
    if theme_name == "Light":
        metric_val = "#000000"
        metric_delta = "#006600"
        bg = "#ffffff"
        text = "#000000"
        metric_bg = "#f7f7f7"
    elif theme_name == "Aqua":
        metric_val = "#005577"
        metric_delta = "#0077b6"
        bg = "#e8fbff"
        text = "#004455"
        metric_bg = "#d9f7ff"
    else:  # Dark
        metric_val = "#e6eef6"
        metric_delta = "#4caf50"
        bg = "#0f1720"
        text = "#e6eef6"
        metric_bg = "#1a2634"

    st.markdown(f"""
    <style>
    .stApp {{ background-color: {bg} !important; color: {text} !important; }}
    h1,h2,h3,h4,h5,h6,p,label,span {{ color: {text} !important; }}
    .stButton>button {{ border-radius:8px !important; }}
    .stTextInput>div>div>input {{ border-radius:6px !important; }}
    div[data-testid="metric-container"] {{
        background-color: {metric_bg} !important;
        border-radius: 12px !important;
        padding: 12px !important;
        border: 1px solid rgba(0,0,0,0.06) !important;
    }}
    div[data-testid="metric-container"] * {{ color: {metric_val} !important; }}
    div[data-testid="metric-container"] [data-testid="metric-delta"] *,
    div[data-testid="metric-container"] [data-testid="stMetricDelta"] * {{
        color: {metric_delta} !important;
    }}
    div[data-testid="stMetricValue"] * {{ color: inherit !important; }}
    div[data-testid="stMetricDelta"] * {{ color: inherit !important; }}
    div[data-testid="stVerticalBlock"] div[data-testid="metric-container"] * {{ color: {metric_val} !important; }}
    div[data-testid="stVerticalBlock"] div[data-testid="metric-container"] [data-testid="metric-delta"] * {{ color: {metric_delta} !important; }}
    div[data-testid="metric-container"] svg text {{ fill: {metric_val} !important; color: {metric_val} !important; }}
    </style>
    """, unsafe_allow_html=True)


# -----------------------
# Lottie helper + load animation
# -----------------------
def load_lottie(path: str):
    try:
        # Check path relative to current working directory
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        # Check assets folder path
        assets_path = os.path.join(os.path.dirname(__file__), "assets", path)
        if os.path.exists(assets_path):
             with open(assets_path, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception as e:
        print(f"Error loading lottie file: {e}")
        return None

# Attempt to load Lottie progress animation
LOTTIE_PROGRESS = None
LOTTIE_FILENAME = "progress_bar.json" 
if st_lottie is not None:
    LOTTIE_PROGRESS = load_lottie(LOTTIE_FILENAME) 
    if LOTTIE_PROGRESS is None:
        LOTTIE_PROGRESS = load_lottie(os.path.join("assets", LOTTIE_FILENAME))

# -----------------------
# Streamlit app start
# -----------------------
st.set_page_config(page_title="WaterBuddy", layout="wide")

# session defaults
if "theme" not in st.session_state:
    st.session_state.theme = "Light"
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False
if "uid" not in st.session_state:
    st.session_state.uid = None
if "page" not in st.session_state:
    st.session_state.page = "login"
if "nav" not in st.session_state:
    st.session_state.nav = "Home"
if "tip" not in st.session_state:
    st.session_state.tip = random.choice(TIPS)

# apply initial theme and ensure theme persistence on login
apply_theme(st.session_state.theme)

st.title("WaterBuddy — Hydration Tracker")

# -----------------------
# Login and Signup UIs (Using st.form for clean flow)
# -----------------------
def login_ui():
    st.header("Login (username + password)")
    col1, col2 = st.columns([3,1])
    with col1:
        username = st.text_input("Username", key="login_username")
        password = st.text_input("Password", type="password", key="login_password")
    with col2:
        with st.form("login_form"):
            st.form_submit_button("Login", type="primary")
            if st.session_state.login_form:
                if not username or not password:
                    st.warning("Enter both username and password.")
                else:
                    ok, uid = validate_login(username.strip(), password)
                    if ok:
                        st.session_state.logged_in = True
                        st.session_state.uid = uid
                        
                        profile = get_user_profile(uid)
                        new_theme = profile.get("theme", "Light")
                        if new_theme != st.session_state.theme:
                            st.session_state.theme = new_theme
                            
                        st.session_state.page = "dashboard"
                        st.success("Login successful. Reloading...")
                        time.sleep(0.5)
                        st.rerun()
                    else:
                        st.error("Invalid username or password.")

    st.markdown("---")
    if st.button("Create new account"):
        st.session_state.page = "signup"
        st.rerun()

def signup_ui():
    st.header("Sign Up (username + password)")
    st.warning("Your password will be securely hashed before storage.")
    col1, col2 = st.columns([3,1])
    with col1:
        username = st.text_input("Choose a username", key="signup_username")
        password = st.text_input("Choose a password", type="password", key="signup_password")
    with col2:
        with st.form("signup_form"):
            st.form_submit_button("Register", type="primary")
            if st.session_state.signup_form:
                if not username or not password:
                    st.warning("Enter both username and password.")
                else:
                    uid = create_user(username.strip(), password)
                    if uid:
                        st.success("Account created. Please log in.")
                        st.session_state.page = "login"
                        time.sleep(0.5)
                        st.rerun()
                    else:
                        st.error("Username already taken or network error.")

    st.markdown("---")
    if st.button("Back to Login"):
        st.session_state.page = "login"
        st.rerun()

# -----------------------
# Dashboard UI
# -----------------------
def dashboard_ui():
    uid = st.session_state.uid
    if not uid:
        st.error("Missing user id. Please login again.")
        st.session_state.logged_in = False
        st.session_state.uid = None
        st.session_state.page = "login"
        st.rerun()
        return

    profile = get_user_profile(uid)
    intake = get_today_intake(uid)
    
    # Calculate core progress variables
    std_goal = AGE_GOALS_ML.get(profile.get("age_group","19-50"), 2500)
    user_goal = int(profile.get("user_goal_ml", std_goal))
    remaining = max(user_goal - intake, 0)
    percent = min((intake / user_goal) * 100 if user_goal > 0 else 0, 100)

    left_col, right_col = st.columns([1,3])

    with left_col:
        st.subheader("Navigate")
        
        # Theme selector 
        theme_options = ["Light","Aqua","Dark"]
        try:
            idx = theme_options.index(st.session_state.theme)
        except Exception:
            idx = 0
            st.session_state.theme = theme_options[0]

        theme_choice = st.selectbox("Theme", theme_options, index=idx)
        if theme_choice != st.session_state.theme:
            st.session_state.theme = theme_choice
            update_user_profile(uid, {"theme": theme_choice})  
            apply_theme(theme_choice)
            st.rerun() 

        st.markdown("")

        # left nav buttons
        if st.button("Home", key="nav_home"):
            st.session_state.nav = "Home"
            st.rerun()
        if st.button("Log Water", key="nav_log"):
            st.session_state.nav = "Log Water"
            st.rerun()
        if st.button("History", key="nav_history"):
            st.session_state.nav = "History"
            st.rerun()
        if st.button("Settings", key="nav_settings"):
            st.session_state.nav = "Settings"
            st.rerun()
        if st.button("Logout", key="nav_logout"):
            st.session_state.logged_in = False
            st.session_state.uid = None
            st.session_state.page = "login"
            st.session_state.nav = "Home"
            st.rerun()

        st.markdown("---")
        st.write("Tip of the day")
        st.info(st.session_state.tip)
        if st.button("New tip", key="new_tip"):
            st.session_state.tip = random.choice(TIPS)
            st.rerun()

    # ensure theme for right pane
    apply_theme(st.session_state.theme)

    with right_col:
        nav = st.session_state.nav

        if nav == "Home":
            st.header("Today's Summary")
            st.write(f"User: **{get_username_by_uid(uid)}**")
            st.write(f"Date: {DATE_STR}")

            col1, col2 = st.columns(2)
            with col1:
                st.subheader("Standard target")
                st.write(f"**{std_goal} ml**")
            with col2:
                st.subheader("Your target")
                st.write(f"**{user_goal} ml**")

            st.metric("Total intake (ml)", f"{intake} ml", delta=f"{remaining} ml to goal" if remaining > 0 else "Goal reached!")
            st.progress(percent / 100)

            svg = generate_bottle_svg(percent)
            st.components.v1.html(svg, height=360, scrolling=False)

            # Lottie progress bar (optional)
            if st_lottie is not None and LOTTIE_PROGRESS is not None:
                try:
                    total_frames = 150
                    end_frame = int(total_frames * (percent / 100.0))
                    if end_frame < 1:
                        end_frame = 1
                    st_lottie(LOTTIE_PROGRESS, loop=False, start_frame=0, end_frame=end_frame, height=120)
                except Exception:
                    pass

            # milestone messages
            if percent >= 100:
                st.success("🎉 Amazing — you reached your daily goal!")
            elif percent >= 75:
                st.info("Great — 75% reached!")
            elif percent >= 50:
                st.info("Nice — 50% reached!")
            elif percent >= 25:
                st.info("Good start — 25% reached!")

        elif nav == "Log Water":
            st.header("Log Water Intake")
            st.write(f"Today's intake: **{intake} ml**")

            c1, c2, c3 = st.columns([1,1,1])
            with c1:
                with st.form("quick_log_form"):
                    st.form_submit_button(f"+{DEFAULT_QUICK_LOG_ML} ml", type="primary")
                    if st.session_state.quick_log_form:
                        new_val = intake + DEFAULT_QUICK_LOG_ML
                        ok = set_today_intake(uid, new_val)
                        if ok:
                            st.success(f"Added {DEFAULT_QUICK_LOG_ML} ml.")
                            st.rerun()
                        else:
                            st.error("Failed to update. Check network/DB rules.")

            with c2:
                with st.form("custom_log_form"):
                    custom = st.number_input("Custom amount (ml)", min_value=0, step=50, key="custom_input")
                    st.form_submit_button("Add custom", type="secondary")
                    if st.session_state.custom_log_form:
                        if custom <= 0:
                            st.warning("Enter amount > 0")
                        else:
                            new_val = intake + int(custom)
                            ok = set_today_intake(uid, new_val)
                            if ok:
                                st.success(f"Added {int(custom)} ml.")
                                st.rerun()
                            else:
                                st.error("Failed to update. Check network/DB rules.")
            
            with c3:
                with st.form("reset_form"):
                    st.form_submit_button("Reset today", type="secondary")
                    if st.session_state.reset_form:
                        ok = reset_today_intake(uid)
                        if ok:
                            st.info("Reset successful.")
                            st.rerun()
                        else:
                            st.error("Failed to reset. Check network/DB rules.")

            st.markdown("---")
            st.subheader("Unit converter")
            cc1, cc2 = st.columns(2)
            with cc1:
                cups = st.number_input("Cups", min_value=0.0, step=0.5, key="conv_cups")
                if st.button("Convert cups → ml", key="conv_to_ml"):
                    ml_conv = round(cups * CUPS_TO_ML, 1)
                    st.success(f"{cups} cups = {ml_conv} ml")
            with cc2:
                ml_in = st.number_input("Milliliters", min_value=0.0, step=50.0, key="conv_ml")
                if st.button("Convert ml → cups", key="conv_to_cups"):
                    cups_conv = round(ml_in / CUPS_TO_ML, 2)
                    st.success(f"{ml_in} ml = {cups_conv} cups")
            
        # HISTORY PAGE
        elif nav == "History":
            st.header("Water Intake History")
            
            # 1. Fetch data 
            past_intake_data = get_past_intake(uid, days_count=7)
            
            st.markdown("---")
            st.subheader("Last 7 Days Bar Chart (Daily Comparison)")
            
            # NEW CHART: Weekly Bar Chart
            try:
                intake_bar_fig = plot_weekly_bar_chart(past_intake_data, user_goal)
                st.pyplot(intake_bar_fig) # 
            except Exception as e:
                st.error(f"Could not generate bar chart. Error: {e}")
                
            st.markdown("---")
            st.subheader("Last 7 Days Trend (Line Chart)")
            
            # EXISTING CHART: Line Chart
            try:
                intake_plot_fig = plot_daily_intake_trend(past_intake_data, user_goal)  
                st.pyplot(intake_plot_fig)  # 
            except Exception as e:
                st.error(f"Could not generate trend graph. Error: {e}")
                st.info("Ensure you have Matplotlib installed and some data logged.")


        elif nav == "Settings":
            st.header("Settings & Profile")
            age_keys = list(AGE_GOALS_ML.keys())
            try:
                idx = age_keys.index(profile.get("age_group", "19-50"))
            except Exception:
                idx = 2
            age_choice = st.selectbox("Select age group", age_keys, index=idx)
            suggested = AGE_GOALS_ML[age_choice]
            st.write(f"Suggested: {suggested} ml")
            
            current_goal = int(profile.get("user_goal_ml", suggested))
            user_goal_val = st.number_input("Daily goal (ml)", min_value=500, max_value=10000, value=current_goal, step=50)
            
            if st.button("Save profile", key="save_profile"):
                ok = update_user_profile(uid, {"age_group": age_choice, "user_goal_ml": int(user_goal_val)})
                if ok:
                    st.success("Profile saved. Please navigate to Home to see the update.")
                else:
                    st.error("Failed to save profile. Check network/DB rules.")


# -----------------------
# App routing
# -----------------------
if not st.session_state.logged_in:
    if st.session_state.page == "signup":
        signup_ui()
    else:
        login_ui()
else:
    dashboard_ui()
