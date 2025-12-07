import streamlit as st
import streamlit.components.v1 as components
import requests
import json
import base64
import random
import matplotlib.pyplot as plt
from datetime import date, timedelta, datetime
import time
import os

# --- Configuration & Global Variables ---
try:
    from streamlit_lottie import st_lottie
except Exception:
    st_lottie = None
    
# NOTE: Replace this with your actual Firebase URL if deploying
FIREBASE_URL = "https://waterhydrator-9ecad-default-rtdb.asia-southeast1.in-asia.firebasedatabase.app"
USERS_NODE = "users"
REQUEST_TIMEOUT = 8
TODAY = date.today().isoformat()
DATE_FORMAT_DISPLAY = "%b %d, %Y"

AGE_GROUP_DEFAULTS = {
    "6-12": 1600,
    "13-18": 2000,
    "19-50": 2500,
    "65+": 2000,
}
DEFAULT_QUICK_ADD = 250
CUPS_TO_ML = 236.588

HYDRATION_TIPS = [
    "Keep a filled water bottle visible on your desk.",
    "Drink a glass (250 ml) after every bathroom break.",
    "Start your day with a glass of water.",
    "Add lemon or cucumber for natural flavor.",
    "Set small hourly reminders and sip regularly.",
    "Drink a small cup of water before each meal.",
    "Take a few sips every 20–30 minutes while studying.",
    "Carry a lightweight bottle when you go outside.",
    "Refill your bottle when it becomes half empty.",
    "Drink extra water on hot or humid days.",
    "Keep a bottle near your bed for morning and night sips.",
    "Choose water instead of soft drinks when thirsty.",
    "Eat fruits with high water content like watermelon or oranges.",
    "Drink water slowly instead of all at once.",
]

# --- Firebase Interaction Functions ---

def fb_path(path: str) -> str:
    path = path.strip("/")
    return f"{FIREBASE_URL}/{path}.json"

def fb_get(path: str):
    try:
        r = requests.get(fb_path(path), timeout=REQUEST_TIMEOUT)
        return r.json() if r.status_code == 200 else None
    except requests.exceptions.RequestException as e:
        print(f"Firebase GET error on {path}: {e}")
        return None

def fb_post(path: str, data: dict):
    try:
        r = requests.post(fb_path(path), json=data, timeout=REQUEST_TIMEOUT)
        return r.json() if r.status_code in (200, 201) else None
    except requests.exceptions.RequestException as e:
        print(f"Firebase POST error on {path}: {e}")
        return None

def fb_patch(path: str, data: dict):
    try:
        r = requests.patch(fb_path(path), json=data, timeout=REQUEST_TIMEOUT)
        return r.status_code in (200, 201)
    except requests.exceptions.RequestException as e:
        print(f"Firebase PATCH error on {path}: {e}")
        return False

def find_user(username: str):
    all_users = fb_get(USERS_NODE)
    if not isinstance(all_users, dict):
        return None, None
    for uid, rec in all_users.items():
        if isinstance(rec, dict) and rec.get("username") == username:
            return uid, rec
    return None, None

def create_user(username: str, password: str):
    if not username or not password:
        print("DEBUG: Username or password empty.")
        return None

    # 1. Check if username already exists
    existing_uid, _ = find_user(username)
    if existing_uid:
        print(f"DEBUG: Username '{username}' already exists. Returning 'EXISTS'.")
        return "EXISTS" # Signal for username conflict

    # 2. Prepare user payload
    default_goal = AGE_GROUP_DEFAULTS["19-50"]
    payload = {
        "username": username,
        "password": password,
        "created_at": TODAY,
        "profile": {
            "age_group": "19-50",
            "user_goal_ml": default_goal,
            "theme": "Light"
        }
    }
    
    # 3. Attempt to post to Firebase
    try:
        url = fb_path(USERS_NODE)
        print(f"DEBUG: Attempting POST to {url} with payload for '{username}'.")
        r = requests.post(url, json=payload, timeout=REQUEST_TIMEOUT)

        # 4. Check response status
        if r.status_code in (200, 201):
            print(f"DEBUG: POST successful. Status {r.status_code}. New UID received.")
            return r.json().get("name") # Returns the generated push ID (UID)
        else:
            # Handle non-success HTTP status codes (e.g., 400, 401, 500)
            print(f"ERROR: Firebase POST failed with status code {r.status_code}.")
            print(f"ERROR: Response text: {r.text}")
            return None

    except requests.exceptions.RequestException as e:
        # Handle network-level errors (timeouts, DNS, connection refused)
        print(f"CRITICAL ERROR: Firebase POST request failed (Network/Timeout). Details: {e}")
        return "NETWORK_ERROR" # Signal for critical network failure

def login_user(username: str, password: str):
    uid, record = find_user(username)
    if uid and record and record.get("password") == password:
        return True, uid
    return False, None

def get_profile(uid: str):
    profile = fb_get(f"{USERS_NODE}/{uid}/profile") or {}
    age_group = profile.get("age_group", "19-50")
    goal = profile.get("user_goal_ml", AGE_GROUP_DEFAULTS.get(age_group, 2500))
    try:
        goal = int(goal)
    except:
        goal = 2500
    return {
        "age_group": age_group, 
        "user_goal_ml": goal, 
        "theme": profile.get("theme", "Light")
    }

