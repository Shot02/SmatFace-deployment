import logging
import random
from django.utils import timezone

logger = logging.getLogger(__name__)

# AI message collections
MORNING_MESSAGES = [
    "Rise and shine! Today is a new opportunity to be awesome!",
    "Good morning! Remember, your attitude determines your direction.",
    "A positive mindset in the morning leads to productivity all day!",
    "Start your day with determination and end it with satisfaction.",
    "Morning productivity tip: tackle your most challenging task first!",
    "Success is not final, failure is not fatal: it's the courage to continue that counts.",
    "Every morning brings new potential, but only if you're awake to receive it!",
    "Your future is created by what you do today, not tomorrow.",
    "The early bird gets the worm, but the second mouse gets the cheese. Be strategic!",
    "Today's goals: 1) Be productive 2) Be awesome 3) Repeat tomorrow"
]

EVENING_MESSAGES = [
    "Great job today! Time to rest and recharge for tomorrow.",
    "Your hard work today sets you up for success tomorrow.",
    "Remember to take time for yourself this evening. Self-care matters!",
    "Reflect on your accomplishments today, not just your to-do list.",
    "Evening wisdom: Don't bring work stress home with you.",
    "You've earned your rest. Tomorrow is another opportunity.",
    "Success is the sum of small efforts repeated day after day.",
    "Take pride in how far you've come and have faith in how far you'll go.",
    "The best preparation for tomorrow is doing your best today.",
    "Congratulations on another productive day! Time to unwind."
]

MARK_IN_MESSAGES = [
    "A smile is the best way to start your day! \ud83d\ude0a",
    "Did you know? Taking breaks boosts productivity by 20%!",
    "Looking sharp today! The camera loves you!",
    "Early bird catches the worm! Or in this case, marks attendance!",
    "Your face is your password here. And what a secure password it is!",
    "Stand tall like you own the place... because you do!",
    "Remember: Coffee first, then conquer the world!",
    "That's a face ready to tackle the day!",
    "Pro tip: Stretch every hour for better focus!",
    "You're not just marking in, you're making history!"
]

MARK_OUT_MESSAGES = [
    "Another day, another dollar! \ud83d\udcb0",
    "Time to relax and recharge those batteries!",
    "Did you do your best today? That's all that matters!",
    "Leaving on time is a form of self-care!",
    "Tomorrow is another chance to be awesome!",
    "All work and no play makes Jack a dull boy!",
    "Don't forget to hydrate before you leave!",
    "Great job today! Now go enjoy your evening!",
    "The best part of the workday? The end! Just kidding... maybe.",
    "You've earned this rest. See you tomorrow!"
]

MOTIVATIONAL_QUOTES = [
    "The only way to do great work is to love what you do. - Steve Jobs",
    "Believe you can and you're halfway there. - Theodore Roosevelt",
    "It does not matter how slowly you go as long as you do not stop. - Confucius",
    "Quality is not an act, it is a habit. - Aristotle",
    "If you're going through hell, keep going. - Winston Churchill",
    "You miss 100% of the shots you don't take. - Wayne Gretzky",
    "The future belongs to those who believe in the beauty of their dreams. - Eleanor Roosevelt",
    "The secret of getting ahead is getting started. - Mark Twain",
    "Don't watch the clock; do what it does. Keep going. - Sam Levenson",
    "The harder you work for something, the greater you'll feel when you achieve it.",
    "Your talent determines what you can do. Your motivation determines how much you're willing to do.",
    "The difference between ordinary and extraordinary is that little extra.",
    "The only limit to our realization of tomorrow is our doubts of today. - Franklin D. Roosevelt",
    "The way to get started is to quit talking and begin doing. - Walt Disney",
    "Don't let yesterday take up too much of today. - Will Rogers"
]

FUNNY_JOKES = [
    "Why don't scientists trust atoms? Because they make up everything!",
    "I told my wife she was drawing her eyebrows too high. She looked surprised.",
    "What do you call a fake noodle? An impasta!",
    "Why did the scarecrow win an award? Because he was outstanding in his field!",
    "I'm reading a book about anti-gravity. It's impossible to put down!",
    "Did you hear about the mathematician who's afraid of negative numbers? He'll stop at nothing to avoid them.",
    "Why don't skeletons fight each other? They don't have the guts.",
    "What's the best thing about Switzerland? I don't know, but the flag is a big plus.",
    "I used to be a baker, but I couldn't make enough dough.",
    "Why did the bicycle fall over? Because it was two tired!"
]

PRODUCTIVITY_TIPS = [
    "Try the Pomodoro Technique: 25 minutes of focused work followed by a 5-minute break.",
    "Set your three most important tasks at the beginning of each day.",
    "Use the 2-minute rule: If a task takes less than 2 minutes, do it now.",
    "Block distracting websites during your work hours.",
    "Keep your workspace clean and organized for better focus.",
    "Stay hydrated! Dehydration can reduce cognitive performance by up to 30%.",
    "Take short walks during breaks to boost creativity and energy.",
    "Group similar tasks together to minimize context switching.",
    "Try time-blocking your calendar to dedicate focused time for important work.",
    "End each day by planning your tasks for tomorrow."
]

DAILY_BOOST_QUOTES = MOTIVATIONAL_QUOTES + FUNNY_JOKES + PRODUCTIVITY_TIPS

def get_ai_message(user, context=None):
    """Generate an AI message based on user context"""
    try:
        # If context is explicitly provided
        if context == 'mark_in':
            return random.choice(MARK_IN_MESSAGES)
        elif context == 'mark_out':
            return random.choice(MARK_OUT_MESSAGES)
        elif context == 'daily_boost':
            return random.choice(DAILY_BOOST_QUOTES)
            
        # Check user's last attendance action from session
        if hasattr(user, 'session') and 'last_attendance_action' in user.session:
            if user.session['last_attendance_action'] == 'mark_in':
                return random.choice(MARK_OUT_MESSAGES)
            elif user.session['last_attendance_action'] == 'mark_out':
                return random.choice(MARK_IN_MESSAGES)
        
        # Default context is time of day
        current_hour = timezone.now().hour
        
        # Time-based messages
        if 5 <= current_hour < 12:
            return random.choice(MORNING_MESSAGES)
        elif 16 <= current_hour < 23:
            return random.choice(EVENING_MESSAGES)
        
        # Default fallback
        default_messages = MORNING_MESSAGES + EVENING_MESSAGES
        return random.choice(default_messages)
        
    except Exception as e:
        logger.error(f"Error generating AI message: {str(e)}")
        return "Have a great day!"

def handle_ai_feedback(user, is_positive, message=None):
    """Handle user feedback on AI messages"""
    try:
        from .models import AIFeedback
        
        # Create feedback record
        AIFeedback.objects.create(
            user=user,
            is_positive=is_positive,
            message=message or "",
            created_at=timezone.now()
        )
        
        logger.info(f"AI feedback recorded: user={user.id}, positive={is_positive}")
        return True
        
    except Exception as e:
        logger.error(f"Error handling AI feedback: {str(e)}")
        return False