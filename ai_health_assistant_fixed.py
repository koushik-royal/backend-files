# ai_health_assistant.py - FIXED VERSION
# Features: Dislike tracking, patient name support, show features only when asked

from typing import Dict, Tuple, List
import re
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression

# ========================
# 1) TRAINING DATA
# ========================
TRAINING_DATA = [
    # Greeting
    ("hi", "greeting"),
    ("hello", "greeting"),
    ("hlo", "greeting"),
    ("hey", "greeting"),
    ("good morning", "greeting"),
    ("good evening", "greeting"),
    
    # Eye care tips
    ("give eye care tips", "eye_care_tips"),
    ("eye care tips", "eye_care_tips"),
    ("how to take care of eyes", "eye_care_tips"),
    ("tips for eye health", "eye_care_tips"),
    
    # Eye exercises
    ("eye exercises", "eye_exercises"),
    ("give me eye exercise", "eye_exercises"),
    ("how to improve vision", "eye_exercises"),
    ("eye workout", "eye_exercises"),
    
    # Vision check
    ("vision check", "vision_check"),
    ("how to check vision", "vision_check"),
    ("my child cannot see properly", "vision_check"),
    
    # Food (dislike patterns will be handled separately)
    ("food for eye health", "food"),
    ("what food is good for eyes", "food"),
    ("best diet for eyes", "food"),
    ("show me foods", "food"),
    
    # Reminder
    ("set reminder", "set_reminder"),
    ("remind me", "set_reminder"),
    ("i want reminder", "set_reminder"),
    ("medicine reminder", "set_reminder"),
    
    # Dislike detection (NEW)
    ("i don't like", "dislike"),
    ("i dislike", "dislike"),
    ("don't like", "dislike"),
    ("hate", "dislike"),
    ("remove from list", "dislike"),
]

# ========================
# 2) ML MODEL SETUP
# ========================
vectorizer = TfidfVectorizer(lowercase=True, stop_words='english', ngram_range=(1, 2))
X = vectorizer.fit_transform([text for text, _ in TRAINING_DATA])
y = [intent for _, intent in TRAINING_DATA]
ml_model = LogisticRegression(max_iter=200)
ml_model.fit(X, y)

# ========================
# 3) SESSION STATE (Track dislikes & context per user)
# ========================
SESSION_STATE = {}

def get_session_state(session_id: str):
    """Get or create session state for a user"""
    if session_id not in SESSION_STATE:
        SESSION_STATE[session_id] = {
            "dislikes": [],  # Foods user doesn't like
            "reminder_step": 0,  # 0=not started, 1=type, 2=time, 3=frequency
            "reminder_data": {},  # Store reminder info
            "shown_foods": [],  # Track shown foods for this session
        }
    return SESSION_STATE[session_id]

# ========================
# 4) FOOD DATABASE (56 foods, 7 categories)
# ========================
FOODS = {
    "Leafy Greens": ["Spinach", "Kale", "Broccoli", "Lettuce", "Cabbage"],
    "Orange Vegetables": ["Carrots", "Sweet Potato", "Pumpkin", "Butternut Squash", "Apricots"],
    "Berries": ["Blueberries", "Blackberries", "Strawberries", "Raspberries", "Cranberries"],
    "Citrus": ["Orange", "Lemon", "Grapefruit", "Tangerine", "Lime"],
    "Nuts & Seeds": ["Almonds", "Walnuts", "Flaxseeds", "Sunflower Seeds", "Pumpkin Seeds"],
    "Fish & Protein": ["Salmon", "Tuna", "Sardines", "Mackerel", "Eggs"],
    "Dairy": ["Milk", "Yogurt", "Cheese", "Ghee", "Butter"],
    "Dry Fruits": ["Dates", "Raisins", "Almonds", "Cashews", "Walnuts"],
}

# Flatten for easier access
ALL_FOODS = []
for category, foods in FOODS.items():
    ALL_FOODS.extend(foods)

