import streamlit as st
import streamlit.components.v1 as components
import requests
import json
import base64
import random
import matplotlib.pyplot as plt
from datetime import date, timedelta
import time # Added for sleep

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
CUPS_TO_ML = 236.588 # Added for unit conversion context

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
        "password": password, # NOTE: In a real app, hash this password!
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
    return {"age_group": age_group, "user_goal_ml": int(goal), "theme": profile.get("theme", "Light")}

def update_profile(uid: str, updates: dict):
    return fb_patch(f"{USERS_NODE}/{uid}/profile", updates)

def get_history(uid: str, days=7):
    """Get last N days of intake, sorted by date (oldest first)."""
    out = {}
    today = date.today()
    temp_history = {}
    for i in range(days):
        d = (today - timedelta(days=i)).isoformat()
        raw = fb_get(f"{USERS_NODE}/{uid}/days/{d}/intake")
        temp_history[d] = int(raw or 0)
    
    # Sort to get chronological order for plotting
    for d in sorted(temp_history.keys()):
        out[d] = temp_history[d]
        
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
        metric_bg = "#f7f7f7"
        metric_fg = "#000000"
    elif theme == "Aqua":
        bg, fg = "#e8fbff", "#004455"
        metric_bg = "#d9f7ff"
        metric_fg = "#005577"
    else:  # Dark Theme
        bg, fg = "#0f1720", "#e6eef6"
        metric_bg = "#1a2634"
        metric_fg = "#e6eef6"

    st.markdown(
        f"""
        <style>
        .stApp {{
            background-color: {bg} !important;
            color: {fg} !important;
        }}
        h1, h2, h3, h4, p, span, label {{ color: {fg} !important; }}
        
        div[data-testid="metric-container"] {{
            background-color: {metric_bg} !important;
            border-radius: 12px;
            padding: 12px;
        }}
        div[data-testid="metric-container"] * {{ color: {metric_fg} !important; }}
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
# Banner
# --------------------------------------------------
def congratulations_banner():
    """Renders an animating congratulatory banner at the bottom of the screen."""
    
    # CSS for the sliding banner animation
    banner_css = """
    <style>
    @keyframes slideInUp {
      0% {
        transform: translateY(100%);
        opacity: 0;
      }
      100% {
        transform: translateY(0);
        opacity: 1;
      }
    }

    .congrats-banner {
      position: fixed;
      bottom: 0;
      left: 0;
      width: 100%;
      background-color: #2ecc71; /* Success color */
      color: white;
      text-align: center;
      padding: 15px;
      z-index: 1000; /* Ensure it's on top */
      box-shadow: 0 -4px 12px rgba(0, 0, 0, 0.2);
      animation: slideInUp 0.8s ease-out forwards;
      font-size: 24px;
      font-weight: bold;
      border-top-left-radius: 10px;
      border-top-right-radius: 10px;
    }
    </style>
    """
    st.markdown(banner_css, unsafe_allow_html=True)

    # HTML for the banner content
    banner_html = """
    <div class="congrats-banner">
        🎉 CONGRATULATIONS! You hit your daily water goal! 🎉
    </div>
    """
    
    with st.container():
        st.markdown(banner_html, unsafe_allow_html=True)


# --------------------------------------------------
# Graphing
# --------------------------------------------------
def render_history_graph(history, goal):
    # Sort keys for chronological order
    days = sorted(history.keys())
    values = [history[d] for d in days]
    labels = [date.fromisoformat(d).strftime("%a %m/%d") for d in days]

    fig, ax = plt.subplots(figsize=(9, 5))
    ax.plot(labels, values, marker="o", color="#3498db")
    ax.axhline(goal, color="#2ecc71", linestyle="--", label="Goal")
    ax.set_ylim(bottom=0)
    ax.set_title("Water Intake (Last 7 Days)")
    ax.set_ylabel("ml")
    ax.tick_params(axis='x', rotation=45)
    ax.grid(True, axis='y', alpha=0.4)
    fig.tight_layout()
    return fig

# --------------------------------------------------
# UI: Login
# --------------------------------------------------
def view_login():
    st.header("Login")

    username = st.text_input("Username", key="login_username_input")
    password = st.text_input("Password", type="password", key="login_password_input")

    if st.button("Sign In", key="login_btn"):
        if not username or not password:
            st.error("Please enter both username and password.")
            return

        ok, uid = login_user(username.strip(), password)
        if ok:
            st.session_state.logged_in = True
            st.session_state.uid = uid
            
            # Load user-specific theme
            profile = get_profile(uid)
            st.session_state.theme = profile.get("theme", "Light")
            
            st.session_state.view = "dashboard"
            st.success("Welcome back! Rerunning...")
            time.sleep(0.1) # Give time for message to display
            st.rerun()
        else:
            st.error("Invalid username or password.")

    if st.button("Create new account", key="go_signup"):
        st.session_state.view = "signup"
        st.rerun()

# --------------------------------------------------
# UI: Signup
# --------------------------------------------------
def view_signup():
    st.header("Create Account")
    st.warning("Note: Passwords are not hashed in this demo, please use a secure password manager for real applications.")

    username = st.text_input("Choose username", key="signup_username_input")
    password = st.text_input("Choose password", type="password", key="signup_password_input")

    if st.button("Register", key="signup_btn"):
        if not username or not password:
            st.error("Please enter both username and password.")
            return

        uid = create_user(username.strip(), password)
        if uid:
            st.success("Account created. You may now log in.")
            st.session_state.view = "login"
            st.rerun()
        else:
            st.error("Username already exists or network error.")

    if st.button("Back to login", key="go_login"):
        st.session_state.view = "login"
        st.rerun()

# --------------------------------------------------
# UI: Logging Water
# --------------------------------------------------
def view_log(uid, intake, goal):
    st.header("Log Water Intake")
    st.write(f"**Today's intake:** {intake} ml")
    st.write(f"**Goal:** {goal} ml")
    
    col1, col2 = st.columns(2)

    with col1:
        # Quick Add Button
        if st.button(f"+ {DEFAULT_QUICK_ADD} ml", use_container_width=True):
            if update_intake(uid, intake + DEFAULT_QUICK_ADD):
                st.success(f"Added {DEFAULT_QUICK_ADD} ml.")
                st.rerun()
            else:
                st.error("Failed to update.")

    with col2:
        # Reset Button
        if st.button("Reset Today", use_container_width=True):
            if reset_intake(uid):
                st.info("Intake reset!")
                st.rerun()
            else:
                st.error("Failed to reset.")
    
    st.markdown("---")

    # Custom Add Form
    with st.form("custom_log_form"):
        custom = st.number_input("Custom amount (ml)", min_value=0, step=50)
        submitted = st.form_submit_button("Add Custom Amount")
        
        if submitted and custom > 0:
            if update_intake(uid, intake + custom):
                st.success(f"Added {custom} ml.")
                st.rerun()
            else:
                st.error("Failed to update.")

    st.markdown("---")
    st.subheader("Unit Converter")
    cc1, cc2 = st.columns(2)
    
    with cc1:
        cups = st.number_input("Cups to Milliliters", min_value=0.0, step=0.5)
        st.write(f"Equals: **{round(cups * CUPS_TO_ML, 1)} ml**")
    
    with cc2:
        ml_in = st.number_input("Milliliters to Cups", min_value=0.0, step=50.0)
        st.write(f"Equals: **{round(ml_in / CUPS_TO_ML, 2)} cups**")

# --------------------------------------------------
# UI: History
# --------------------------------------------------
def view_history(uid, goal):
    st.header("History")
    history = get_history(uid, 7)
    
    st.subheader("Intake Trend")
    try:
        fig = render_history_graph(history, goal)
        st.pyplot(fig)
    except Exception as e:
        st.error("Could not render chart.")
        print(f"Graphing Error: {e}")

    st.subheader("Raw History Data")
    # Convert history dict for table display (most recent first)
    table_data = {
        "Date": [date.fromisoformat(d).strftime("%b %d, %Y") for d in reversed(sorted(history.keys()))],
        "Intake": [f"{history[d]} ml" for d in reversed(sorted(history.keys()))]
    }
    st.table(table_data)

# --------------------------------------------------
# UI: Settings
# --------------------------------------------------
def view_settings(uid, profile):
    st.header("Settings")
    
    current_theme = profile.get("theme", "Light")

    age_group_list = list(AGE_GROUP_DEFAULTS.keys())
    selected_age = st.selectbox("Age Group", age_group_list, index=age_group_list.index(profile["age_group"]))
    st.write(f"Suggested goal for this group: **{AGE_GROUP_DEFAULTS[selected_age]} ml**")

    custom_goal = st.number_input("Daily Goal (ml)", min_value=500, max_value=10000, value=profile["user_goal_ml"], step=100)
    
    theme_options = ["Light", "Aqua", "Dark"]
    selected_theme = st.selectbox("App Theme", theme_options, index=theme_options.index(current_theme))


    if st.button("Save Settings"):
        updates = {
            "age_group": selected_age, 
            "user_goal_ml": int(custom_goal),
            "theme": selected_theme
        }
        if update_profile(uid, updates):
            st.success("Settings saved! Reloading for theme change...")
            st.session_state.theme = selected_theme
            st.rerun()
        else:
            st.error("Failed to save settings.")

# --------------------------------------------------
# UI: 2D Runner
# --------------------------------------------------
def view_runner_game():
    st.header("WaterBuddy Runner Game 🤖💧")
    st.write("Press **SPACE** to jump and collect water droplets (blue circles). You can now **land on top** of the obstacles!")
    st.markdown("---")
    
    # --- Image Loading (Base64 is essential for Streamlit components) ---
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
        st.error("Error: **ROBO.png** file not found. Game cannot load. Please ensure the file exists.")
        return

    # --- FULL JAVASCRIPT GAME CODE ---
    js_game_code = f"""
    const canvas = document.getElementById("gameCanvas");
    const ctx = canvas.getContext("2d");

    let playerImg = new Image();
    playerImg.src = "{robo_url}";

    // Physics settings for smoother jump arc
    let player = {{ x: 150, y: 350, width: 120, height: 140, velocityY: 0, gravity: 0.7, jumpPower: -15, onGround: true }};
    
    let obstacles = [];
    let droplets = [];
    let speed = 6;
    let score = 0;
    let frame = 0;

    // --- INPUT HANDLER (Spacebar Fix) ---
    document.addEventListener("keydown", function(e) {{
        if (e.code === "Space") {{
            e.preventDefault(); 
            if (player.onGround) {{
                player.velocityY = player.jumpPower;
                player.onGround = false;
            }}
        }}
    }});

    function spawnObstacle() {{
        obstacles.push({{ type: "block", x: canvas.width + 50, y: 380, width: 60, height: 60 }});
    }}

    function spawnDroplet() {{
        droplets.push({{ x: canvas.width + 50, y: Math.random() * 200 + 150, width: 30, height: 40 }});
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

    function gameLoop() {{
        ctx.clearRect(0, 0, canvas.width, canvas.height);

        // Player physics
        player.velocityY += player.gravity; 
        player.y += player.velocityY;
        // Check for landing on the ground (base floor)
        if (player.y >= 350) {{ player.y = 350; player.velocityY = 0; player.onGround = true; }}

        drawPlayer();

        if (frame % 70 === 0) spawnObstacle();
        if (frame % 50 === 0) spawnDroplet();

        // Obstacle processing with PRECISION HITBOX and PLATFORM LOGIC
        for (let i = obstacles.length - 1; i >= 0; i--) {{
            let obs = obstacles[i];
            obs.x -= speed;
            drawObstacle(obs);
            
            // --- Define Virtual Hitbox ---
            let hitbox_width = 90;
            let hitbox_height = 40;
            let hitbox_x = player.x + (player.width - hitbox_width); 
            let hitbox_y = player.y + (player.height - hitbox_height); 
            
            // --- Full AABB Collision Check ---
            let is_overlapping = (
                hitbox_x < obs.x + obs.width && 
                hitbox_x + hitbox_width > obs.x && 
                hitbox_y < obs.y + obs.height && 
                hitbox_y + hitbox_height > obs.y 
            );

            if (is_overlapping) {{
                // 1. Check for TOP-SIDE COLLISION (Landing/Climbing)
                // If the player is falling (velocityY > 0) AND the player's previous bottom was above the obstacle's top (obs.y)
                let prev_bottom_y = player.y + player.height - hitbox_height - player.velocityY; 
                
                if (player.velocityY > 0 && prev_bottom_y <= obs.y) {{
                    // Set player precisely on the platform
                    player.y = obs.y - hitbox_height; 
                    player.velocityY = 0;
                    player.onGround = true;
                    continue; // Skip the death check below
                }}
                
                // 2. Check for DEATH (Side/Bottom-Up/Head Collision)
                // If it's still overlapping, and it wasn't a landing, it's a death.
                alert("Game Over! Final Score: " + score);
                document.location.reload(); 
            }}
            
            // Fall-Off Logic: If the robot is standing on the obstacle and the obstacle passes it, set onGround to false.
            if (player.onGround && player.y + player.height - hitbox_height === obs.y && obs.x + obs.width < hitbox_x) {{
                player.onGround = false;
            }}
            
            if (obs.x < -100) obstacles.splice(i, 1);
        }}

        // Droplet processing (uses the full bounding box for easier collection)
        for (let i = droplets.length - 1; i >= 0; i--) {{
            let drop = droplets[i];
            drop.x -= speed;
            drawDroplet(drop);
            if (player.x < drop.x + drop.width && 
                player.x + player.width > drop.x &&
                player.y < drop.y + drop.height && 
                player.y + player.height > drop.y) {{
                score += 10;
                droplets.splice(i, 1);
            }}
            if (drop.x < -50) droplets.splice(i, 1);
        }}

        ctx.fillStyle = "#000";
        ctx.font = "28px Arial";
        ctx.fillText("Score: " + score, 30, 40);

        speed += 0.002;
        frame++;

        requestAnimationFrame(gameLoop);
    }}

    playerImg.onload = gameLoop;
    
    document.getElementById('gameCanvas').focus();
    """

    # --- HTML and Components ---
    html_content = f"""
    <style>
    canvas {{
        background: linear-gradient(#ffefd5, #ffd5c8);
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
# --------------------------------------------------
# Dashboard / Main App View
# --------------------------------------------------
def view_dashboard():
    uid = st.session_state.uid
    if not uid:
        st.error("Authentication error. Please log in again.")
        st.session_state.logged_in = False
        st.session_state.view = "login"
        st.rerun()
        return

    profile = get_profile(uid)
    intake = get_intake(uid)
    goal = profile["user_goal_ml"]
    percent = min(intake / goal * 100, 100)

    left, right = st.columns([1, 2])

    ## Navigation Panel
    with left:
        st.subheader("Navigation")
        for option in ["Home", "Log Water", "History", "Settings", "Runner Game", "Logout"]:
            if st.button(option, key=f"nav_{option}"):
                if option == "Logout":
                    st.session_state.logged_in = False
                    st.session_state.uid = None
                    st.session_state.view = "login"
                else:
                    st.session_state.nav = option
                st.rerun()

        st.markdown("---")
        
        # Theme selector (uses session state but the main logic is in settings)
        theme_options = ["Light", "Aqua", "Dark"]
        try:
             idx = theme_options.index(st.session_state.theme)
        except ValueError:
            idx = 0
            
        theme = st.selectbox("Theme Quick View", theme_options, index=idx)
        if theme != st.session_state.theme:
            st.session_state.theme = theme
            apply_theme(theme)
            # NOTE: Theme is properly persisted in view_settings upon saving.

        st.markdown("---")
        st.subheader("Tip of the Day")
        st.info(st.session_state.tip)
        if st.button("New Tip", key="new_tip"):
            st.session_state.tip = random.choice(HYDRATION_TIPS)
            st.rerun()

    ## Main Panel
    with right:
        nav = st.session_state.nav

        if nav == "Home":
            st.header("Today's Summary")
            st.write(f"Goal: **{goal} ml** | Date: **{TODAY}**")
            
            st.metric("Total Intake", f"{intake} ml", f"{goal - intake} ml remaining" if goal > intake else "Goal Achieved!")
            st.progress(percent / 100)

            col_viz, col_status = st.columns([1, 1])
            with col_viz:
                st.components.v1.html(render_bottle(percent), height=350, width=200)

            with col_status:
                if st_lottie is not None:
                    # NOTE: Lottie must be loaded here if used
                    pass
                    
                if percent >= 100:
                    st.success("🏆 Goal achieved! You are fully hydrated for the day.")
                    congratulations_banner() # Call the banner
                elif percent >= 75:
                    st.info("Almost there! Only a little bit more to go.")
                elif percent >= 50:
                    st.info("Halfway there! Keep sipping.")
                else:
                    st.info("Nice start! Make sure to space out your remaining intake.")

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
