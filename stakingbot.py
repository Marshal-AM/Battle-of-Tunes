import os
import asyncio
import logging
import sqlite3
import threading
from datetime import datetime, timedelta

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ConversationHandler
)
import aiohttp

# Logging setup
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', 
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Constants for conversation states
WAITING_WALLET = 1

class ParticipantsDatabase:
    def __init__(self, db_path='song_battle_participants.db'):
        """
        Initialize the database with participant tracking.
        
        Args:
            db_path (str): Path to the SQLite database file
        """
        self.db_path = db_path
        self._lock = threading.Lock()
        self._init_database()

    def _init_database(self):
        """
        Create the database tables if they don't exist.
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Participants table with comprehensive details
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS participants (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                wallet_address TEXT UNIQUE,
                audio_file TEXT,
                verified BOOLEAN DEFAULT 1,
                battle_start_timestamp DATETIME,
                battle_active BOOLEAN DEFAULT 0
            )
        ''')
        
        conn.commit()
        conn.close()

    def add_participant(self, user_id, username, wallet_address):
        """
        Add a participant to the database.
        
        Args:
            user_id (int): Telegram user ID
            username (str): Telegram username
            wallet_address (str): User's wallet address
        """
        with self._lock:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            try:
                cursor.execute('''
                    INSERT OR REPLACE INTO participants 
                    (user_id, username, wallet_address, verified, battle_start_timestamp, battle_active) 
                    VALUES (?, ?, ?, 1, datetime('now'), 1)
                ''', (user_id, username, wallet_address))
                
                conn.commit()
            except sqlite3.Error as e:
                logger.error(f"Database error: {e}")
            finally:
                conn.close()

    def get_participants(self):
        """
        Retrieve all active participants.
        
        Returns:
            dict: Dictionary of active participants
        """
        with self._lock:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            try:
                cursor.execute('SELECT * FROM participants WHERE battle_active = 1')
                results = cursor.fetchall()
                
                participants = {}
                for result in results:
                    participants[result[0]] = {
                        'username': result[1],
                        'wallet_address': result[2],
                        'audio_file': result[3],
                        'verified': bool(result[4])
                    }
                
                return participants
            except sqlite3.Error as e:
                logger.error(f"Database error: {e}")
                return {}
            finally:
                conn.close()

    def is_participant_verified(self, user_id):
        """
        Check if a user is a verified participant.
        
        Args:
            user_id (int): Telegram user ID
        
        Returns:
            bool: True if participant is verified, False otherwise
        """
        with self._lock:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            try:
                cursor.execute(
                    'SELECT verified FROM participants WHERE user_id = ? AND battle_active = 1',
                    (user_id,)
                )
                result = cursor.fetchone()
                return result is not None and bool(result[0])
            except sqlite3.Error as e:
                logger.error(f"Database error: {e}")
                return False
            finally:
                conn.close()

    def update_participant_audio(self, user_id, audio_file):
        """
        Update the audio file for a participant.
        
        Args:
            user_id (int): Telegram user ID
            audio_file (str): Path to the audio file
        """
        with self._lock:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            try:
                cursor.execute(
                    'UPDATE participants SET audio_file = ? WHERE user_id = ? AND battle_active = 1',
                    (audio_file, user_id)
                )
                conn.commit()
            except sqlite3.Error as e:
                logger.error(f"Database error: {e}")
            finally:
                conn.close()

    def reset_battle(self):
        """
        Reset the battle state for all participants.
        """
        with self._lock:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            try:
                # Update all participants to reset battle state
                cursor.execute('''
                    UPDATE participants 
                    SET battle_active = 0, audio_file = NULL, battle_start_timestamp = NULL
                ''')
                conn.commit()
            except sqlite3.Error as e:
                logger.error(f"Database error: {e}")
            finally:
                conn.close()

    def get_battle_status(self):
        """
        Check if a battle is currently active.
        
        Returns:
            bool: True if a battle is active, False otherwise
        """
        with self._lock:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            try:
                cursor.execute('SELECT COUNT(*) FROM participants WHERE battle_active = 1')
                result = cursor.fetchone()
                return result[0] > 0
            except sqlite3.Error as e:
                logger.error(f"Database error: {e}")
                return False
            finally:
                conn.close()

class SongBattleBot:
    def __init__(self, token):
        self.token = token
        self.participants_db = ParticipantsDatabase()

    async def start(self, update: Update, context):
        """Handler for /start command"""
        user = update.effective_user

        # Check if a battle is active and user is already a verified participant
        if self.participants_db.get_battle_status() and self.participants_db.is_participant_verified(user.id):
            await update.message.reply_text(
                "You're already registered for the current song battle!"
            )
            return

        await update.message.reply_text(
            f"Welcome {user.mention_markdown_v2()}! Please provide your crypto wallet address."
        )
        return WAITING_WALLET

    async def validate_wallet_address(self, update: Update, context):
        """Validate and store wallet address"""
        wallet_address = update.message.text.strip()
        user = update.effective_user

        # Basic wallet address validation
        if not wallet_address.startswith('0x') or len(wallet_address) != 42:
            await update.message.reply_text(
                "Invalid wallet address. Please provide a valid Ethereum wallet address."
            )
            return WAITING_WALLET

        # Add participant to database
        self.participants_db.add_participant(
            user_id=user.id,
            username=user.username,
            wallet_address=wallet_address
        )

        await update.message.reply_text(
            f"Wallet address registered! Here's the link to the Music generation bot: https://t.me/musicgen_051203_bot"
        )
        return ConversationHandler.END

    async def receive_audio(self, update: Update, context):
        """Handle audio file submission"""
        user = update.effective_user

        # Check if user is a verified participant
        if not self.participants_db.is_participant_verified(user.id):
            await update.message.reply_text("You're not registered for this battle.")
            return

        # Download and save audio file
        audio_file = await update.message.audio.get_file()
        file_path = f"audio_submissions/{user.id}_{audio_file.file_unique_id}.mp3"
        await audio_file.download_to_drive(file_path)

        # Update participant's audio file in database
        self.participants_db.update_participant_audio(user.id, file_path)

        # Check if all participants have submitted
        participants = self.participants_db.get_participants()
        if all(p.get('audio_file') for p in participants.values()):
            await self.process_battle(context)

    async def process_battle(self, context):
        """Submit audio files to evaluation API"""
        # Get participants from database
        participants = self.participants_db.get_participants()

        # Prepare submission data
        submission_data = {
            'submissions': [
                {
                    'wallet_address': participant['wallet_address'],
                    'audio_file': participant['audio_file']
                }
                for participant in participants.values()
                if participant['audio_file']
            ]
        }

        async with aiohttp.ClientSession() as session:
            async with session.post('https://your-evaluation-api.com/submit', json=submission_data) as response:
                result = await response.json()

        # Announce winner
        winner_wallet = result.get('winner_wallet')
        winner = next(
            (p for p in participants.values() if p['wallet_address'] == winner_wallet),
            None
        )

        if winner:
            message = f"🏆 Battle Winner: {winner['username']} (Wallet: {winner_wallet})"
        else:
            message = "No winner could be determined."

        # Broadcast to all participants
        for user_id in participants:
            try:
                await context.bot.send_message(chat_id=user_id, text=message)
            except Exception as e:
                logger.error(f"Could not send message to {user_id}: {e}")

        # Reset battle state
        self.participants_db.reset_battle()

    def main(self):
        """Set up and run the bot"""
        application = Application.builder().token(self.token).build()

        # Conversation handler
        conv_handler = ConversationHandler(
            entry_points=[CommandHandler('start', self.start)],
            states={
                WAITING_WALLET: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, self.validate_wallet_address)
                ],
            },
            fallbacks=[]
        )

        # Add handlers
        application.add_handler(conv_handler)
        application.add_handler(MessageHandler(filters.AUDIO, self.receive_audio))

        # Start the bot
        application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    # Replace with your actual Telegram bot token
    TOKEN = '************************'

    # Ensure audio submissions directory exists
    os.makedirs('audio_submissions', exist_ok=True)

    bot = SongBattleBot(TOKEN)
    bot.main()