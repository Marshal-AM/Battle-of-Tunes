import os
import asyncio
import logging
import sqlite3
import threading
import aiohttp
import nest_asyncio
import base64
from telebot.async_telebot import AsyncTeleBot
from telebot import types
from telebot.types import ReplyKeyboardMarkup, ReplyKeyboardRemove

# Logging setup
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

nest_asyncio.apply()

class ParticipantsDatabase:
    def __init__(self, db_path='/content/drive/MyDrive/BattleOfTunes/song_battle_participants.db'):
        self.db_path = db_path
        self._lock = threading.Lock()
        self._init_database()

    def _init_database(self):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS participants (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            wallet_address TEXT,
            audio_file TEXT,
            verified BOOLEAN DEFAULT 1,
            battle_start_timestamp DATETIME,
            battle_active BOOLEAN DEFAULT 0
        )
        ''')
        conn.commit()
        conn.close()

    def verify_participant(self, wallet_address, user_id):
        """Verify if a participant exists with the given wallet address and matches the user"""
        with self._lock:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            try:
                cursor.execute('''
                SELECT user_id
                FROM participants
                WHERE wallet_address = ?
                ''', (wallet_address,))
                result = cursor.fetchone()

                if result is None:
                    return False, "No participant found with this wallet address"

                db_user_id = result[0]
                if db_user_id != user_id:
                    return False, "Wallet address belongs to a different user"

                return True, "Participant verified successfully"
            except sqlite3.Error as e:
                logger.error(f"Database error: {e}")
                return False, f"Database error: {str(e)}"
            finally:
                conn.close()

    def update_participant_audio(self, user_id, audio_file):
        with self._lock:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            try:
                # First check if the participant exists
                cursor.execute('''
                SELECT COUNT(*)
                FROM participants
                WHERE user_id = ?
                ''', (user_id,))

                if cursor.fetchone()[0] == 0:
                    conn.close()
                    return False, "Participant not found"

                cursor.execute('''
                UPDATE participants
                SET audio_file = ?
                WHERE user_id = ?
                ''', (audio_file, user_id))
                conn.commit()
                return True, "Audio file updated successfully"
            except sqlite3.Error as e:
                logger.error(f"Database error: {e}")
                return False, f"Database error: {str(e)}"
            finally:
                conn.close()

# Bot initialization and configuration
BOT_TOKEN = '***********************************'
MUSIC_MODEL_API = '*******************************'

bot = AsyncTeleBot(BOT_TOKEN)
db_manager = ParticipantsDatabase()

user_states = {}
user_last_audio = {}

def validate_wallet_address(address):
    """Basic wallet address format validation"""
    return address.startswith('0x') and len(address) == 42

@bot.message_handler(commands=['start'])
async def send_welcome(message):
    welcome_text = (
        "Welcome to the Music Generation Bot! 🎵\n\n"
        "Please provide your Ethereum wallet address to verify your participation."
    )
    await bot.reply_to(message, welcome_text)
    user_states[message.from_user.id] = 'awaiting_wallet_address'

@bot.message_handler(func=lambda message: user_states.get(message.from_user.id) == 'awaiting_wallet_address')
async def verify_wallet(message):
    wallet_address = message.text.strip()

    if not validate_wallet_address(wallet_address):
        await bot.reply_to(message, "Invalid wallet address format. Please provide a valid Ethereum address.")
        return

    success, msg = db_manager.verify_participant(
        wallet_address=wallet_address,
        user_id=message.from_user.id
    )

    if success:
        welcome_text = (
            "Welcome back! Your wallet has been verified. 🎉\n\n"
            "Use /generate to create music with a text prompt\n"
            "Use /about to learn more about the bot"
        )
        await bot.reply_to(message, welcome_text)
        user_states[message.from_user.id] = None
    else:
        await bot.reply_to(message, f"Verification failed: {msg}")

@bot.message_handler(commands=['generate'])
async def initiate_generation(message):
    await bot.reply_to(message, "Please send me a text prompt describing the music you want to generate.")
    user_states[message.from_user.id] = 'awaiting_prompt'

@bot.message_handler(func=lambda message: user_states.get(message.from_user.id) == 'awaiting_prompt')
async def generate_music(message):
    """Handle music generation requests with base64 audio response"""
    waiting_message = await bot.reply_to(message, "Please wait till we perform magic (create your music audio file)...")

    try:
        # Prepare the request to the music generation API
        payload = {
            'data': [message.text]
        }

        # Make POST request to the music generation API using aiohttp
        async with aiohttp.ClientSession() as session:
            async with session.post(MUSIC_MODEL_API, json=payload) as response:
                if response.status == 200:
                    response_data = await response.json()
                    base64_audio = response_data.get('data', {}).get('audio')

                    if not base64_audio:
                        await bot.reply_to(message, "Error: No audio data received from the server.")
                        user_states[message.from_user.id] = None
                        return

                    # Decode base64 string to binary audio data
                    audio_binary = base64.b64decode(base64_audio)

                    # Save the decoded audio to an MP3 file
                    audio_file_path = f'generated_music_{message.from_user.id}.mp3'
                    with open(audio_file_path, 'wb') as f:
                        f.write(audio_binary)

                    # Send the audio file
                    with open(audio_file_path, 'rb') as audio:
                        await bot.send_audio(message.chat.id, audio)

                    # Delete the waiting message
                    await bot.delete_message(message.chat.id, waiting_message.message_id)

                    # Store the audio file path for potential submission
                    user_last_audio[message.from_user.id] = audio_file_path

                    # Ask for satisfaction with submit option
                    satisfaction_markup = ReplyKeyboardMarkup(row_width=2)
                    submit_button = types.KeyboardButton('Submit')
                    no_button = types.KeyboardButton('No')
                    satisfaction_markup.add(submit_button, no_button)

                    await bot.send_message(
                        message.chat.id,
                        "Do you want to submit this audio or generate a new one?",
                        reply_markup=satisfaction_markup
                    )

                    user_states[message.from_user.id] = 'awaiting_satisfaction'
                else:
                    error_message = f"Sorry, music generation failed. Status code: {response.status}"
                    await bot.reply_to(message, error_message)
                    user_states[message.from_user.id] = None

    except Exception as e:
        error_message = f"An error occurred: {str(e)}"
        await bot.reply_to(message, error_message)
        user_states[message.from_user.id] = None

@bot.message_handler(func=lambda message: user_states.get(message.from_user.id) == 'awaiting_satisfaction')
async def handle_satisfaction(message):
    if message.text.lower() == 'submit':
        if message.from_user.id in user_last_audio:
            try:
                success, msg = db_manager.update_participant_audio(
                    user_id=message.from_user.id,
                    audio_file=user_last_audio[message.from_user.id]
                )

                if success:
                    await bot.send_message(
                        message.chat.id,
                        "Audio successfully submitted and recorded! 🎵",
                        reply_markup=ReplyKeyboardRemove()
                    )
                else:
                    await bot.send_message(
                        message.chat.id,
                        f"Submission failed: {msg}",
                        reply_markup=ReplyKeyboardRemove()
                    )

                del user_last_audio[message.from_user.id]
            except Exception as e:
                await bot.send_message(
                    message.chat.id,
                    f"Submission failed: {str(e)}",
                    reply_markup=ReplyKeyboardRemove()
                )

            user_states[message.from_user.id] = None
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
        if message.from_user.id in user_last_audio:
            os.remove(user_last_audio[message.from_user.id])
            del user_last_audio[message.from_user.id]

        user_states[message.from_user.id] = None
    else:
        await bot.send_message(
            message.chat.id,
            "Please select 'Submit' or 'No'.",
            reply_markup=ReplyKeyboardRemove()
        )

@bot.message_handler(commands=['about'])
async def about_bot(message):
    about_text = (
        "🎵 *Music Generation Bot* 🎵\n\n"
        "This bot uses AI to generate music based on your text descriptions.\n\n"
        "Available commands:\n"
        "/start - Start the bot and verify your wallet\n"
        "/generate - Create new music with a text prompt\n"
        "/about - Show this information\n\n"
        "Created for the Battle of Tunes competition 🏆"
    )
    await bot.send_message(message.chat.id, about_text, parse_mode="Markdown")

@bot.message_handler(func=lambda message: True)
async def handle_other_messages(message):
    await bot.reply_to(message, "Please use /generate to create music or /about to learn more about the bot.")

async def main():
    print("Bot is running...")
    try:
        await bot.polling(non_stop=True, timeout=60)
    except Exception as e:
        logger.error(f"Bot polling error: {e}")
        await asyncio.sleep(5)
        await main()

if __name__ == '__main__':
    asyncio.run(main())