def update_profile(uid: str, updates: dict):
    return fb_patch(f"{USERS_NODE}/{uid}/profile", updates)

def get_intake(uid: str) -> int:
    raw = fb_get(f"{USERS_NODE}/{uid}/days/{TODAY}/intake")
    try:
        return int(raw) if raw is not None else 0
    except:
        return 0

def get_log_entries(uid: str) -> list:
    entries = fb_get(f"{USERS_NODE}/{uid}/days/{TODAY}/log_entries")
    if not isinstance(entries, dict):
        return []
    sorted_entries = sorted(entries.values(), key=lambda x: x.get('timestamp', ''))
    return sorted_entries

def update_intake(uid: str, amount: int) -> bool:
    validated_amount = max(0, amount)
    return fb_patch(f"{USERS_NODE}/{uid}/days/{TODAY}", {"intake": validated_amount})

def log_water_entry(uid: str, amount: int) -> bool:
    if amount <= 0: return False
    timestamp = datetime.now().isoformat()
    entry = {
        "amount_ml": amount,
        "timestamp": timestamp,
    }
    response = fb_post(f"{USERS_NODE}/{uid}/days/{TODAY}/log_entries", entry)
    return response is not None

def reset_intake(uid: str) -> bool:
    fb_patch(f"{USERS_NODE}/{uid}/days/{TODAY}", {"intake": 0})
    try:
        # Attempt to delete the log entries node
        requests.delete(fb_path(f"{USERS_NODE}/{uid}/days/{TODAY}/log_entries"), timeout=REQUEST_TIMEOUT)
        return True
    except requests.exceptions.RequestException as e:
        print(f"Firebase DELETE error on log entries: {e}")
        return False

def get_history(uid: str, days: int = 7) -> dict:
    history_data = {}
    today_date = date.today()
    for i in range(days):
        d = (today_date - timedelta(days=i)).isoformat()
        raw_intake = fb_get(f"{USERS_NODE}/{uid}/days/{d}/intake")
        intake_value = 0
        try:
            intake_value = int(raw_intake) if raw_intake is not None else 0
        except:
            intake_value = 0
        history_data[d] = max(0, intake_value)
    return {d: history_data[d] for d in sorted(history_data.keys())}

# --- Streamlit State & Styling ---

DEFAULT_STATE = {
    "logged_in": False,
    "uid": None,
    "view": "login",
    "nav": "Home",
    "theme": "Light",
    "tip": "",
    "log_update": 0 
}

def initialize_session_state():
    for key, value in DEFAULT_STATE.items():
        st.session_state.setdefault(key, value)
    st.session_state.setdefault("tip", random.choice(HYDRATION_TIPS))

def apply_theme(theme: str):
    if theme == "Light":
        bg, fg = "#ffffff", "#000000"
        metric_bg = "#f7f7f7"
        metric_fg = "#000000"
        st.session_state.theme_fg = fg
        st.session_state.theme_bg = bg
    elif theme == "Aqua":
        bg, fg = "#e8fbff", "#004455"
        metric_bg = "#d9f7ff"
        metric_fg = "#005577"
        st.session_state.theme_fg = fg
        st.session_state.theme_bg = bg
    else: # Dark
        bg, fg = "#0f1720", "#e6eef6"
        metric_bg = "#1a2634"
        metric_fg = "#e6eef6"
        st.session_state.theme_fg = fg
        st.session_state.theme_bg = bg
        
    st.markdown(
        f"""
        <style>
        .stApp {{
            background-color: {bg} !important;
            color: {fg} !important;
        }}
        h1, h2, h3, h4, p, span, label, div.st-emotion-cache-1cypcdb {{ color: {fg} !important; }}
        div[data-testid="metric-container"] {{
            background-color: {metric_bg} !important;
            border-radius: 12px;
            padding: 12px;
            box-shadow: 0 4px 6px rgba(0, 0, 0, 0.05);
        }}
        div[data-testid="metric-container"] * {{ color: {metric_fg} !important; }}
        .stHtmlContainer svg text {{
             fill: var(--text-color) !important;
        }}
        </style>
        """,
        unsafe_allow_html=True,
    )

st.set_page_config(page_title="WaterBuddy: Hydration Tracker & Game", layout="wide")
initialize_session_state()
apply_theme(st.session_state.theme)

# --- Visualization Components ---

def render_bottle(percent: float):
    percent = min(max(percent, 0), 100)
    height = 300
    filled = int((percent / 100) * height)
    fill_color = "#5dade2"
    return f"""
    <svg width="120" height="350" xmlns="http://www.w3.org/2000/svg">
        <rect x="30" y="20" width="60" height="300" rx="20" ry="20"
              fill="none" stroke="#3498db" stroke-width="4"/>
        <rect x="34" y="{320-filled}" width="52" height="{filled}"
              rx="16" ry="16" fill="{fill_color}"/>
        <text x="60" y="340" text-anchor="middle"
              font-size="20" fill="var(--text-color)">{percent:.0f}%</text>
    </svg>
    """

