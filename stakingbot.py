import telebot
from web3 import Web3
import secrets
import time
import sqlite3
import threading
import os
from datetime import datetime

# Configuration
class Config:
    # Telegram Bot Token
    BOT_TOKEN = "***********************************"

    # Web3 Configuration
    WEB3_PROVIDER = "https://data-seed-prebsc-1-s1.binance.org:8545"
    CONTRACT_ADDRESS = "0x242c0c356cbaea0e1a80a574f1d3571a0babe772"
    CONTRACT_ABI = [
        {
            "inputs": [],
            "name": "stake",
            "outputs": [],
            "stateMutability": "payable",
            "type": "function"
        },
        {
            "inputs": [{"internalType": "address", "name": "user", "type": "address"}],
            "name": "verifyStake",
            "outputs": [{"internalType": "bool", "name": "", "type": "bool"}],
            "stateMutability": "view",
            "type": "function"
        },
    ]

    # Database Configuration
    DB_FOLDER = '/content/drive/MyDrive/BattleOfTunes/'
    DB_NAME = 'song_battle_participants.db'

    # Staking Configuration
    STAKE_PAGE_URL = "*******************************"
    BASE_GROUP_INVITE_LINK = "https://t.me/+NxOSoOVa-BUwYWVl"
    STAKE_AMOUNT = "0.0002"

class DatabaseManager:
    def __init__(self):
        self.db_path = os.path.join(Config.DB_FOLDER, Config.DB_NAME)
        self._lock = threading.Lock()
        self._ensure_database()

    def _ensure_database(self):
        """Initialize database and create tables if they don't exist"""
        os.makedirs(Config.DB_FOLDER, exist_ok=True)

        with self._lock:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            # Create participants table
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS participants (
                user_id INTEGER NOT NULL,
                chat_id INTEGER NOT NULL,
                username TEXT,
                wallet_address TEXT,
                audio_file TEXT,
                verified INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (user_id, chat_id)
            )
            ''')

            # Create invite_links table
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS invite_links (
                wallet_address TEXT PRIMARY KEY,
                invite_link TEXT NOT NULL,
                used INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                expires_at TIMESTAMP
            )
            ''')

            # Create indexes
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_wallet ON participants(wallet_address)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_verified ON participants(verified)')

            conn.commit()
            conn.close()

    def update_participant_info(self, user_id, username, wallet_address, chat_id):
        """Update or insert participant information"""
        with self._lock:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            try:
                cursor.execute('''
                INSERT INTO participants
                (user_id, username, wallet_address, chat_id, verified, updated_at)
                VALUES (?, ?, ?, ?, 1, CURRENT_TIMESTAMP)
                ON CONFLICT(user_id, chat_id) DO UPDATE SET
                username = COALESCE(excluded.username, username),
                wallet_address = COALESCE(excluded.wallet_address, wallet_address),
                verified = 1,
                updated_at = CURRENT_TIMESTAMP
                ''', (user_id, username, wallet_address, chat_id))
                conn.commit()
                return True
            except sqlite3.Error as e:
                print(f"Database error in update_participant_info: {e}")
                return False
            finally:
                conn.close()

    def add_invite_link(self, wallet_address, invite_link):
        """Add or update an invite link for a wallet address"""
        with self._lock:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            try:
                # Set expiration to 24 hours from now
                cursor.execute('''
                    INSERT OR REPLACE INTO invite_links
                    (wallet_address, invite_link, used, created_at, expires_at)
                    VALUES (?, ?, 0, CURRENT_TIMESTAMP, datetime('now', '+1 day'))
                ''', (wallet_address, invite_link))
                conn.commit()
                return True
            except sqlite3.Error as e:
                print(f"Database error in add_invite_link: {e}")
                return False
            finally:
                conn.close()

    def get_participant_info(self, wallet_address):
        """Get participant information by wallet address"""
        with self._lock:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            try:
                cursor.execute('''
                    SELECT user_id, username, verified, audio_file
                    FROM participants
                    WHERE wallet_address = ?
                ''', (wallet_address,))
                return cursor.fetchone()
            except sqlite3.Error as e:
                print(f"Database error in get_participant_info: {e}")
                return None
            finally:
                conn.close()

