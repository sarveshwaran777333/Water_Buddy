import streamlit as st
import streamlit.components.v1 as components
import requests
import json
import base64
import random
import matplotlib.pyplot as plt
from datetime import date, timedelta
import time

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
        
        /* Ensure the SVG bottle text is visible against light themes */
        .stHtmlContainer svg text {{
             fill: var(--text-color) !important;
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
              font-size="20" fill="var(--text-color)">{percent:.0f}%</text>
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

    # Use theme colors for Matplotlib
    fg_color = st.session_state.theme_fg
    bg_color = st.session_state.theme_bg

    plt.style.use('default') # Reset style
    
    # Create figure with transparent background and theme colors
    fig, ax = plt.subplots(figsize=(9, 5))
    fig.patch.set_facecolor('none')
    ax.set_facecolor('none')
    
    # Set text and line colors
    ax.plot(labels, values, marker="o", color="#3498db")
    ax.axhline(goal, color="#2ecc71", linestyle="--", label="Goal")
    
    ax.set_ylim(bottom=0)
    ax.set_title("Water Intake (Last 7 Days)", color=fg_color)
    ax.set_ylabel("ml", color=fg_color)
    
    # Set axis tick colors
    ax.tick_params(axis='x', rotation=45, colors=fg_color)
    ax.tick_params(axis='y', colors=fg_color)
    
    # Set spine colors
    for spine in ax.spines.values():
        spine.set_color(fg_color)

    ax.grid(True, axis='y', alpha=0.4, color=fg_color)
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
# UI: 2D Runner (with Theme Fixes)
# --------------------------------------------------
def view_runner_game():
    st.header("WaterBuddy Runner Game 🤖💧")
    st.write("Press **SPACE** to start/jump. Collect droplets (coins). Press **R** to restart in-game.")
    st.markdown("---")
    
    # 1. Determine Canvas Background Color based on the active theme
    current_theme = st.session_state.get("theme", "Light")
    
    if current_theme == "Aqua":
        # Light blue gradient for Aqua theme
        canvas_bg_gradient = "linear-gradient(#d0f7ff, #b5efff)"
    elif current_theme == "Dark":
        # Dark gradient for Dark theme
        canvas_bg_gradient = "linear-gradient(#3c4854, #2a3440)"
    else: # Light and default
        # Original light pink/orange gradient
        canvas_bg_gradient = "linear-gradient(#ffefd5, #ffd5c8)"
    
    # Image Loading
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
        st.error("Error: **ROBO.png** file not found. Game cannot load.")
        return

    js_game_code = f"""
    (function() {{
      if (window.__waterbuddyGameStarted) return;
      window.__waterbuddyGameStarted = true;

      const canvas = document.getElementById("gameCanvas");
      const ctx = canvas.getContext("2d");

      const groundY = 350;

      // FIX APPLIED: Read the Streamlit theme text color for the HUD.
      const STREAMLIT_TEXT_COLOR = getComputedStyle(document.body).getPropertyValue('--text-color').trim() || '#000000'; 

      // Persistent lifetime coins across runs (per page session)
      window.__waterbuddyTotalCoins = window.__waterbuddyTotalCoins || 0;

      // Game state
      let gameState = "menu"; // "menu", "playing", "gameover"
      let gameOver = false;

      // Player and gameplay vars
      let playerImg = new Image();
      playerImg.src = "{robo_url}";

      let player = {{ x: 150, y: groundY, width: 120, height: 140, velocityY: 0, gravity: 0.4, jumpPower: -12, onGround: true }};
      let obstacles = [];
      let droplets = [];
      let speed = 6;
      let score = 0;            // run score (distance + coins)
      let coinsCollected = 0;   // run coins
      let frame = 0;

      // Input
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

      // Spawns
      function spawnObstacle() {{
        // Bottom aligns with player feet (430 + 60 = 490; ground feet 350 + 140 = 490)
        obstacles.push({{ type: "block", x: canvas.width + 50, y: 430, width: 60, height: 60 }});
      }}

      function spawnDroplet() {{
        const y = Math.random() * 200 + 150;
        droplets.push({{ x: canvas.width + 50, y, width: 30, height: 40 }});
      }}

      // Draw
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

      // HUD
      function drawHUD() {{
        // Use the theme color for the score text
        ctx.fillStyle = STREAMLIT_TEXT_COLOR; 
        ctx.font = "28px Arial";
        ctx.fillText("Score: " + score, 30, 40);
        ctx.fillText("Coins: " + coinsCollected, 30, 80);
      }}

      // Menu
      function drawMenu() {{
        ctx.clearRect(0, 0, canvas.width, canvas.height);
        // Background - set to a neutral color that contrasts the menu text
        ctx.fillStyle = "#222"; 
        ctx.fillRect(0, 0, canvas.width, canvas.height);

        ctx.fillStyle = "#fff";
        ctx.font = "48px Arial";
        ctx.fillText("WaterBuddy Runner", canvas.width/2 - 250, canvas.height/2 - 120);

        ctx.font = "24px Arial";
        ctx.fillText("Press SPACE to Start", canvas.width/2 - 120, canvas.height/2 - 40);
        ctx.fillText("Jump with SPACE. Press R to restart.", canvas.width/2 - 170, canvas.height/2);

        // Lifetime coins
        ctx.font = "28px Arial";
        ctx.fillText("Total Coins: " + window.__waterbuddyTotalCoins, canvas.width/2 - 120, canvas.height/2 + 60);
      }}

      // Utils
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

      // Game Loop
      function gameLoop() {{
        if (gameState !== "playing") return;

        ctx.clearRect(0, 0, canvas.width, canvas.height);

        // Physics
        player.velocityY += player.gravity;
        player.y += player.velocityY;
        player.onGround = false;

        // Ground clamp
        if (player.y >= groundY) {{
          player.y = groundY;
          player.velocityY = 0;
          player.onGround = true;
        }}

        // Spawns
        if (frame % 70 === 0) spawnObstacle();
        if (frame % 55 === 0) spawnDroplet();

        // Obstacles
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

            // 1. Safe landing on top
            if (falling && playerFeetY > obsTopY) {{ 
              player.y = obsTopY - player.height;
              player.velocityY = 0;
              player.onGround = true;
              continue;
            }}

            // 2. Head bump
            if (player.velocityY < 0 && player.y <= obs.y + obs.height) {{
              player.velocityY = 0;
              continue;
            }}

            // 3. Side/Bottom Collision -> game over
            endGame();
            break;
          }}

          if (obs.x < -120) obstacles.splice(i, 1);
        }}

        // Droplets (coins)
        for (let i = droplets.length - 1; i >= 0; i--) {{
          const drop = droplets[i];
          drop.x -= speed;
          drawDroplet(drop);

          const pcb = playerCollisionBox();
          // Slightly shrunken droplet hitbox for fair collection
          const m = 5;
          if (aabb(pcb.x, pcb.y, pcb.w, pcb.h, drop.x + m, drop.y + m, drop.width - 2*m, drop.height - 2*m)) {{
            coinsCollected += 1;                 
            window.__waterbuddyTotalCoins += 1;  
            score += 100;                        
            droplets.splice(i, 1);
          }} else if (drop.x < -60) {{
            droplets.splice(i, 1);
          }}
        }}

        // Base score like Subway Surfers (distance-based)
        score += Math.floor(speed);

        // Draw player and HUD
        drawPlayer();
        drawHUD();

        // Difficulty scaling
        speed += 0.002;
        frame++;

        requestAnimationFrame(gameLoop);
      }}

      // State transitions
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

        // Overlay
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

      // Start: show menu, then focus
      playerImg.onload = function() {{
        drawMenu();
        setTimeout(() => {{
          canvas.focus();
        }}, 0);
      }};
    }})();
    """

    # 2. Use the conditional canvas_bg_gradient in the HTML
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

    # Pass theme colors to session state for graphing
    if st.session_state.theme == "Dark":
        st.session_state.theme_fg = "#e6eef6"
        st.session_state.theme_bg = "#0f1720"
    elif st.session_state.theme == "Aqua":
        st.session_state.theme_fg = "#004455"
        st.session_state.theme_bg = "#e8fbff"
    else:
        st.session_state.theme_fg = "#000000"
        st.session_state.theme_bg = "#ffffff"


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
            st.rerun() # Rerun to apply new theme immediately

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