def congratulations_banner():
    # Burst and Balloon Pop Animation CSS
    banner_css = """
    <style>
    @keyframes burstIn {
      0% {
        transform: scale(0.5);
        opacity: 0;
        box-shadow: 0 0 0 rgba(0, 0, 0, 0);
      }
      50% {
        transform: scale(1.1);
        opacity: 1;
        box-shadow: 0 0 30px #2ecc71, 0 0 10px #ffffff; 
      }
      100% {
        transform: scale(1);
        opacity: 1;
        box-shadow: 0 -4px 12px rgba(0, 0, 0, 0.2);
      }
    }
    @keyframes balloonFloat {
      0% { transform: translateY(0) rotate(0deg); opacity: 1; }
      100% { transform: translateY(-500px) rotate(30deg); opacity: 0; }
    }
    .congrats-banner {
      position: fixed;
      bottom: 0;
      left: 0;
      width: 100%;
      background-color: #2ecc71;
      color: white;
      text-align: center;
      padding: 15px;
      z-index: 1000;
      box-shadow: 0 -4px 12px rgba(0, 0, 0, 0.2);
      animation: burstIn 0.8s cubic-bezier(0.175, 0.885, 0.32, 1.275) forwards;
      font-size: 24px;
      font-weight: bold;
      border-top-left-radius: 10px;
      border-top-right-radius: 10px;
      overflow: hidden;
    }
    .balloon {
        position: absolute;
        bottom: 0;
        font-size: 30px;
        animation: balloonFloat 4s ease-out forwards;
        z-index: 999;
        pointer-events: none;
    }
    .balloon:nth-child(1) { left: 10%; animation-delay: 0.1s; color: #ff6347; }
    .balloon:nth-child(2) { left: 30%; animation-delay: 0.5s; color: #ffd700; }
    .balloon:nth-child(3) { right: 30%; animation-delay: 0.3s; color: #1e90ff; }
    .balloon:nth-child(4) { right: 10%; animation-delay: 0.7s; color: #ff69b4; }
    </style>
    """
    st.markdown(banner_css, unsafe_allow_html=True)
    
    balloon_html = """
    <div class="balloon" style="left: 10%;">🎈</div>
    <div class="balloon" style="left: 30%;">🎈</div>
    <div class="balloon" style="right: 30%;">🎈</div>
    <div class="balloon" style="right: 10%;">🎈</div>
    """
    
    banner_html = f"""
    <div class="congrats-banner">
        {balloon_html}
        <span style="position: relative; z-index: 1001;">
            💥 CONGRATULATIONS! You hit your daily water goal! 💥
        </span>
    </div>
    """
    st.markdown(banner_html, unsafe_allow_html=True)

def render_history_graph(history: dict, goal: int):
    days = sorted(history.keys())
    values = [history[d] for d in days]
    labels = [date.fromisoformat(d).strftime("%a %m/%d") for d in days]
    fg_color = st.session_state.theme_fg
    
    fig, ax = plt.subplots(figsize=(9, 5))
    fig.patch.set_facecolor('none')
    ax.set_facecolor('none')
    
    ax.plot(labels, values, marker="o", color="#3498db", linewidth=2, label="Intake")
    ax.axhline(goal, color="#2ecc71", linestyle="--", linewidth=1.5, label="Goal")
    
    ax.set_ylim(bottom=0)
    ax.set_title("Water Intake (Last 7 Days)", color=fg_color, fontsize=16)
    ax.set_ylabel("Intake (ml)", color=fg_color, fontsize=12)
    ax.set_xlabel("Date", color=fg_color, fontsize=12)
    
    ax.tick_params(axis='x', rotation=45, colors=fg_color, labelsize=10)
    ax.tick_params(axis='y', colors=fg_color, labelsize=10)
    
    for spine in ax.spines.values():
        spine.set_color(fg_color)
        
    ax.grid(True, axis='y', alpha=0.3, color=fg_color)
    ax.legend(loc='upper left', frameon=False, fontsize=10)
    fig.tight_layout()
    return fig

# --- View Pages ---

def view_login():
    st.header("Login to WaterBuddy")
    username = st.text_input("Username", key="login_username_input")
    password = st.text_input("Password", type="password", key="login_password_input")
    
    col_btn_login, col_btn_signup = st.columns(2)
    
    with col_btn_login:
        if st.button("Sign In", key="login_btn", use_container_width=True):
            if not username or not password:
                st.error("Please enter both username and password.")
                return
                
            ok, uid = login_user(username.strip(), password)
            
            if ok:
                st.session_state.logged_in = True
                st.session_state.uid = uid
                profile = get_profile(uid)
                st.session_state.theme = profile.get("theme", "Light")
                apply_theme(st.session_state.theme)
                st.session_state.view = "dashboard"
                st.success("Welcome back! Loading dashboard...")
                time.sleep(0.1)
                st.rerun()
            else:
                st.error("Invalid username or password.")
                
    with col_btn_signup:
        if st.button("Create new account", key="go_signup", use_container_width=True):
            st.session_state.view = "signup"
            st.rerun()

