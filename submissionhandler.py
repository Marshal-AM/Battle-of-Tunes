import os
import asyncio
import logging
import sqlite3
import threading
from datetime import datetime, timedelta
import telebot
from telebot.async_telebot import AsyncTeleBot
from telebot.handler_backends import State, StatesGroup
from telebot.storage import StateMemoryStorage
import aiohttp

# Logging setup
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

AUDIO_GEN_BOT_USERNAME = "@musicgen_051203_bot"  # Replace with actual audio generation bot username

class ParticipantsDatabase:
    def __init__(self, db_path='/content/drive/MyDrive/BattleOfTunes/song_battle_participants.db'):
        self.db_path = db_path
        self._lock = threading.Lock()

        # Ensure the directory exists
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)

        # Initialize database with lock to prevent race conditions
        with self._lock:
            self._init_database()

    def _init_database(self):
        """Create the database tables if they don't exist."""
        conn = None
        try:
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

        except sqlite3.Error as e:
            logger.error(f"Failed to initialize database: {e}")
            raise
        finally:
            if conn:
                conn.close()

    def get_all_inactive_participants(self):
        """Get all participants who aren't in an active battle"""
        with self._lock:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            try:
                cursor.execute('''
                    SELECT user_id, username, wallet_address, chat_id
                    FROM participants
                    WHERE battle_active = 0
                    ORDER BY battle_start_timestamp DESC NULLS LAST
                ''')
                return cursor.fetchall()
            except sqlite3.Error as e:
                logger.error(f"Database error: {e}")
                return []
            finally:
                conn.close()

    def get_participants(self, chat_id):
        """Get active participants for a specific group"""
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

    def get_all_participants_for_chat(self, chat_id):
        """Get all participants (both active and inactive) for a specific group"""
        with self._lock:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            try:
                cursor.execute('''
                    SELECT username, wallet_address, battle_active
                    FROM participants
                    WHERE chat_id = ?
                    ORDER BY battle_active DESC, username
                ''', (chat_id,))
                return cursor.fetchall()
            except sqlite3.Error as e:
                logger.error(f"Database error: {e}")
                return []
            finally:
                conn.close()

    def activate_battle_for_users(self, user_ids, chat_id):
        """Activate battle for specified users in a chat"""
        with self._lock:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            try:
                cursor.execute('''
                    UPDATE participants
                    SET battle_active = 1,
                        battle_start_timestamp = datetime('now')
                    WHERE user_id IN ({}) AND chat_id = ?
                '''.format(','.join('?' * len(user_ids))), (*user_ids, chat_id))

                conn.commit()
                return True
            except sqlite3.Error as e:
                logger.error(f"Database error: {e}")
                return False
            finally:
                conn.close()

    def check_user_in_battle(self, user_id, chat_id):
        """Check if user is in active battle"""
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

    def check_all_participants_submitted(self, chat_id):
        """Check if all participants have submitted audio"""
        with self._lock:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            try:
                cursor.execute('''
                    SELECT COUNT(*)
                    FROM participants
                    WHERE chat_id = ? AND battle_active = 1 AND audio_file IS NULL
                ''', (chat_id,))
                result = cursor.fetchone()
                return result[0] == 0
            except sqlite3.Error as e:
                logger.error(f"Database error: {e}")
                return False
            finally:
                conn.close()

    def get_participants_for_submission(self, chat_id):
        """Get participants with their audio files"""
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
        """Reset battle state for a group"""
        with self._lock:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            try:
                cursor.execute('''
                    UPDATE participants
                    SET battle_active = 0,
                        audio_file = NULL,
                        battle_start_timestamp = NULL
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
        self.bot = AsyncTeleBot(token, state_storage=StateMemoryStorage())
        self.participants_db = ParticipantsDatabase()
        self.evaluation_tasks = {}
        self.active_battles = set()
        self.setup_handlers()

    def setup_handlers(self):
        @self.bot.message_handler(commands=['start'])
        async def handle_start(message):
            """Handle the /start command"""
            welcome_text = (
                "🎵 Welcome to Song Battle Bot! 🎵\n\n"
                "I organize music creation battles where participants generate and compete with their AI-created tracks.\n\n"
                "📜 How it works:\n"
                "1. When there are 3 eligible participants, a battle automatically begins\n"
                f"2. Participants use {AUDIO_GEN_BOT_USERNAME} to create their tracks\n"
                "3. Once all tracks are submitted, they're evaluated and a winner is chosen\n\n"
                "🎮 Commands:\n"
                "/start - Show this information and current participants\n"
                "/gentrack - Get the link to generate your track when in battle\n\n"
            )

            # Get current participants
            participants = self.participants_db.get_all_participants_for_chat(message.chat.id)

            if participants:
                participant_text = "👥 Current Participants:\n\n"
                active_participants = []
                waiting_participants = []

                for username, wallet, is_active in participants:
                    user_info = f"@{username} (Wallet: {wallet[:6]}...{wallet[-4:]})"
                    if is_active:
                        active_participants.append(user_info + " 🎮")
                    else:
                        waiting_participants.append(user_info)

                if active_participants:
                    participant_text += "Active Battle:\n" + "\n".join(active_participants) + "\n\n"
                if waiting_participants:
                    participant_text += "Waiting for Battle:\n" + "\n".join(waiting_participants)
            else:
                participant_text = "👥 No participants registered yet!"

            full_message = welcome_text + "\n" + participant_text
            await self.bot.reply_to(message, full_message)

        @self.bot.message_handler(commands=['gentrack'])
        async def handle_gentrack(message):
            """Direct active participants to the audio generation bot"""
            user_id = message.from_user.id
            chat_id = message.chat.id

            if not self.participants_db.check_user_in_battle(user_id, chat_id):
                await self.bot.reply_to(
                    message,
                    "You are not currently participating in any active battles."
                )
                return

            await self.bot.reply_to(
                message,
                f"Please generate your track using {AUDIO_GEN_BOT_USERNAME}\n\n"
                "Once your track is generated, it will be automatically included in the battle.\n"
                "No need to submit it here - I'll check periodically for your generated track."
            )

    async def check_for_battles(self):
        """Continuously check for potential battles"""
        while True:
            try:
                all_participants = self.participants_db.get_all_inactive_participants()

                chat_participants = {}
                for user_id, username, wallet, chat_id in all_participants:
                    if chat_id not in chat_participants:
                        chat_participants[chat_id] = []
                    chat_participants[chat_id].append((user_id, username, wallet))

                for chat_id, participants in chat_participants.items():
                    if chat_id in self.active_battles:
                        continue

                    if len(participants) >= 3:
                        valid_participants = []
                        for user_id, username, wallet in participants:
                            try:
                                member = await self.bot.get_chat_member(chat_id, user_id)
                                if member.status in ['member', 'administrator', 'creator']:
                                    valid_participants.append((user_id, username, wallet))
                            except telebot.apihelper.ApiTelegramException:
                                continue

                        if len(valid_participants) == 3:
                            user_ids = [p[0] for p in valid_participants]
                            if self.participants_db.activate_battle_for_users(user_ids, chat_id):
                                self.active_battles.add(chat_id)
                                await self.start_battle(chat_id, valid_participants)

            except Exception as e:
                logger.error(f"Error in battle checking: {e}")

            await asyncio.sleep(30)

    async def start_battle(self, chat_id, participants):
        """Start a battle with the given participants"""
        participant_mentions = ", ".join(f"@{username}" for _, username, _ in participants)
        announcement = (
            "🎵 Battle of Tunes has begun! 🎵\n\n"
            f"Today's Contestants:\n{participant_mentions}\n\n"
            "🎼 How to Generate Your Track:\n"
            f"1. Head over to {AUDIO_GEN_BOT_USERNAME}\n"
            "2. Generate your track using their interface\n"
            "3. Your generated track will be automatically included in the battle\n\n"
            "Need the generation link? Use the /gentrack command here\n\n"
            "⏰ Important Notes:\n"
            "• I'll check every 10 seconds for your generated tracks\n"
            "• The battle will be evaluated once all tracks are received\n"
            "• Don't submit tracks here - use only the generation bot\n\n"
            "May the best tune win! 🎧"
        )
        await self.bot.send_message(chat_id, announcement)

        self.evaluation_tasks[chat_id] = asyncio.create_task(
            self.monitor_battle_submissions(chat_id)
        )

    async def monitor_battle_submissions(self, chat_id):
        """Monitor battle submissions by checking database"""
        try:
            while True:
                if self.participants_db.check_all_participants_submitted(chat_id):
                    await self.submit_to_evaluation(chat_id)
                    return
                await asyncio.sleep(10)
        except Exception as e:
            logger.error(f"Monitoring error for group {chat_id}: {e}")
        finally:
            if chat_id in self.active_battles:
                self.active_battles.remove(chat_id)

    async def submit_to_evaluation(self, chat_id):
        """Submit to evaluation API using form-data format and display detailed results"""
        submissions = self.participants_db.get_participants_for_submission(chat_id)

        try:
            # Prepare form data
            form_data = aiohttp.FormData()

            # Add audio files first (in order)
            for idx, submission in enumerate(submissions):
                audio_data = submission['audio_file']
                form_data.add_field(f'audio_{idx + 1}',
                                  audio_data,
                                  filename=f'track{idx + 1}.mp3',
                                  content_type='audio/mpeg')

            # Add wallet addresses in the same order
            for idx, submission in enumerate(submissions):
                form_data.add_field(f'wallet_{idx + 1}',
                                  submission['wallet_address'])

            # Submit to evaluation API
            async with aiohttp.ClientSession() as session:
                async with session.post('https://music-evaluation.onrender.com/evaluate-tracks/',
                                      data=form_data) as response:
                    if response.status != 200:
                        raise Exception(f"API returned status code {response.status}")
                    result = await response.json()

            # Get winner details
            winner_wallet = result['winner_wallet']
            winning_track = result['winning_track']
            winning_score = result['score']

            # Format rankings message
            rankings_message = "🎵 Battle Results 🎵\n\n"

            # Add timestamp
            battle_time = datetime.fromisoformat(result['timestamp'])
            rankings_message += f"🕒 Battle completed at: {battle_time.strftime('%Y-%m-%d %H:%M:%S')}\n\n"

            # Add rankings
            for idx, ranking in enumerate(result['all_rankings'], 1):
                wallet = ranking['wallet_address']
                score = ranking['quality_score']
                track = ranking['file_name']
                features = ranking['features']

                participant = next(
                    (p for p in participants.values() if p['wallet_address'] == wallet),
                    None
                )

                username = participant['username'] if participant else "Unknown"

                rankings_message += f"#{idx} @{username}\n"
                rankings_message += f"🎵 Track: {track}\n"
                rankings_message += f"💰 Wallet: {wallet[:6]}...{wallet[-4:]}\n"
                rankings_message += f"📊 Score: {score:.2f}\n"
                rankings_message += "🎼 Features:\n"
                rankings_message += f"  • Energy: {features['energy']:.3f}\n"
                rankings_message += f"  • Danceability: {features['danceability']:.3f}\n"
                rankings_message += f"  • Instrumentalness: {features['instrumentalness']:.3f}\n"
                rankings_message += f"  • Loudness: {features['loudness']:.2f} dB\n\n"

            # Add transaction hash
            rankings_message += f"🔗 Transaction Hash: {result['transaction_hash'][:6]}...{result['transaction_hash'][-4:]}\n\n"

            # Add score differences if available
            if result.get('score_differences'):
                rankings_message += "📊 Score Differences:\n"
                for idx, diff in enumerate(result['score_differences'], 1):
                    rankings_message += f"#{idx+1} vs #{idx}: {diff:.3f} points\n"

            # Send results
            await self.bot.send_message(
                chat_id=chat_id,
                text=rankings_message,
                parse_mode='HTML'
            )

            # Reset battle
            self.participants_db.reset_battle(chat_id)
            del self.evaluation_tasks[chat_id]

        except Exception as e:
            logger.error(f"Evaluation error for group {chat_id}: {e}")
            await self.bot.send_message(
                chat_id=chat_id,
                text="⚠️ An error occurred during battle evaluation. Please try again later."
            )

    # [Rest of the code remains the same...]

    async def run(self):
        """Run the bot with battle checking"""
        logger.info("Starting bot...")
        # Start both the battle checker and polling in parallel
        await asyncio.gather(
            self.check_for_battles(),
            self.bot.polling()
        )