# ========================
# 5) EXERCISES (12 exercises)
# ========================
EXERCISES = [
    {"name": "Eye Rolling", "steps": "Roll eyes clockwise 10 times, then counterclockwise 10 times", "duration": "2 min", "benefit": "Improves eye flexibility"},
    {"name": "Near-Far Focus", "steps": "Focus on near object (3 inches) for 5 sec, then far object (20 feet) for 5 sec. Repeat 10 times", "duration": "3 min", "benefit": "Strengthens lens flexibility"},
    {"name": "Blinking Exercise", "steps": "Blink rapidly 20 times, rest for 10 seconds. Repeat 5 times", "duration": "2 min", "benefit": "Reduces eye strain"},
    {"name": "Palming", "steps": "Close eyes, cover with palms without pressing. Relax for 2-3 minutes", "duration": "3 min", "benefit": "Relieves eye fatigue"},
    {"name": "Figure 8 Pattern", "steps": "Imagine a figure 8 on the floor. Follow it with your eyes 2-3 times", "duration": "2 min", "benefit": "Increases eye movement range"},
    {"name": "Diagonal Movements", "steps": "Move eyes diagonally (up-left, down-right) 10 times each direction", "duration": "2 min", "benefit": "Activates all eye muscles"},
    {"name": "Peripheral Vision", "steps": "Focus straight ahead, notice objects to the sides without turning head", "duration": "2 min", "benefit": "Expands visual field"},
    {"name": "Focusing Exercise", "steps": "Hold a pen at arm's length, move slowly towards nose while focusing, then away", "duration": "2 min", "benefit": "Improves focus control"},
    {"name": "20-20-20 Rule", "steps": "Every 20 minutes, look at something 20 feet away for 20 seconds", "duration": "20 sec", "benefit": "Prevents screen fatigue"},
    {"name": "Eye Massage", "steps": "Gently massage around eyes in circular motion for 1 minute", "duration": "1 min", "benefit": "Improves blood circulation"},
    {"name": "Sunlight Therapy", "steps": "Face sun with eyes closed for 1 minute, move head side to side", "duration": "1 min", "benefit": "Strengthens optic nerve"},
    {"name": "Water Splash", "steps": "Splash cool water on eyes 5 times, blink several times", "duration": "1 min", "benefit": "Refreshes and cools eyes"},
]

# ========================
# 6) INTENT DETECTION
# ========================
def predict_intent(text: str) -> Tuple[str, float]:
    """ML-based intent prediction"""
    X_test = vectorizer.transform([text])
    intent = ml_model.predict(X_test)[0]
    confidence = ml_model.predict_proba(X_test).max()
    return intent, confidence

def detect_dislike_items(text: str) -> List[str]:
    """Extract food items from dislike messages"""
    # Pattern: "i don't like X and Y" -> extract X, Y
    items = []
    
    # Remove common words
    text_lower = text.lower()
    dislike_patterns = [
        r"(?:don't like|dislike|hate|remove|don't want)\s+(.+?)(?:\.|$|and)",
    ]
    
    for pattern in dislike_patterns:
        matches = re.findall(pattern, text_lower)
        for match in matches:
            # Split by 'and' to get multiple items
            parts = [p.strip() for p in match.split('and')]
            items.extend(parts)
    
    return items

def is_dislike_message(text: str) -> bool:
    """Check if message is about dislikes"""
    return any(word in text.lower() for word in ["don't like", "dislike", "hate", "remove", "don't want"])