def view_signup():
    st.header("Create New WaterBuddy Account")
    st.warning("⚠️ **Security Warning:** This is a demo. Passwords are NOT hashed. Do not use a real password.")
    
    username = st.text_input("Choose a Username", key="signup_username_input")
    password = st.text_input("Choose a Password", type="password", key="signup_password_input")
    
    col_btn_register, col_btn_back = st.columns(2)
    
    with col_btn_register:
        if st.button("Register Account", key="signup_btn", use_container_width=True):
            if not username or not password:
                st.error("Please enter both username and password.")
                return
                
            result = create_user(username.strip(), password)
            
            if result and result not in ["EXISTS", "NETWORK_ERROR"]:
                st.success("Account created successfully! You may now log in.")
                st.session_state.view = "login"
                st.rerun()
            elif result == "EXISTS":
                st.error(f"❌ **Error:** The username **'{username}'** is already taken. Please choose another.")
            elif result == "NETWORK_ERROR":
                st.error("🚨 **CRITICAL NETWORK ERROR:** Could not connect to the database. Check your `FIREBASE_URL` or internet connection.")
            else:
                st.error("❗ **Database Error:** Failed to create account. Check the Streamlit console logs for details.")

    with col_btn_back:
        if st.button("Back to Login", key="go_login", use_container_width=True):
            st.session_state.view = "login"
            st.rerun()

def view_log(uid: str, intake: int, goal: int):
    st.header("💧 Log Water Intake")
    st.markdown(f"Current Daily Intake: **{intake} ml** | Target Goal: **{goal} ml**")
    st.markdown("---")
    
    st.subheader("Quick Add")
    col1, col2 = st.columns(2)
    
    with col1:
        if st.button(f"➕ Add {DEFAULT_QUICK_ADD} ml", use_container_width=True):
            if log_water_entry(uid, DEFAULT_QUICK_ADD):
                new_intake = intake + DEFAULT_QUICK_ADD
                update_intake(uid, new_intake)
                st.session_state.log_update += 1
                st.success(f"Added {DEFAULT_QUICK_ADD} ml. New total: {new_intake} ml.")
                st.rerun()
            else:
                st.error("Failed to update intake due to a network error.")
                
    with col2:
        if st.button("🔄 Reset Today's Intake", use_container_width=True):
            if reset_intake(uid):
                st.session_state.log_update += 1
                st.info("Today's intake has been reset to 0 ml (including log entries).")
                st.rerun()
            else:
                st.error("Failed to reset intake.")
                
    st.markdown("---")
    
    st.subheader("Custom Log")
    with st.form("custom_log_form"):
        custom = st.number_input("Enter amount to add (ml):", min_value=0, step=50)
        submitted = st.form_submit_button("Add Custom Amount")
        
        if submitted and custom > 0:
            if log_water_entry(uid, custom):
                new_intake = intake + custom
                update_intake(uid, new_intake)
                st.session_state.log_update += 1
                st.success(f"Added {custom} ml. New total: {new_intake} ml.")
                st.rerun()
            else:
                st.error("Failed to process custom amount.")
                
    st.markdown("---")
    
    st.subheader("Unit Conversion Utility")
    cc1, cc2 = st.columns(2)
    
    with cc1:
        cups = st.number_input("Cups to Milliliters (cups):", min_value=0.0, step=0.5)
        ml_result = round(cups * CUPS_TO_ML, 1)
        st.markdown(f"Result: **{ml_result} ml**")
        
    with cc2:
        ml_in = st.number_input("Milliliters to Cups (ml):", min_value=0.0, step=50.0)
        cups_result = round(ml_in / CUPS_TO_ML, 2)
        st.markdown(f"Result: **{cups_result} cups**")

