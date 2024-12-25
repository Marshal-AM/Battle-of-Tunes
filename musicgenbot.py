import os
import asyncio
import logging
import sqlite3
import threading
import requests
import telebot
from telebot.async_telebot import AsyncTeleBot
from telebot.types import ReplyKeyboardMarkup, ReplyKeyboardRemove

# Logging setup
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Existing ParticipantsDatabase class would be here (as you provided earlier)
# For brevity, I'll just include the key methods

class ParticipantsDatabase:
    def __init__(self, db_path='song_battle_participants.db'):
        self.db_path = db_path
        self._lock = threading.Lock()
        self._init_database()

    def _init_database(self):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS participants (
        user_id INTEGER,
        username TEXT,
        wallet_address TEXT,
        audio_file TEXT,
        chat_id INTEGER,
        verified BOOLEAN DEFAULT 1,
        battle_start_timestamp DATETIME,
        battle_active BOOLEAN DEFAULT 0,
        PRIMARY KEY (user_id, chat_id)
        )
        ''')
        conn.commit()
        conn.close()

    def add_participant(self, user_id, username, wallet_address, chat_id):
        with self._lock:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            try:
                # Remove any existing entries for this user in the current group
                cursor.execute('''
                DELETE FROM participants
                WHERE user_id = ? AND chat_id = ?
                ''', (user_id, chat_id))
                
                # Insert new participant entry
                cursor.execute('''
                INSERT INTO participants
                (user_id, username, wallet_address, chat_id, verified)
                VALUES (?, ?, ?, ?, 1)
                ''', (user_id, username, wallet_address, chat_id))
                conn.commit()
                return True
            except sqlite3.Error as e:
                logger.error(f"Database error: {e}")
                return False
            finally:
                conn.close()

    def update_participant_audio(self, user_id, chat_id, audio_file):
        with self._lock:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            try:
                cursor.execute('''
                UPDATE participants
                SET audio_file = ?
                WHERE user_id = ? AND chat_id = ?
                ''', (audio_file, user_id, chat_id))
                conn.commit()
            except sqlite3.Error as e:
                logger.error(f"Database error: {e}")
            finally:
                conn.close()

    def check_wallet_address(self, wallet_address):
        with self._lock:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            try:
                # Basic wallet address validation and existence check
                cursor.execute('''
                SELECT COUNT(*) 
                FROM participants 
                WHERE wallet_address = ?
                ''', (wallet_address,))
                result = cursor.fetchone()
                return result[0] > 0
            except sqlite3.Error as e:
                logger.error(f"Database error: {e}")
                return False
            finally:
                conn.close()

# Replace with your actual configurations
BOT_TOKEN = '**********************************'
MUSIC_MODEL_API = '********************************'

# Initialize the Telegram Bot and Database
bot = AsyncTeleBot(BOT_TOKEN)
db_manager = ParticipantsDatabase()

# Store user states and last generated audio
user_states = {}
user_last_audio = {}

def validate_wallet_address(wallet_address):
    """
    Validate wallet address format and check against database
    """
    # Basic Ethereum address validation
    if not wallet_address.startswith('0x') or len(wallet_address) != 42:
        return False
    
    # Check if wallet exists in database
    return db_manager.check_wallet_address(wallet_address)

@bot.message_handler(commands=['start'])
async def send_welcome(message):
    """Send a welcome message and request wallet address"""
    welcome_text = (
        "Welcome to the Music Generation Bot! 🎵\n\n"
        "Please provide your Ethereum wallet address to verify your participation."
    )
    await bot.reply_to(message, welcome_text)
    user_states[message.chat.id] = 'awaiting_wallet_address'

@bot.message_handler(func=lambda message: user_states.get(message.chat.id) == 'awaiting_wallet_address')
async def verify_wallet(message):
    """Verify the provided wallet address"""
    wallet_address = message.text.strip()

    # Validate wallet address
    if validate_wallet_address(wallet_address):
        # Add or update user record in the database
        db_manager.add_participant(
            user_id=message.from_user.id, 
            username=message.from_user.username, 
            wallet_address=wallet_address, 
            chat_id=message.chat.id
        )

        # Send welcome message after verification
        welcome_text = (
            "Welcome! Your wallet has been verified. 🎉\n\n"
            "Use /generate to create music with a text prompt\n"
            "Use /about to learn more about the bot"
        )
        await bot.reply_to(message, welcome_text)
        
        # Reset user state
        user_states[message.chat.id] = None
    else:
        # Invalid wallet address
        await bot.reply_to(message, "Invalid wallet address or you are not a registered participant. Please try again.")

@bot.message_handler(commands=['generate'])
async def initiate_generation(message):
    """Initiate music generation process"""
    await bot.reply_to(message, "Please send me a text prompt describing the music you want to generate.")
    user_states[message.chat.id] = 'awaiting_prompt'

@bot.message_handler(func=lambda message: user_states.get(message.chat.id) == 'awaiting_prompt')
async def generate_music(message):
    """Handle music generation requests"""
    # Send initial waiting message
    waiting_message = await bot.reply_to(message, "Please wait till we perform magic (create your music audio file)...")

    try:
        # Prepare the request to the music generation API
        payload = {
            'prompts': [message.text]
        }

        # Make POST request to the music generation API
        response = requests.post(MUSIC_MODEL_API, json=payload)

        # Check if the request was successful
        if response.status_code == 200:
            # Save the generated audio file
            audio_file_path = f'generated_music_{message.chat.id}.mp3'
            with open(audio_file_path, 'wb') as f:
                f.write(response.content)

            # Send the audio file 
            with open(audio_file_path, 'rb') as audio:
                await bot.send_audio(message.chat.id, audio)

            # Delete the waiting message
            await bot.delete_message(message.chat.id, waiting_message.message_id)

            # Store the audio file path for potential submission
            user_last_audio[message.chat.id] = audio_file_path

            # Ask for satisfaction with submit option
            satisfaction_markup = ReplyKeyboardMarkup(row_width=2)
            submit_button = telebot.types.KeyboardButton('Submit')
            no_button = telebot.types.KeyboardButton('No')
            satisfaction_markup.add(submit_button, no_button)

            await bot.send_message(
                message.chat.id,
                "Do you want to submit this audio or generate a new one?",
                reply_markup=satisfaction_markup
            )

            # Update user state
            user_states[message.chat.id] = 'awaiting_satisfaction'
        else:
            # Handle API error
            error_message = f"Sorry, music generation failed. Status code: {response.status_code}"
            await bot.reply_to(message, error_message)

            # Reset user state
            user_states[message.chat.id] = None

    except Exception as e:
        # Handle any unexpected errors
        error_message = f"An error occurred: {str(e)}"
        await bot.reply_to(message, error_message)

        # Reset user state
        user_states[message.chat.id] = None

@bot.message_handler(func=lambda message: user_states.get(message.chat.id) == 'awaiting_satisfaction')
async def handle_satisfaction(message):
    """Handle user satisfaction with generated music"""
    if message.text.lower() == 'submit':
        # Submit the audio to the user's record in the database
        if message.chat.id in user_last_audio:
            try:
                # Update user record with audio file path in the database
                db_manager.update_participant_audio(
                    user_id=message.from_user.id, 
                    chat_id=message.chat.id, 
                    audio_file=user_last_audio[message.chat.id]
                )

                await bot.send_message(
                    message.chat.id,
                    "Audio successfully submitted and recorded! 🎵",
                    reply_markup=ReplyKeyboardRemove()
                )

                # Clean up the audio file reference
                del user_last_audio[message.chat.id]
            except Exception as e:
                await bot.send_message(
                    message.chat.id,
                    f"Submission failed: {str(e)}",
                    reply_markup=ReplyKeyboardRemove()
                )

            # Reset user state
            user_states[message.chat.id] = None
        else:
            await bot.send_message(
                message.chat.id,
                "No audio to submit. Please generate a new audio file first.",
                reply_markup=ReplyKeyboardRemove()
            )
    elif message.text.lower() == 'no':
        await bot.send_message(
            message.chat.id,
            "No problem! Use /generate command again to create another music file.",
            reply_markup=ReplyKeyboardRemove()
        )
        # Clean up the last generated audio
        if message.chat.id in user_last_audio:
            os.remove(user_last_audio[message.chat.id])
            del user_last_audio[message.chat.id]

        # Reset user state
        user_states[message.chat.id] = None
    else:
        # If user doesn't select Submit or No
        await bot.send_message(
            message.chat.id,
            "Please select 'Submit' or 'No'.",
            reply_markup=ReplyKeyboardRemove()
        )

@bot.message_handler(func=lambda message: True)
async def handle_other_messages(message):
    """Handle messages that don't match any specific command"""
    await bot.reply_to(message, "Please use /generate to create music or /about to learn more about the bot.")

def main():
    print("Bot is running...")
    bot.polling(none_stop=True)

if __name__ == '__main__':
    main()