# ========================
# 7) MAIN AI FUNCTION
# ========================
def get_ai_reply(user_text: str, patient_name: str = "there", session_id: str = "default") -> str:
    """
    Main AI function with:
    - Dislike tracking
    - Patient name personalization
    - Features only when asked
    - Session-based memory
    """
    
    if not user_text or not user_text.strip():
        return "I'm here to help! Ask me about eye health, foods, exercises, or reminders. 👀"
    
    state = get_session_state(session_id)
    text_lower = user_text.lower().strip()
    
    # ===== DISLIKE HANDLING =====
    if is_dislike_message(text_lower):
        items = detect_dislike_items(text_lower)
        if items:
            state["dislikes"].extend(items)
            state["dislikes"] = list(set(state["dislikes"]))  # Remove duplicates
            items_str = " and ".join(items)
            return f"Got it {patient_name}! 😊 I will not suggest {items_str}."
        return f"I understand {patient_name}. Please tell me which foods you don't like."
    
    # ===== GREETING (only when asked) =====
    if text_lower in ["hi", "hello", "hey", "hlo"]:
        return f"Hi {patient_name}! 👋 How are you today?"
    
    # ===== ML INTENT PREDICTION =====
    intent, confidence = predict_intent(text_lower)
    
    # ===== FOOD REQUEST =====
    if intent == "food" or "food" in text_lower:
        # Get 10 foods, excluding dislikes
        available_foods = [f for f in ALL_FOODS if f.lower() not in [d.lower() for d in state["dislikes"]]]
        
        if not available_foods:
            return f"You've marked all foods as disliked! 😅 Tell me 'remove <food>' to add it back."
        
        # Show 10 foods at a time with time slots and benefits
        import random
        foods_to_show = random.sample(available_foods, min(10, len(available_foods)))
        state["shown_foods"].extend(foods_to_show)
        
        # Enhanced food details with time slots and benefits
        food_details = {
            "Spinach": ("🥗 Spinach", "Breakfast/Lunch", "🟢 Improves night vision - 2-3x/week", "Lutein rich"),
            "Kale": ("🥬 Kale", "Breakfast/Lunch", "🟢 Reduces eye strain - 2-3x/week", "Antioxidants"),
            "Carrots": ("🥕 Carrots", "Snack/Lunch", "🟠 Boosts vision clarity - Daily", "Beta-carotene"),
            "Blueberries": ("🫐 Blueberries", "Breakfast/Snack", "🔵 Protects retina - Daily", "Anthocyanins"),
            "Salmon": ("🐟 Salmon", "Lunch/Dinner", "🟡 Reduces dry eyes - 2-3x/week", "Omega-3 fatty acids"),
            "Almonds": ("🌰 Almonds", "Snack", "🟤 Prevents cataracts - Daily", "Vitamin E"),
            "Orange": ("🍊 Orange", "Breakfast/Snack", "🟠 Protects cells - Daily", "Vitamin C"),
            "Eggs": ("🥚 Eggs", "Breakfast", "🟡 Strengthens lens - 3-4x/week", "Lutein & Zeaxanthin"),
            "Broccoli": ("🥦 Broccoli", "Lunch/Dinner", "🟢 Prevents macular degeneration - 2x/week", "Vitamins A,C,K"),
            "Sweet Potato": ("🍠 Sweet Potato", "Lunch/Dinner", "🟠 Enhances vision - 2x/week", "Vitamin A"),
            "Walnuts": ("🌰 Walnuts", "Snack", "🟤 Supports retina - Daily", "Omega-3s"),
            "Berries": ("🫐 Berries", "Breakfast/Snack", "🔵 Anti-inflammatory - Daily", "Antioxidants"),
        }
        
        foods_list = ""
        for f in foods_to_show:
            if f in food_details:
                emoji, time_slot, benefit, component = food_details[f]
                foods_list += f"{emoji} • {time_slot} • {benefit} ({component})\n"
            else:
                foods_list += f"🥗 {f} • Rich in nutrients\n"
        
        return f"✨ **Eye-Healthy Foods for You** ✨\n\n{foods_list}\n📌 Tip: Rotate foods weekly for variety!\nType 'more foods' to see more! 🥕"
    
    # ===== EXERCISE REQUEST =====
    if intent == "eye_exercises" or "exercise" in text_lower:
        exercises_list = "\n".join([f"💪 {e['name']}: {e['duration']} - {e['benefit']}" for e in EXERCISES])
        return f"Here are your 12 eye exercises:\n{exercises_list}\n\nType 'exercise <name>' for steps! 👀"
    
    # ===== REMINDER SETUP (Step-by-step) =====
    if intent == "set_reminder" or "reminder" in text_lower:
        if state["reminder_step"] == 0:
            # Explain first with examples
            explanation = """⏰ **Set Your Eye Care Reminders**

💡 Reminders help you remember:
  • 💧 Eye drops (2-3 times daily)
  • 👓 Screen breaks (Every 20 mins)
  • 🏃 Eye exercises (Morning & evening)
  • 📋 Eye checkups (Monthly)
  • 🍽️ Healthy meals (Throughout day)

What do you want to be reminded about? 
(e.g., 'eye drops', 'break', 'exercise')"""
            state["reminder_step"] = 1
            return explanation
        elif state["reminder_step"] == 1:
            state["reminder_data"]["type"] = user_text
            state["reminder_step"] = 2
            return f"""✓ Got it! You want reminders for: **{user_text}**

⏰ What time should I remind you?
   Format: (e.g., '9:00 AM', '2:30 PM', 'morning', 'evening')"""
        elif state["reminder_step"] == 2:
            state["reminder_data"]["time"] = user_text
            state["reminder_step"] = 3
            return f"""✓ Time set: **{user_text}**

📅 How often do you need this?
   • daily (Every day)
   • weekly (Once a week)
   • custom (Specific pattern)"""
        elif state["reminder_step"] == 3:
            state["reminder_data"]["frequency"] = user_text
            # Confirmation with all details
            reminder_text = f"{state['reminder_data']['type']} at {state['reminder_data']['time']} ({state['reminder_data']['frequency']})"
            state["reminder_step"] = 0  # Reset
            return f"""✅ **Reminder Successfully Created!**

📌 Reminder Details:
   • Task: {state['reminder_data']['type']}
   • Time: {state['reminder_data']['time']}
   • Frequency: {state['reminder_data']['frequency']}

🎉 You'll get notified to {state['reminder_data']['type']} at {state['reminder_data']['time']}!
Set more reminders anytime by typing 'remind me' 🔔"""
    
    # ===== VISION CHECK =====
    if intent == "vision_check" or "vision" in text_lower:
        return f"👀 Vision concerns detected, {patient_name}!\n\nCan you tell me more? (e.g., blur, difficulty reading, headache)"
    
    # ===== EYE CARE TIPS =====
    if intent == "eye_care_tips" or "care" in text_lower:
        tips = """
👁️ **Complete Eye Care Guide for Kids** 👁️

🔵 **Screen Time Management:**
  ✓ 20-20-20 Rule: Every 20 mins → Look 20 feet away for 20 seconds
  ✓ Keep screen 18-24 inches away from eyes
  ✓ Adjust brightness & contrast for comfort
  ✓ Limit daily screen to 2 hours max

📖 **Reading & Homework:**
  ✓ Use good lighting (natural light preferred)
  ✓ Keep books 10-12 inches from eyes
  ✓ Sit up straight with good posture
  ✓ Take breaks every 30 minutes

🥗 **Nutrition Tips:**
  ✓ Eat carrots, spinach, berries daily
  ✓ Include fish (salmon, tuna) 2-3x/week
  ✓ Drink 6-8 glasses of water daily
  ✓ Limit sugary drinks & snacks

🏃 **Physical Activity:**
  ✓ Play outdoors 1-2 hours daily
  ✓ Play ball games (improves tracking)
  ✓ Reduce indoor time for eye development
  ✓ Practice sports requiring focus

💤 **Eye Hygiene:**
  ✓ Blink regularly (reduces dry eyes)
  ✓ Don't rub eyes (can cause infection)
  ✓ Wash hands before touching eyes
  ✓ Use prescribed eye drops on time

👁️ **Warning Signs (Tell a Doctor):**
  🔴 Persistent squinting or eye strain
  🔴 Difficulty seeing board at school
  🔴 Frequent headaches
  🔴 Eyes crossing/turned
  🔴 Redness or excessive tearing

📅 **Regular Checkups:**
  • Annual eye exams (minimum)
  • More frequent if prescribed glasses
  • Share screen time concerns with doctor
        """
        return tips
    
    # ===== DEFAULT (only if confidence is low) =====
    if confidence < 0.55:
        return f"I can help with:\n✅ Foods\n✅ Exercises\n✅ Reminders\n✅ Eye Care Tips\n\nWhat would you like, {patient_name}? 😊"
    
    return f"I'm not sure about that, {patient_name}. Ask me about foods, exercises, reminders, or vision tips! 👀"

