import telebot
from web3 import Web3
import time
import sqlite3
import threading
import os
from datetime import datetime

class Config:
    BOT_TOKEN = "************************"  
    WEB3_PROVIDER = "https://data-seed-prebsc-1-s1.binance.org:8545"
    CONTRACT_ADDRESS = "0xA546819d48330FB2E02D3424676d13D7B8af3bB2"
    CONTRACT_ABI = [{"inputs":[],"stateMutability":"nonpayable","type":"constructor"},{"anonymous":"false","inputs":[{"indexed":"true","internalType":"address","name":"recipient","type":"address"},{"indexed":"false","internalType":"uint256","name":"amount","type":"uint256"}],"name":"FundsSent","type":"event"},{"anonymous":"false","inputs":[{"indexed":"true","internalType":"address","name":"user","type":"address"},{"indexed":"false","internalType":"uint256","name":"amount","type":"uint256"}],"name":"Staked","type":"event"},{"inputs":[],"name":"STAKE_AMOUNT","outputs":[{"internalType":"uint256","name":"","type":"uint256"}],"stateMutability":"view","type":"function"},{"inputs":[{"internalType":"address","name":"","type":"address"}],"name":"hasStaked","outputs":[{"internalType":"bool","name":"","type":"bool"}],"stateMutability":"view","type":"function"},{"inputs":[],"name":"owner","outputs":[{"internalType":"address","name":"","type":"address"}],"stateMutability":"view","type":"function"},{"inputs":[{"internalType":"address payable","name":"recipient","type":"address"}],"name":"sendFundsTo","outputs":[],"stateMutability":"nonpayable","type":"function"},{"inputs":[],"name":"stake","outputs":[],"stateMutability":"payable","type":"function"},{"inputs":[{"internalType":"address","name":"user","type":"address"}],"name":"verifyStake","outputs":[{"internalType":"bool","name":"","type":"bool"}],"stateMutability":"view","type":"function"},{"inputs":[],"name":"withdraw","outputs":[],"stateMutability":"nonpayable","type":"function"}]
    DB_FOLDER = '/content/drive/MyDrive/BattleOfTunes/'
    DB_NAME = 'song_battle_participants.db'
    STAKE_PAGE_URL = "*********************"
    STAKE_AMOUNT = "0.0002"
    BASE_GROUP_INVITE_LINK = "https://t.me/+NxOSoOVa-BUwYWVl"
    FIXED_CHAT_ID = -4701503942  

class DatabaseManager:
    def __init__(self):
        self.db_path = os.path.join(Config.DB_FOLDER, Config.DB_NAME)
        self._lock = threading.Lock()
        self._ensure_database()

    def _ensure_database(self):
        """Initialize database with participants table"""
        os.makedirs(Config.DB_FOLDER, exist_ok=True)

        with self._lock:
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

            cursor.execute('CREATE INDEX IF NOT EXISTS idx_wallet ON participants(wallet_address)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_battle_active ON participants(battle_active)')

            conn.commit()
            conn.close()

    def update_participant_info(self, user_id, username, wallet_address, chat_id=None):
        """Update or insert participant information"""
        chat_id = Config.FIXED_CHAT_ID  # Always use the fixed chat ID
        with self._lock:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            try:
                current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                cursor.execute('''
                INSERT INTO participants
                (user_id, username, wallet_address, chat_id, verified,
                 battle_start_timestamp, battle_active, audio_file)
                VALUES (?, ?, ?, ?, 1, ?, 0, NULL)
                ON CONFLICT(user_id, chat_id) DO UPDATE SET
                username = COALESCE(excluded.username, username),
                wallet_address = COALESCE(excluded.wallet_address, wallet_address),
                verified = 1,
                battle_start_timestamp = COALESCE(battle_start_timestamp, ?),
                battle_active = COALESCE(battle_active, 0)
                ''', (user_id, username, wallet_address, chat_id, current_time, current_time))
                conn.commit()
                return True
            except sqlite3.Error as e:
                print(f"Database error in update_participant_info: {e}")
                return False
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
        @self.bot.message_handler(commands=['start'])
        def start_handler(message):
            welcome_message = (
                "Welcome to Battle of Tunes! 🎵\n\n"
                "Available commands:\n"
                "/stake <wallet_address> - Start the staking process to participate\n"
                "/verify <wallet_address> - Verify your existing stake\n\n"
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

                for _ in range(18):  # 3 minute timeout
                    if self._verify_stake(user_wallet):
                        if self._handle_successful_stake(message, user_wallet):
                            self.bot.reply_to(message, "Staking verified! You are now registered for Battle of Tunes.")
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
                        self.bot.reply_to(message, "Stake verified! Your registration is confirmed.")
                        return
                else:
                    self.bot.reply_to(message, "You have not staked the required amount.")

            except Exception as e:
                self.bot.reply_to(message, f"An error occurred: {str(e)}")

    def _verify_stake(self, user_wallet):
        try:
            return self.contract.functions.verifyStake(user_wallet).call()
        except Exception as e:
            print(f"Error verifying stake: {e}")
            return False

    def _handle_successful_stake(self, message, wallet_address):
        success = self.db.update_participant_info(
            user_id=message.from_user.id,
            username=message.from_user.username,
            wallet_address=wallet_address,
            chat_id=Config.FIXED_CHAT_ID  # Use fixed chat ID instead of message.chat.id
        )
        return success

    def run(self):
        print("Bot is running...")
        self.bot.polling()

if __name__ == "__main__":
    bot = BattleOfTunesBot()
    bot.run()