def view_progress_log(uid: str, goal: int, intake: int):
    st.header("🕒 Hourly Water Log")
    st.markdown(f"Visualizing your **{intake} ml** intake towards your **{goal} ml** goal.")
    st.markdown("---")
    
    log_entries = get_log_entries(uid)
    log_data_list = []
    
    for entry in log_entries:
        try:
            ts = datetime.fromisoformat(entry['timestamp'])
            log_data_list.append({
                "hour": ts.hour,
                "amount": entry['amount_ml']
            })
        except:
            continue
            
    log_data_json = json.dumps(log_data_list)
    total_intake = intake
    
    # JavaScript/HTML/CSS for the Circular Progress Clock
    progress_clock_code = f"""
    (function() {{
        const LOG_DATA = {log_data_json};
        const TOTAL_GOAL = {goal};
        const TOTAL_INTAKE = {total_intake};
        const COLOR_WATER = "#3498db";
        const COLOR_GOAL_ACHIEVED = "#2ecc71";
        const COLOR_BACKGROUND = "#eee";
        const COLOR_TEXT = getComputedStyle(document.body).getPropertyValue('--text-color').trim() || '#000000';
        
        const canvas = document.getElementById('logClockCanvas');
        if (!canvas) return;
        
        const ctx = canvas.getContext('2d');
        const centerX = canvas.width / 2;
        const centerY = canvas.height / 2;
        const outerRadius = 180;
        const barWidth = 15;
        const hourRadius = 120;
        const hourDotRadius = 6;
        const hourStart = 6;
        const hourEnd = 22;
        
        // Group amounts by hour
        const hourlyAmounts = new Array(24).fill(0);
        LOG_DATA.forEach(entry => {{
            hourlyAmounts[entry.hour] += entry.amount;
        }});
        
        // Determine the maximum hourly amount for scaling the bars
        let maxHourlyAmount = 0;
        for (let h = hourStart; h <= hourEnd; h++) {{
            maxHourlyAmount = Math.max(maxHourlyAmount, hourlyAmounts[h]);
        }}

        function drawClockFace() {{
            ctx.strokeStyle = COLOR_BACKGROUND;
            ctx.lineWidth = 1;
            ctx.beginPath();
            ctx.arc(centerX, centerY, outerRadius, 0, 2 * Math.PI);
            ctx.stroke();
            
            // Draw hour markers
            for (let i = 0; i < 24; i++) {{
                const angle = (i / 24) * 2 * Math.PI - Math.PI / 2;
                const x = centerX + Math.cos(angle) * hourRadius;
                const y = centerY + Math.sin(angle) * hourRadius;
                
                ctx.fillStyle = (i >= hourStart && i <= hourEnd) ? COLOR_TEXT : '#ccc';
                ctx.beginPath();
                ctx.arc(x, y, hourDotRadius, 0, 2 * Math.PI);
                ctx.fill();
                
                // Hour text
                ctx.fillStyle = COLOR_TEXT;
                ctx.font = '14px Arial';
                ctx.textAlign = 'center';
                ctx.textBaseline = 'middle';
                const textX = centerX + Math.cos(angle) * (hourRadius + 20);
                const textY = centerY + Math.sin(angle) * (hourRadius + 20);
                ctx.fillText(i, textX, textY);
            }}
        }}

        function drawHourlyLog() {{
            for (let h = hourStart; h <= hourEnd; h++) {{
                const amount = hourlyAmounts[h];
                if (amount === 0) continue;
                
                // Scale the bar thickness based on the amount logged
                const scaleFactor = (maxHourlyAmount > 0) ? amount / maxHourlyAmount : 0;
                const thickness = barWidth * (0.2 + scaleFactor * 0.8);
                
                // Calculate angles
                const startAngle = (h / 24) * 2 * Math.PI - Math.PI / 2;
                const endAngle = ((h + 1) / 24) * 2 * Math.PI - Math.PI / 2;
                
                ctx.beginPath();
                ctx.lineWidth = thickness;
                ctx.strokeStyle = COLOR_WATER;
                
                // Draw the arc section
                ctx.arc(centerX, centerY, outerRadius - barWidth / 2, startAngle, endAngle);
                ctx.stroke();
            }}
        }}

        function drawCenterMetric() {{
            const percent = Math.min(100, (TOTAL_INTAKE / TOTAL_GOAL) * 100);
            const metricColor = (TOTAL_INTAKE >= TOTAL_GOAL) ? COLOR_GOAL_ACHIEVED : COLOR_WATER;
            
            // Draw a thick progress arc for the total goal
            ctx.beginPath();
            ctx.lineWidth = barWidth;
            ctx.strokeStyle = metricColor;
            const progressAngle = (percent / 100) * 2 * Math.PI;
            ctx.arc(centerX, centerY, outerRadius, -Math.PI / 2, -Math.PI / 2 + progressAngle);
            ctx.stroke();

            // Center Text
            ctx.fillStyle = metricColor;
            ctx.font = '50px Arial';
            ctx.textAlign = 'center';
            ctx.textBaseline = 'middle';
            ctx.fillText(Math.round(percent) + '%', centerX, centerY - 20);
            
            ctx.font = '20px Arial';
            ctx.fillStyle = COLOR_TEXT;
            ctx.fillText(TOTAL_INTAKE + ' / ' + TOTAL_GOAL + ' ml', centerX, centerY + 20);
            
            ctx.font = '14px Arial';
            ctx.fillText('Hourly Intake Intensity', centerX, centerY + outerRadius + 30);
        }}
        
        function draw() {{
            ctx.clearRect(0, 0, canvas.width, canvas.height);
            drawClockFace();
            drawHourlyLog();
            drawCenterMetric();
        }}
        draw();
    }})();
    """
    
    html_content = f"""
    <div style="text-align: center;">
        <canvas id="logClockCanvas" width="450" height="450" style="margin: 20px;"></canvas>
    </div>
    <script>{progress_clock_code}</script>
    """
    st.components.v1.html(html_content, height=500)
    
    st.markdown("---")
    
    st.subheader("Recent Entries")
    if log_entries:
        # Prepare log entries for display
        display_data = []
        for entry in reversed(log_entries):
            try:
                ts = datetime.fromisoformat(entry['timestamp'])
                display_data.append({
                    "Time": ts.strftime("%I:%M %p"),
                    "Amount (ml)": entry['amount_ml']
                })
            except:
                continue
        st.dataframe(display_data, use_container_width=True, hide_index=True)
    else:
        st.info("No water log entries for today yet.")

