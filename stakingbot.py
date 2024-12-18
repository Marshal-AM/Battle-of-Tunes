import telebot
from web3 import Web3
import qrcode
from io import BytesIO
import time

# Telegram Bot Token
BOT_TOKEN = "**********************************"
bot = telebot.TeleBot(BOT_TOKEN)
STAKE_PAGE_URL = "https://samfelix03.github.io/MusicBattle/"

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

staking_status = {}


web3 = Web3(Web3.HTTPProvider(WEB3_PROVIDER))
contract = web3.eth.contract(address=Web3.to_checksum_address(CONTRACT_ADDRESS), abi=CONTRACT_ABI)

# Group Invite Link
GROUP_INVITE_LINK = "LINK"  # Replace with your group invite link

# Command Handlers

@bot.message_handler(commands=['stake'])
def stake_handler(message):
    """Generates transaction details for the user to stake using their wallet."""
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

        # Generate transaction data
        # staking_amount = web3.to_wei(1, 'ether')  # Example: 1 BNB

        stake_link = generate_stake_link(user_wallet, 0.0002)

        # Send the link to the user
        bot.reply_to(message, f"Please complete your staking by visiting the link below:\n\n{stake_link}")


        # Wait and verify staking status
        bot.reply_to(message, "Waiting for transaction confirmation...")

        # Retry check every 10 seconds for 3 minutes
        for _ in range(18):  # 18 attempts (10 seconds each)
            has_staked = verify_stake(user_wallet)
            if has_staked:
                bot.reply_to(
                    message,
                    f"Staking confirmed! You have successfully staked the required amount.\n\nHere's your invite link to the premium group: {GROUP_INVITE_LINK}"
                )
                return
            time.sleep(10)

        bot.reply_to(message, "Staking not detected. Please ensure the transaction was completed successfully.")
    except Exception as e:
        bot.reply_to(message, f"An error occurred: {str(e)}")


@bot.message_handler(commands=['verify'])
def verify_stake_handler(message):
    """Directly verifies if the user has staked the required amount."""
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

        # Check if the user has staked
        has_staked = verify_stake(user_wallet)
        if has_staked:
            bot.reply_to(
                message,
                f"Staking verified! Here is your invite link to join the group:\n\n{GROUP_INVITE_LINK}"
            )
        else:
            bot.reply_to(message, "You have not staked the required amount.")
    except Exception as e:
        bot.reply_to(message, f"An error occurred: {str(e)}")


# Helper Functions

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

def generate_stake_link(wallet_address, staking_amount_bnb):
    """Generate a unique link for the staking page."""
    # Generate a random unique ID for the staking request (e.g., to track the transaction later)
    unique_id = ''.join(random.choices(string.ascii_letters + string.digits, k=10))

    # Create a link to the staking page with the wallet address and amount as URL params
    return f"{STAKE_PAGE_URL}?wallet={wallet_address}&amount={staking_amount_bnb}&id={unique_id}"


# Run the bot
if __name__ == "__main__":
    print("Bot is running...")
    bot.polling()