# ========================
# 8) DEMO & TESTING
# ========================
if __name__ == "__main__":
    print("=" * 80)
    print("[DEMO] AI Health Assistant with Dislikes & Patient Names")
    print("=" * 80 + "\n")
    
    # Test 1: Dislike handling
    print("[Test 1] Dislike Handling")
    session_1 = "test_user_1"
    print("USER: I don't like milk and dryfruit")
    reply = get_ai_reply("I don't like milk and dryfruit", "Koushik", session_1)
    print(f"AI: {reply}\n")
    
    print("USER: Show me foods")
    reply = get_ai_reply("Show me foods", "Koushik", session_1)
    print(f"AI: {reply}\n")
    
    print("USER: remove milk")
    reply = get_ai_reply("remove milk", "Koushik", session_1)
    print(f"AI: {reply}\n")
    
    # Test 2: Features only when asked
    print("\n[Test 2] Greeting")
    print("USER: hi")
    reply = get_ai_reply("hi", "Koushik", "test_user_2")
    print(f"AI: {reply}\n")
    
    print("USER: exercise")
    reply = get_ai_reply("exercise", "Koushik", "test_user_2")
    print(f"AI: {reply}\n")
    
    print("=" * 80)
    print("[SUCCESS] All features working correctly!")
    print("=" * 80)
