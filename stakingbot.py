import telebot
from web3 import Web3
import secrets
import time
import sqlite3
import threading

# Telegram Bot Token
BOT_TOKEN = "*****************************"
bot = telebot.TeleBot(BOT_TOKEN)
STAKE_PAGE_URL = "*************************"

# Web3 Configuration
WEB3_PROVIDER = "https://data-seed-prebsc-1-s1.binance.org:8545"
CONTRACT_ADDRESS = "0x242c0c356cbaea0e1a80a574f1d3571a0babe772"
CONTRACT_ABI = [{"inputs":[],"stateMutability":"nonpayable","type":"constructor"},{"anonymous":false,"inputs":[{"indexed":true,"internalType":"address","name":"recipient","type":"address"},{"indexed":false,"internalType":"uint256","name":"amount","type":"uint256"}],"name":"FundsSent","type":"event"},{"anonymous":false,"inputs":[{"indexed":true,"internalType":"address","name":"user","type":"address"},{"indexed":false,"internalType":"uint256","name":"amount","type":"uint256"}],"name":"Staked","type":"event"},{"inputs":[],"name":"STAKE_AMOUNT","outputs":[{"internalType":"uint256","name":"","type":"uint256"}],"stateMutability":"view","type":"function"},{"inputs":[],"name":"owner","outputs":[{"internalType":"address","name":"","type":"address"}],"stateMutability":"view","type":"function"},{"inputs":[{"internalType":"address payable","name":"recipient","type":"address"}],"name":"sendFundsTo","outputs":[],"stateMutability":"nonpayable","type":"function"},{"inputs":[],"name":"stake","outputs":[],"stateMutability":"payable","type":"function"},{"inputs":[],"name":"withdraw","outputs":[],"stateMutability":"nonpayable","type":"function"}]

class ParticipantsDatabase:
    def __init__(self, db_path='song_battle_participants.db'):
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
        
        # Create a table for invite links if not exists
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS invite_links (
            wallet_address TEXT PRIMARY KEY,
            invite_link TEXT UNIQUE,
            used BOOLEAN DEFAULT 0
        )
        ''')
        
        conn.commit()
        conn.close()

    def add_verified_participant(self, wallet_address, user_id=None, username=None, chat_id=None):
        """
        Add a verified participant to the database.
        """
        with self._lock:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            try:
                # Remove any existing entries for this wallet
                cursor.execute('''
                DELETE FROM participants
                WHERE wallet_address = ?
                ''', (wallet_address,))
                
                # Insert new participant entry
                cursor.execute('''
                INSERT INTO participants
                (user_id, username, wallet_address, chat_id, verified)
                VALUES (?, ?, ?, ?, 1)
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
                # Insert or replace the record for this wallet
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
BASE_GROUP_INVITE_LINK = "https://t.me/+ImTq8tu-h_82N2Y9"

def generate_one_time_invite_link(wallet_address):
    """
    Generate a unique one-time invite link for a verified staker.
    """
    # Generate a cryptographically secure random token
    unique_token = secrets.token_urlsafe(16)
    
    # Construct the one-time invite link
    one_time_link = f"{BASE_GROUP_INVITE_LINK}?start={unique_token}"
    
    # Store the link in the database
    db_manager.add_invite_link(wallet_address, one_time_link)
    
    return one_time_link

def verify_and_get_invite_link(wallet_address):
    """
    Verify stake and generate or retrieve a one-time invite link.
    """
    # First, verify the stake
    if not verify_stake(wallet_address):
        return None
    
    # Generate or retrieve the one-time invite link
    return generate_one_time_invite_link(wallet_address)

def verify_stake(user_wallet):
    """
    Verifies if the user has staked the required amount by calling the contract function.
    """
    try:
        # Call the verifyStake function from the smart contract
        return contract.functions.verifyStake(user_wallet).call()
    except Exception as e:
        print(f"Error verifying stake: {e}")
        return False

@bot.message_handler(commands=['stake'])
def stake_handler(message):
    """
    Handle stake command to generate staking transaction link.
    """
    try:
        # Split command and address
        command_parts = message.text.split()
        if len(command_parts) != 2:
            bot.reply_to(message, "Usage: /stake <wallet_address>")
            return

        user_wallet = command_parts[1]
        if not web3.is_address(user_wallet):
            bot.reply_to(message, "Invalid wallet address. Please provide a valid address.")
            return

        # Generate staking transaction link
        stake_link = f"{STAKE_PAGE_URL}?wallet={user_wallet}&amount=0.0002"

        # Send the link to the user
        bot.reply_to(message, f"Please complete your staking by visiting the link below:\n\n{stake_link}")

        # Wait and verify staking status
        bot.reply_to(message, "Waiting for transaction confirmation...")

        # Retry check every 10 seconds for 3 minutes
        for _ in range(18):  # 18 attempts (10 seconds each)
            has_staked = verify_stake(user_wallet)
            if has_staked:
                # Add verified participant to the database
                db_manager.add_verified_participant(
                    wallet_address=user_wallet,
                    user_id=message.from_user.id,
                    username=message.from_user.username,
                    chat_id=message.chat.id
                )
                
                # Generate one-time invite link
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
    """
    Directly verify stake and generate one-time invite link if verified.
    """
    try:
        # Split command and address
        command_parts = message.text.split()
        if len(command_parts) != 2:
            bot.reply_to(message, "Usage: /verify <wallet_address>")
            return

        user_wallet = command_parts[1]
        if not web3.is_address(user_wallet):
            bot.reply_to(message, "Invalid wallet address. Please provide a valid address.")
            return

        # Verify stake
        if verify_stake(user_wallet):
            # Add verified participant to the database
            db_manager.add_verified_participant(
                wallet_address=user_wallet,
                user_id=message.from_user.id,
                username=message.from_user.username,
                chat_id=message.chat.id
            )

            # Generate one-time invite link
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

# Run the bot
if __name__ == "__main__":
    print("Bot is running...")
    bot.polling()
