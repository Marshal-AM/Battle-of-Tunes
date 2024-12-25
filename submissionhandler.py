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
    ConversationHandler,
    ContextTypes
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
        Initialize the database with participant tracking for group battles.
        
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
        
        # Participants table with group-specific fields
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
        """
        Add a participant to the database for a specific group battle.
        
        Args:
            user_id (int): Telegram user ID
            username (str): Telegram username
            wallet_address (str): User's wallet address
            chat_id (int): Group chat ID
        """
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
                    (user_id, username, wallet_address, chat_id, verified, battle_start_timestamp, battle_active) 
                    VALUES (?, ?, ?, ?, 1, datetime('now'), 1)
                ''', (user_id, username, wallet_address, chat_id))
                
                conn.commit()
            except sqlite3.Error as e:
                logger.error(f"Database error: {e}")
            finally:
                conn.close()

    def get_participants(self, chat_id):
        """
        Retrieve active participants for a specific group.
        
        Args:
            chat_id (int): Group chat ID
        
        Returns:
            dict: Dictionary of active participants
        """
        with self._lock:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            try:
                cursor.execute('''
                    SELECT user_id, username, wallet_address, audio_file 
                    FROM participants 
                    WHERE chat_id = ? AND battle_active = 1
                ''', (chat_id,))
                results = cursor.fetchall()
                
                participants = {}
                for result in results:
                    participants[result[0]] = {
                        'username': result[1],
                        'wallet_address': result[2],
                        'audio_file': result[3]
                    }
                
                return participants
            except sqlite3.Error as e:
                logger.error(f"Database error: {e}")
                return {}
            finally:
                conn.close()

    def check_user_in_battle(self, user_id, chat_id):
        """
        Check if a user is already in an active battle for a specific group.
        
        Args:
            user_id (int): Telegram user ID
            chat_id (int): Group chat ID
        
        Returns:
            bool: True if user is in an active battle, False otherwise
        """
        with self._lock:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            try:
                cursor.execute('''
                    SELECT COUNT(*) 
                    FROM participants 
                    WHERE user_id = ? AND chat_id = ? AND battle_active = 1
                ''', (user_id, chat_id))
                result = cursor.fetchone()
                return result[0] > 0
            except sqlite3.Error as e:
                logger.error(f"Database error: {e}")
                return False
            finally:
                conn.close()

    def update_participant_audio(self, user_id, chat_id, audio_file):
        """
        Update the audio file for a participant in a specific group battle.
        
        Args:
            user_id (int): Telegram user ID
            chat_id (int): Group chat ID
            audio_file (str): Path to the audio file
        """
        with self._lock:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            try:
                cursor.execute('''
                    UPDATE participants 
                    SET audio_file = ? 
                    WHERE user_id = ? AND chat_id = ? AND battle_active = 1
                ''', (audio_file, user_id, chat_id))
                conn.commit()
            except sqlite3.Error as e:
                logger.error(f"Database error: {e}")
            finally:
                conn.close()

    def check_all_participants_submitted(self, chat_id):
        """
        Check if all participants in a group have submitted audio files.
        
        Args:
            chat_id (int): Group chat ID
        
        Returns:
            bool: True if all participants have submitted, False otherwise
        """
        with self._lock:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            try:
                # Check if all participants have a non-None audio file
                cursor.execute('''
                    SELECT COUNT(*) 
                    FROM participants 
                    WHERE chat_id = ? AND battle_active = 1 AND audio_file IS NULL
                ''', (chat_id,))
                result = cursor.fetchone()
                
                # If count is 0, all participants have submitted
                return result[0] == 0
            except sqlite3.Error as e:
                logger.error(f"Database error: {e}")
                return False
            finally:
                conn.close()

    def get_participants_for_submission(self, chat_id):
        """
        Get participants with their audio files for submission in a specific group.
        
        Args:
            chat_id (int): Group chat ID
        
        Returns:
            list: List of participants with audio files
        """
        with self._lock:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            try:
                cursor.execute('''
                    SELECT wallet_address, audio_file 
                    FROM participants 
                    WHERE chat_id = ? AND battle_active = 1 AND audio_file IS NOT NULL
                ''', (chat_id,))
                return [
                    {
                        'wallet_address': result[0],
                        'audio_file': result[1]
                    }
                    for result in cursor.fetchall()
                ]
            except sqlite3.Error as e:
                logger.error(f"Database error: {e}")
                return []
            finally:
                conn.close()

    def reset_battle(self, chat_id):
        """
        Reset the battle state for a specific group.
        
        Args:
            chat_id (int): Group chat ID
        """
        with self._lock:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            try:
                # Update participants to reset battle state for specific group
                cursor.execute('''
                    UPDATE participants 
                    SET battle_active = 0, audio_file = NULL, battle_start_timestamp = NULL
                    WHERE chat_id = ?
                ''', (chat_id,))
                conn.commit()
            except sqlite3.Error as e:
                logger.error(f"Database error: {e}")
            finally:
                conn.close()

class SongBattleBot:
    def __init__(self, token):
        self.token = token
        self.participants_db = ParticipantsDatabase()
        self.evaluation_tasks = {}  # Track evaluation tasks per group

    async def start_battle(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handler for /startbattle command in a group"""
        chat = update.effective_chat
        user = update.effective_user

        # Check if a battle is already active in this group
        participants = self.participants_db.get_participants(chat.id)
        if participants:
            await update.message.reply_text(
                "A battle is already active in this group. Wait for it to finish!"
            )
            return

        await update.message.reply_text(
            "🎵 Song Battle Started! 🎵\n"
            "Participants, use /join to enter the battle!"
        )

    async def join_battle(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handler for /join command to enter the battle"""
        chat = update.effective_chat
        user = update.effective_user

        # Check if a battle is active in this group
        participants = self.participants_db.get_participants(chat.id)
        if not participants:
            await update.message.reply_text(
                "No active battle. Start a battle first with /startbattle"
            )
            return

        # Check if user is already in the battle
        if self.participants_db.check_user_in_battle(user.id, chat.id):
            await update.message.reply_text(
                "You're already in this battle!"
            )
            return

        # Prompt for wallet address
        await update.message.reply_text(
            f"{user.mention_markdown_v2()}, please provide your crypto wallet address."
        )
        return WAITING_WALLET

    async def validate_wallet_address(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Validate and store wallet address for group battle"""
        wallet_address = update.message.text.strip()
        user = update.effective_user
        chat = update.effective_chat

        # Basic wallet address validation
        if not wallet_address.startswith('0x') or len(wallet_address) != 42:
            await update.message.reply_text(
                "Invalid wallet address. Please provide a valid Ethereum wallet address."
            )
            return WAITING_WALLET

        # Add participant to database for this group
        self.participants_db.add_participant(
            user_id=user.id,
            username=user.username,
            wallet_address=wallet_address,
            chat_id=chat.id
        )

        # Start evaluation monitoring if not already started
        if chat.id not in self.evaluation_tasks:
            self.evaluation_tasks[chat.id] = asyncio.create_task(
                self.monitor_battle_submissions(context, chat.id)
            )

        await update.message.reply_text(
            f"Wallet address registered! {user.mention_markdown_v2()} is now in the battle. "
            "Upload your audio track when ready!"
        )
        return ConversationHandler.END

    async def receive_audio(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle audio file submission in group"""
        user = update.effective_user
        chat = update.effective_chat
        participants = self.participants_db.get_participants(chat.id)

        # Check if user is a verified participant in this group's battle
        if user.id not in participants:
            await update.message.reply_text("You're not registered for this battle.")
            return

        # Download and save audio file
        audio_file = await update.message.audio.get_file()
        file_path = f"audio_submissions/{chat.id}_{user.id}_{audio_file.file_unique_id}.mp3"
        await audio_file.download_to_drive(file_path)

        # Update participant's audio file in database
        self.participants_db.update_participant_audio(user.id, chat.id, file_path)

        # Confirm audio submission
        await update.message.reply_text(f"{user.mention_markdown_v2()} has submitted their track!")

    async def monitor_battle_submissions(self, context, chat_id):
        """
        Monitor battle submissions with periodic checking for a specific group.
        
        Checks every 5 seconds if all participants have submitted.
        Automatically submits to evaluation after 5 minutes.
        """
        try:
            while True:
                # Check if all participants have submitted
                if self.participants_db.check_all_participants_submitted(chat_id):
                    await self.submit_to_evaluation(context, chat_id)
                    return

                # Wait 5 seconds before checking again
                await asyncio.sleep(5)

                # Check if 5 minutes have passed since battle start
                # TODO: Implement timestamp check if needed
        except asyncio.CancelledError:
            # Task was cancelled
            return
        except Exception as e:
            logger.error(f"Error in battle submission monitoring for group {chat_id}: {e}")

    async def submit_to_evaluation(self, context, chat_id):
        """Submit audio files to evaluation API for a specific group"""
        # Get participants with audio files
        submissions = self.participants_db.get_participants_for_submission(chat_id)

        # Prepare submission data
        submission_data = {
            'submissions': submissions
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post('https://your-evaluation-api.com/submit', json=submission_data) as response:
                    result = await response.json()

            # Announce winner
            winner_wallet = result.get('winner_wallet')
            participants = self.participants_db.get_participants(chat_id)
            
            winner = next(
                (p for p in participants.values() if p['wallet_address'] == winner_wallet),
                None
            )

            if winner:
                message = f"🏆 Battle Winner: @{winner['username']} (Wallet: {winner_wallet})"
            else:
                message = "No winner could be determined."

            # Send winner announcement to the group
            await context.bot.send_message(chat_id=chat_id, text=message)

            # Reset battle state for this group
            self.participants_db.reset_battle(chat_id)
            del self.evaluation_tasks[chat_id]

        except Exception as e:
            logger.error(f"Evaluation submission error for group {chat_id}: {e}")

    def main(self):
        """Set up and run the bot"""
        application = Application.builder().token(self.token).build()

        # Conversation handler for joining battle
        join_battle_handler = ConversationHandler(
            entry_points=[CommandHandler('join', self.join_battle)],
            states={
                WAITING_WALLET: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, self.validate_wallet_address)
                ],
            },
            fallbacks=[]
        )

        # Add handlers
        application.add_handler(CommandHandler('startbattle', self.start_battle))
        application.add_handler(join_battle_handler)
        application.add_handler
