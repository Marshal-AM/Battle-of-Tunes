import telebot
from web3 import Web3
import secrets
import time
import sqlite3
import threading

# Telegram Bot Token
BOT_TOKEN = "***************************"
bot = telebot.TeleBot(BOT_TOKEN)
STAKE_PAGE_URL = "******************************"

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

class ParticipantsDatabase:
    def __init__(self, db_path='/content/drive/MyDrive/BattleOfTunes/song_battle_participants.db'):
        self.db_path = db_path
        self._lock = threading.Lock()
        self._init_database()

    def _init_database(self):
        """
        Create the database tables if they don't exist.
        """
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

        cursor.execute('''
        CREATE TABLE IF NOT EXISTS invite_links (
            wallet_address TEXT PRIMARY KEY,
            invite_link TEXT UNIQUE,
            used BOOLEAN DEFAULT 0
        )
        ''')

        conn.commit()
        conn.close()

    def update_participant_info(self, user_id, username, wallet_address, chat_id):
        """
        Update or insert participant information including username and wallet address.
        Sets audio_file to None for new entries.
        """
        with self._lock:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            try:
                cursor.execute('''
                INSERT INTO participants
                (user_id, username, wallet_address, chat_id, audio_file, verified)
                VALUES (?, ?, ?, ?, NULL, 1)
                ON CONFLICT(user_id, chat_id) DO UPDATE SET
                username = COALESCE(excluded.username, username),
                wallet_address = COALESCE(excluded.wallet_address, wallet_address),
                verified = 1
                ''', (user_id, username, wallet_address, chat_id))
                conn.commit()
                return True
            except sqlite3.Error as e:
                print(f"Database error: {e}")
                return False
            finally:
                conn.close()

    def add_invite_link(self, wallet_address, invite_link):
        """
        Add or update an invite link for a wallet address.
        """
        with self._lock:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            try:
                cursor.execute('''
                    INSERT OR REPLACE INTO invite_links
                    (wallet_address, invite_link, used)
                    VALUES (?, ?, 0)
                ''', (wallet_address, invite_link))
                conn.commit()
                return True
            except sqlite3.Error as e:
                print(f"Database error: {e}")
                return False
            finally:
                conn.close()

# Initialize database manager
db_manager = ParticipantsDatabase()

web3 = Web3(Web3.HTTPProvider(WEB3_PROVIDER))
contract = web3.eth.contract(address=Web3.to_checksum_address(CONTRACT_ADDRESS), abi=CONTRACT_ABI)

# Base group invite link
BASE_GROUP_INVITE_LINK = "https://t.me/+NxOSoOVa-BUwYWVl"

@bot.message_handler(commands=['start'])
def start_handler(message):
    welcome_message = (
        "Welcome to Battle of Tunes! 🎵\n\n"
        "Available commands:\n"
        "/stake <wallet_address> - Start the staking process to participate\n"
        "/verify <wallet_address> - Verify your existing stake and get group invite\n\n"
        "To participate in Battle of Tunes, you'll need to stake first. Use the /stake command followed by your wallet address to begin!"
    )
    bot.reply_to(message, welcome_message)

def generate_one_time_invite_link(wallet_address):
    unique_token = secrets.token_urlsafe(16)
    one_time_link = f"{BASE_GROUP_INVITE_LINK}?start={unique_token}"
    db_manager.add_invite_link(wallet_address, one_time_link)
    return one_time_link

def verify_and_get_invite_link(wallet_address):
    if not verify_stake(wallet_address):
        return None
    return generate_one_time_invite_link(wallet_address)

def verify_stake(user_wallet):
    try:
        return contract.functions.verifyStake(user_wallet).call()
    except Exception as e:
        print(f"Error verifying stake: {e}")
        return False

@bot.message_handler(commands=['stake'])
def stake_handler(message):
    try:
        command_parts = message.text.split()
        if len(command_parts) != 2:
            bot.reply_to(message, "Usage: /stake <wallet_address>")
            return

        user_wallet = command_parts[1]
        if not web3.is_address(user_wallet):
            bot.reply_to(message, "Invalid wallet address. Please provide a valid address.")
            return

        stake_link = f"{STAKE_PAGE_URL}?wallet={user_wallet}&amount=0.0002"
        bot.reply_to(message, f"Please complete your staking by visiting the link below:\n\n{stake_link}")
        bot.reply_to(message, "Waiting for transaction confirmation...")

        for _ in range(18):
            has_staked = verify_stake(user_wallet)
            if has_staked:
                success = db_manager.update_participant_info(
                    user_id=message.from_user.id,
                    username=message.from_user.username,
                    wallet_address=user_wallet,
                    chat_id=message.chat.id
                )

                if not success:
                    bot.reply_to(message, "Error updating participant information.")
                    return

                invite_link = verify_and_get_invite_link(user_wallet)
                if invite_link:
                    bot.reply_to(
                        message,
                        f"Staking confirmed! Your unique group invite link is:\n\n{invite_link}\n\nThis link can only be used once!"
                    )
                    return
                else:
                    bot.reply_to(message, "Staking verified, but group invite generation failed.")
                    return
            time.sleep(10)

        bot.reply_to(message, "Staking not detected. Please ensure the transaction was completed successfully.")
    except Exception as e:
        bot.reply_to(message, f"An error occurred: {str(e)}")

@bot.message_handler(commands=['verify'])
def verify_stake_handler(message):
    try:
        command_parts = message.text.split()
        if len(command_parts) != 2:
            bot.reply_to(message, "Usage: /verify <wallet_address>")
            return

        user_wallet = command_parts[1]
        if not web3.is_address(user_wallet):
            bot.reply_to(message, "Invalid wallet address. Please provide a valid address.")
            return

        if verify_stake(user_wallet):
            success = db_manager.update_participant_info(
                user_id=message.from_user.id,
                username=message.from_user.username,
                wallet_address=user_wallet,
                chat_id=message.chat.id
            )

            if not success:
                bot.reply_to(message, "Error updating participant information.")
                return

            invite_link = verify_and_get_invite_link(user_wallet)
            if invite_link:
                bot.reply_to(
                    message,
                    f"Staking verified! Your unique group invite link is:\n\n{invite_link}\n\nThis link can only be used once!"
                )
            else:
                bot.reply_to(message, "Staking verified, but group invite generation failed.")
        else:
            bot.reply_to(message, "You have not staked the required amount.")
    except Exception as e:
        bot.reply_to(message, f"An error occurred: {str(e)}")

if __name__ == "__main__":
    print("Bot is running...")
    bot.polling()