def view_history(uid: str, goal: int):
    st.header("📅 Weekly Hydration History")
    history = get_history(uid, 7)
    
    st.subheader("Intake Trend Over 7 Days")
    try:
        fig = render_history_graph(history, goal)
        st.pyplot(fig)
    except Exception as e:
        st.error("Could not render the chart. Check data format or Matplotlib installation.")
        print(f"Graphing Error: {e}")
        
    st.markdown("---")
    
    st.subheader("Detailed History Table")
    sorted_dates = reversed(sorted(history.keys()))
    table_data = {
        "Date": [date.fromisoformat(d).strftime(DATE_FORMAT_DISPLAY) for d in sorted_dates],
        "Intake (ml)": [history[d] for d in reversed(sorted(history.keys()))]
    }
    
    if table_data["Date"]:
        st.dataframe(table_data, use_container_width=True, hide_index=True)
    else:
        st.info("No historical intake data found for the last 7 days.")

def view_settings(uid: str, profile: dict):
    st.header("⚙️ User and App Settings")
    
    st.subheader("Hydration Goal Configuration")
    
    current_theme = profile.get("theme", "Light")
    current_age_group = profile["age_group"]
    current_goal = profile["user_goal_ml"]
    
    age_group_list = list(AGE_GROUP_DEFAULTS.keys())
    selected_age = st.selectbox(
        "Select Age Group (for default goal suggestions):", 
        age_group_list, 
        index=age_group_list.index(current_age_group)
    )
    
    st.info(f"The recommended goal for the **{selected_age}** group is **{AGE_GROUP_DEFAULTS[selected_age]} ml**.")
    
    custom_goal = st.number_input(
        "Set Your Custom Daily Goal (ml):", 
        min_value=500, 
        max_value=10000, 
        value=current_goal, 
        step=100,
        help="This is the target amount of water you aim to drink each day."
    )
    
    st.markdown("---")
    
    st.subheader("Application Theme")
    theme_options = ["Light", "Aqua", "Dark"]
    selected_theme = st.selectbox(
        "Choose App Theme:", 
        theme_options, 
        index=theme_options.index(current_theme),
        help="Changes the color scheme of the entire application."
    )
    
    st.markdown("---")
    
    if st.button("💾 Save All Settings", use_container_width=True):
        updates = {
            "age_group": selected_age, 
            "user_goal_ml": int(custom_goal),
            "theme": selected_theme
        }
        
        if update_profile(uid, updates):
            st.success("Settings saved successfully!")
            if selected_theme != st.session_state.theme:
                st.session_state.theme = selected_theme
                apply_theme(selected_theme)
                st.info("Theme updated. Reloading dashboard...")
            st.rerun()
        else:
            st.error("Failed to save settings. Please check your connection.")