class BattleOfTunesBot:
    def __init__(self):
        self.bot = telebot.TeleBot(Config.BOT_TOKEN)
        self.web3 = Web3(Web3.HTTPProvider(Config.WEB3_PROVIDER))
        self.contract = self.web3.eth.contract(
            address=Web3.to_checksum_address(Config.CONTRACT_ADDRESS),
            abi=Config.CONTRACT_ABI
        )
        self.db = DatabaseManager()
        self._setup_handlers()

    def _setup_handlers(self):
        """Set up message handlers for the bot"""
        @self.bot.message_handler(commands=['start'])
        def start_handler(message):
            welcome_message = (
                "Welcome to Battle of Tunes! 🎵\n\n"
                "Available commands:\n"
                "/stake <wallet_address> - Start the staking process to participate\n"
                "/verify <wallet_address> - Verify your existing stake and get group invite\n\n"
                "To participate in Battle of Tunes, you'll need to stake first. "
                "Use the /stake command followed by your wallet address to begin!"
            )
            self.bot.reply_to(message, welcome_message)

        @self.bot.message_handler(commands=['stake'])
        def stake_handler(message):
            try:
                command_parts = message.text.split()
                if len(command_parts) != 2:
                    self.bot.reply_to(message, "Usage: /stake <wallet_address>")
                    return

                user_wallet = command_parts[1]
                if not self.web3.is_address(user_wallet):
                    self.bot.reply_to(message, "Invalid wallet address. Please provide a valid address.")
                    return

                stake_link = f"{Config.STAKE_PAGE_URL}?wallet={user_wallet}&amount={Config.STAKE_AMOUNT}"
                self.bot.reply_to(message,
                    f"Please complete your staking by visiting the link below:\n\n{stake_link}")
                self.bot.reply_to(message, "Waiting for transaction confirmation...")

                # Poll for stake confirmation
                for _ in range(18):  # 3 minute timeout (18 * 10 seconds)
                    if self._verify_stake(user_wallet):
                        if self._handle_successful_stake(message, user_wallet):
                            return
                        break
                    time.sleep(10)

                self.bot.reply_to(message,
                    "Staking not detected. Please ensure the transaction was completed successfully.")

            except Exception as e:
                self.bot.reply_to(message, f"An error occurred: {str(e)}")

        @self.bot.message_handler(commands=['verify'])
        def verify_stake_handler(message):
            try:
                command_parts = message.text.split()
                if len(command_parts) != 2:
                    self.bot.reply_to(message, "Usage: /verify <wallet_address>")
                    return

                user_wallet = command_parts[1]
                if not self.web3.is_address(user_wallet):
                    self.bot.reply_to(message, "Invalid wallet address. Please provide a valid address.")
                    return

                if self._verify_stake(user_wallet):
                    if self._handle_successful_stake(message, user_wallet):
                        return
                else:
                    self.bot.reply_to(message, "You have not staked the required amount.")

            except Exception as e:
                self.bot.reply_to(message, f"An error occurred: {str(e)}")

    def _verify_stake(self, user_wallet):
        """Verify if a user has staked the required amount"""
        try:
            return self.contract.functions.verifyStake(user_wallet).call()
        except Exception as e:
            print(f"Error verifying stake: {e}")
            return False

    def _generate_invite_link(self, wallet_address):
        """Generate a unique one-time invite link"""
        unique_token = secrets.token_urlsafe(16)
        one_time_link = f"{Config.BASE_GROUP_INVITE_LINK}?start={unique_token}"
        self.db.add_invite_link(wallet_address, one_time_link)
        return one_time_link

    def _handle_successful_stake(self, message, wallet_address):
        """Handle successful stake verification and invite link generation"""
        success = self.db.update_participant_info(
            user_id=message.from_user.id,
            username=message.from_user.username,
            wallet_address=wallet_address,
            chat_id=message.chat.id
        )

        if not success:
            self.bot.reply_to(message, "Error updating participant information.")
            return False

        invite_link = self._generate_invite_link(wallet_address)
        if invite_link:
            self.bot.reply_to(
                message,
                f"Staking verified! Your unique group invite link is:\n\n{invite_link}\n\n"
                "This link can only be used once and expires in 24 hours!"
            )
            return True
        else:
            self.bot.reply_to(message, "Staking verified, but group invite generation failed.")
            return False

    def run(self):
        """Start the bot"""
        print("Bot is running...")
        self.bot.polling()

if __name__ == "__main__":
    bot = BattleOfTunesBot()
    bot.run()