def view_runner_game():
    st.header("🎮 WaterBuddy Runner Game 🤖💧")
    
    st.markdown("### How to Play")
    st.markdown(
        """
        * Press **SPACE** to start the game and to jump.
        * Collect the blue droplets (coins) for points.
        * Jump over the gray blocks. You can land on them!
        * Press **R** to restart the game in-progress.
        """
    )
    
    st.markdown("---")
    
    current_theme = st.session_state.get("theme", "Light")
    if current_theme == "Aqua":
        canvas_bg_gradient = "linear-gradient(#d0f7ff, #b5efff)"
    elif current_theme == "Dark":
        canvas_bg_gradient = "linear-gradient(#3c4854, #2a3440)"
    else:
        canvas_bg_gradient = "linear-gradient(#ffefd5, #ffd5c8)"

    # Note: Requires a ROBO.png file in the same directory or 'assets/' folder
    try:
        try:
            with open("assets/ROBO.png", "rb") as f:
                robo_data = f.read()
        except FileNotFoundError:
            with open("ROBO.png", "rb") as f:
                robo_data = f.read()
        robo_base64 = base64.b64encode(robo_data).decode()
        robo_url = f"data:image/png;base64,{robo_base64}"
    except FileNotFoundError:
        st.error("🚨 **Error:** The image file **ROBO.png** is required but was not found. Game cannot load.")
        return

    js_game_code = f"""
    (function() {{
      if (window.__waterbuddyGameStarted) return;
      window.__waterbuddyGameStarted = true;
      
      const canvas = document.getElementById("gameCanvas");
      const ctx = canvas.getContext("2d");
      const groundY = 350;
      const STREAMLIT_TEXT_COLOR = getComputedStyle(document.body).getPropertyValue('--text-color').trim() || '#000000'; 
      
      window.__waterbuddyTotalCoins = window.__waterbuddyTotalCoins || 0;
      let gameState = "menu";
      let gameOver = false;
      let playerImg = new Image();
      playerImg.src = "{robo_url}";
      let player = {{ x: 150, y: groundY, width: 120, height: 140, velocityY: 0, gravity: 0.4, jumpPower: -12, onGround: true }};
      let obstacles = [];
      let droplets = [];
      let speed = 6;
      let score = 0;           
      let coinsCollected = 0;   
      let frame = 0;

      document.addEventListener("keydown", function(e) {{
        if (e.code === "Space") {{
          e.preventDefault();
          if (gameState === "menu") {{
            startGame();
          }} else if (gameState === "playing" && player.onGround && !gameOver) {{
            player.velocityY = player.jumpPower;
            player.onGround = false;
          }} else if (gameState === "gameover") {{
            gameState = "menu";
            drawMenu();
          }}
        }}
        if (e.code === "KeyR" && gameState === "playing") {{
          restart();
        }}
      }});

      function spawnObstacle() {{
        obstacles.push({{ type: "block", x: canvas.width + 50, y: 430, width: 60, height: 60 }});
      }}
      function spawnDroplet() {{
        const y = Math.random() * 200 + 150;
        droplets.push({{ x: canvas.width + 50, y, width: 30, height: 40 }});
      }}

      function drawPlayer() {{
        ctx.drawImage(playerImg, player.x, player.y, player.width, player.height);
      }}

      function drawObstacle(obs) {{
        ctx.fillStyle = "#666";
        ctx.fillRect(obs.x, obs.y, obs.width, obs.height);
      }}

      function drawDroplet(drop) {{
        ctx.fillStyle = "#00aaff";
        ctx.beginPath();
        ctx.ellipse(drop.x + 15, drop.y + 20, 15, 20, 0, 0, Math.PI * 2);
        ctx.fill();
      }}

      function drawHUD() {{
        ctx.fillStyle = STREAMLIT_TEXT_COLOR; 
        ctx.font = "28px Arial";
        ctx.fillText("Score: " + score, 30, 40);
        ctx.fillText("Coins: " + coinsCollected, 30, 80);
      }}

      function drawMenu() {{
        ctx.clearRect(0, 0, canvas.width, canvas.height);
        ctx.fillStyle = "#222"; 
        ctx.fillRect(0, 0, canvas.width, canvas.height);
        ctx.fillStyle = "#fff";
        ctx.font = "48px Arial";
        ctx.fillText("WaterBuddy Runner", canvas.width/2 - 250, canvas.height/2 - 120);
        ctx.font = "24px Arial";
        ctx.fillText("Press SPACE to Start", canvas.width/2 - 120, canvas.height/2 - 40);
        ctx.fillText("Jump with SPACE. Press R to restart.", canvas.width/2 - 170, canvas.height/2);
        ctx.font = "28px Arial";
        ctx.fillText("Total Coins: " + window.__waterbuddyTotalCoins, canvas.width/2 - 120, canvas.height/2 + 60);
      }}

      function aabb(ax, ay, aw, ah, bx, by, bw, bh) {{
        return ax < bx + bw && ax + aw > bx && ay < by + bh && ay + ah > by;
      }}

      function playerCollisionBox() {{
        const insetX = 20, insetY = 20;
        return {{
          x: player.x + insetX,
          y: player.y + insetY,
          w: player.width - insetX * 2,
          h: player.height - insetY * 2
        }};
      }}

      function gameLoop() {{
        if (gameState !== "playing") return;
        
        ctx.clearRect(0, 0, canvas.width, canvas.height);
        
        player.velocityY += player.gravity;
        player.y += player.velocityY;
        player.onGround = false;

        if (player.y >= groundY) {{
          player.y = groundY;
          player.velocityY = 0;
          player.onGround = true;
        }}

        if (frame % 70 === 0) spawnObstacle();
        if (frame % 55 === 0) spawnDroplet();

        for (let i = obstacles.length - 1; i >= 0; i--) {{
          const obs = obstacles[i];
          obs.x -= speed;
          drawObstacle(obs);

          const pcb = playerCollisionBox();
          const overlapping = aabb(pcb.x, pcb.y, pcb.w, pcb.h, obs.x, obs.y, obs.width, obs.height);
          
          if (overlapping) {{
            const falling = player.velocityY >= 0;
            const playerFeetY = player.y + player.height;
            const obsTopY = obs.y;
            
            if (falling && playerFeetY > obsTopY) {{ 
              player.y = obsTopY - player.height;
              player.velocityY = 0;
              player.onGround = true;
              continue;
            }}
            
            if (player.velocityY < 0 && player.y <= obs.y + obs.height) {{
              player.velocityY = 0;
              continue;
            }}
            
            endGame();
            break;
          }}

          if (obs.x < -120) obstacles.splice(i, 1);
        }}

        for (let i = droplets.length - 1; i >= 0; i--) {{
          const drop = droplets[i];
          drop.x -= speed;
          drawDroplet(drop);

          const pcb = playerCollisionBox();
          const m = 5; // Margin for collision detection
          if (aabb(pcb.x, pcb.y, pcb.w, pcb.h, drop.x + m, drop.y + m, drop.width - 2*m, drop.height - 2*m)) {{
            coinsCollected += 1;                 
            window.__waterbuddyTotalCoins += 1;  
            score += 100;                        
            droplets.splice(i, 1);
          }} else if (drop.x < -60) {{
            droplets.splice(i, 1);
          }}
        }}

        score += Math.floor(speed);
        
        drawPlayer();
        drawHUD();
        
        speed += 0.002;
        frame++;
        requestAnimationFrame(gameLoop);
      }}

      function startGame() {{
        gameState = "playing";
        gameOver = false;
        obstacles = [];
        droplets = [];
        speed = 6;
        score = 0;
        coinsCollected = 0;
        frame = 0;
        player.x = 150;
        player.y = groundY;
        player.velocityY = 0;
        player.onGround = true;
        requestAnimationFrame(gameLoop);
      }}

      function endGame() {{
        gameOver = true;
        gameState = "gameover";
        ctx.fillStyle = "rgba(0,0,0,0.5)";
        ctx.fillRect(0, 0, canvas.width, canvas.height);
        ctx.fillStyle = "#fff";
        ctx.font = "32px Arial";
        ctx.fillText("Game Over! Final Score: " + score, canvas.width/2 - 200, canvas.height/2 - 20);
        ctx.font = "22px Arial";
        ctx.fillText("Run Coins: " + coinsCollected, canvas.width/2 - 90, canvas.height/2 + 20);
        ctx.font = "20px Arial";
        ctx.fillText("Press SPACE to return to Menu", canvas.width/2 - 150, canvas.height/2 + 60);
      }}

      function restart() {{
        startGame();
      }}

      playerImg.onload = function() {{
        drawMenu();
        setTimeout(() => {{
          canvas.focus(); 
        }}, 0);
      }};
    }})();
    """
    
    html_content = f"""
    <style>
    canvas {{
        background: {canvas_bg_gradient};
        display: block;
        margin: 0 auto;
        border-radius: 10px;
        border: 2px solid #333;
    }}
    #gameCanvas:focus {{
        outline: 3px solid #5dade2; 
    }}
    </style>
    <canvas id="gameCanvas" width="900" height="500" tabindex="0"></canvas>
    <script>{js_game_code}</script>
    """
    components.html(html_content, height=600)

# --- Layout and Navigation ---

def render_sidebar_navigation(uid):
    st.subheader("🧭 Navigation Menu")
    
    nav_options = ["Home", "Log Water", "Progress Log", "History", "Settings", "Runner Game", "Logout"]
    
    for option in nav_options:
        if st.button(option, key=f"nav_{option}", use_container_width=True):
            if option == "Logout":
                st.session_state.logged_in = False
                st.session_state.uid = None
                st.session_state.view = "login"
            else:
                st.session_state.nav = option
            st.rerun()

    st.markdown("---")
    
    st.subheader("🎨 Theme Quick View")
    theme_options = ["Light", "Aqua", "Dark"]
    try:
        idx = theme_options.index(st.session_state.theme)
    except ValueError:
        idx = 0
        
    theme = st.selectbox("Select Theme:", theme_options, index=idx, key="sidebar_theme_select")
    
    if theme != st.session_state.theme:
        st.session_state.theme = theme
        # Update profile theme in the background
        update_profile(uid, {"theme": theme})
        apply_theme(theme)
        st.info(f"Theme changed to **{theme}**. Reloading...")
        st.rerun()
        
    st.markdown("---")
    
    st.subheader("💡 Hydration Tip")
    st.info(st.session_state.tip)
    
    if st.button("Generate New Tip", key="new_tip", use_container_width=True):
        st.session_state.tip = random.choice(HYDRATION_TIPS)
        st.rerun()

def render_dashboard_main(uid, intake, goal, percent):
    st.header("🏠 Today's Hydration Summary")
    st.markdown(f"Goal: **{goal} ml** | Today's Date: **{TODAY}**")
    
    remaining = goal - intake
    metric_label = f"{remaining} ml remaining" if remaining > 0 else "Goal Achieved!"
    
    st.metric("Total Water Intake", f"{intake} ml", metric_label)
    st.progress(percent / 100, text=f"Progress: {percent:.1f}%")
    
    col_viz, col_status = st.columns([1, 1])
    
    with col_viz:
        st.subheader("Water Level")
        st.components.v1.html(render_bottle(percent), height=350, width=200)
        
    with col_status:
        st.subheader("Status")
        if percent >= 100:
            st.success("🏆 Goal achieved! You are fully hydrated for the day. Reward yourself with a game run!")
            congratulations_banner()
        elif percent >= 75:
            st.info("Almost there! Just a few more sips to reach your daily target.")
        elif percent >= 50:
            st.info("Halfway there! Keep sipping regularly to maintain momentum.")
        else:
            st.info("Nice start! Remember to drink consistent amounts throughout the day.")

def view_dashboard():
    uid = st.session_state.uid
    if not uid:
        st.error("Session expired or authentication failed. Please log in again.")
        st.session_state.logged_in = False
        st.session_state.view = "login"
        st.rerun()
        return

    profile = get_profile(uid)
    intake = get_intake(uid)
    goal = profile["user_goal_ml"]
    percent = min(intake / goal * 100, 100)
    
    # Ensure the correct theme is loaded from profile
    if st.session_state.theme != profile.get("theme", "Light"):
        st.session_state.theme = profile.get("theme", "Light")
        apply_theme(st.session_state.theme)

    left, right = st.columns([1, 3])
    
    with left:
        render_sidebar_navigation(uid)
        
    with right:
        nav = st.session_state.nav
        
        if nav == "Home":
            render_dashboard_main(uid, intake, goal, percent)
        elif nav == "Log Water":
            view_log(uid, intake, goal)
        elif nav == "Progress Log":
            view_progress_log(uid, goal, intake)
        elif nav == "History":
            view_history(uid, goal)
        elif nav == "Settings":
            view_settings(uid, profile)
        elif nav == "Runner Game":
            view_runner_game()
        else:
            st.error("Invalid navigation state.")

# --- Main Application Runner ---

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
