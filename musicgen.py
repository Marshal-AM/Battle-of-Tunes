import os
import requests
import telebot

# Replace with your actual configurations
BOT_TOKEN = '8129215983:AAEeGuv6KUWyXXPfRI1CRTSjqd2WOxgWKCY'
MUSIC_MODEL_API = 'https://da2d-34-124-198-76.ngrok-free.app/generate-music'
SUBMISSION_CHAT_ID = '-4701503942'  # The chat where audio will be automatically submitted

# Initialize the Telegram Bot
bot = telebot.TeleBot(BOT_TOKEN)

# Store user states and last generated audio
user_states = {}
user_last_audio = {}

def send_audio_via_telegram_api(bot_token, chat_id, audio_file_path):
    """Send audio file using Telegram Bot API POST request"""
    url = f"https://api.telegram.org/bot{bot_token}/sendAudio"

    # Prepare the files and data for the request
    files = {
        'audio': open(audio_file_path, 'rb')
    }

    data = {
        'chat_id': chat_id,
        'title': 'Generated Music',
        'performer': 'AI Music Generator'
    }

    try:
        # Send the POST request
        response = requests.post(url, files=files, data=data)

        # Check the response
        response_json = response.json()

        if response.status_code == 200 and response_json.get('ok'):
            print("Audio sent successfully!")
            return response_json
        else:
            print("Failed to send audio")
            print(response_json)
            return None

    except Exception as e:
        print(f"Error sending audio: {e}")
        return None

@bot.message_handler(commands=['start'])
def send_welcome(message):
    """Send a welcome message when the bot is started"""
    welcome_text = (
        "Welcome to the Music Generation Bot! 🎵\n\n"
        "Use /generate to create music with a text prompt\n"
        "Use /about to learn more about the bot"
    )
    bot.reply_to(message, welcome_text)

@bot.message_handler(commands=['about'])
def send_about(message):
    """Provide information about the bot"""
    about_text = (
        "This Bot generates an audio file based on your prompt which will act as your submission. 🎧\n\n"
        "How to use:\n"
        "1. Use /generate command\n"
        "2. Provide a text prompt describing the music you want\n"
        "3. Receive a generated audio file\n"
        "4. Submit the audio or generate a new one"
    )
    bot.reply_to(message, about_text)

@bot.message_handler(commands=['generate'])
def initiate_generation(message):
    """Initiate music generation process"""
    bot.reply_to(message, "Please send me a text prompt describing the music you want to generate.")
    user_states[message.chat.id] = 'awaiting_prompt'

@bot.message_handler(func=lambda message: user_states.get(message.chat.id) == 'awaiting_prompt')
def generate_music(message):
    """Handle music generation requests"""
    # Send initial waiting message
    waiting_message = bot.reply_to(message, "Please wait till we perform magic (create your music audio file)...")

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

            # Send the audio file using Telegram Bot API POST request
            send_result = send_audio_via_telegram_api(
                bot_token=BOT_TOKEN,
                chat_id=message.chat.id,
                audio_file_path=audio_file_path
            )

            # Delete the waiting message
            bot.delete_message(message.chat.id, waiting_message.message_id)

            if send_result:
                # Store the audio file path for potential submission
                user_last_audio[message.chat.id] = audio_file_path

                # Ask for satisfaction with submit option
                satisfaction_markup = telebot.types.ReplyKeyboardMarkup(row_width=2)
                submit_button = telebot.types.KeyboardButton('Submit')
                no_button = telebot.types.KeyboardButton('No')
                satisfaction_markup.add(submit_button, no_button)

                bot.send_message(
                    message.chat.id,
                    "Do you want to submit this audio or generate a new one?",
                    reply_markup=satisfaction_markup
                )

                # Update user state
                user_states[message.chat.id] = 'awaiting_satisfaction'
            else:
                # Handle send audio failure
                bot.reply_to(message, "Failed to send the generated audio.")
                user_states[message.chat.id] = None

        else:
            # Handle API error
            error_message = f"Sorry, music generation failed. Status code: {response.status_code}"
            bot.reply_to(message, error_message)

            # Reset user state
            user_states[message.chat.id] = None

    except Exception as e:
        # Handle any unexpected errors
        error_message = f"An error occurred: {str(e)}"
        bot.reply_to(message, error_message)

        # Reset user state
        user_states[message.chat.id] = None

@bot.message_handler(func=lambda message: user_states.get(message.chat.id) == 'awaiting_satisfaction')
def handle_satisfaction(message):
    """Handle user satisfaction with generated music"""
    if message.text.lower() == 'submit':
        # Submit the audio to the specified chat
        if message.chat.id in user_last_audio:
            try:
                # Use Telegram API POST request to submit audio
                submit_result = send_audio_via_telegram_api(
                    bot_token=BOT_TOKEN,
                    chat_id=SUBMISSION_CHAT_ID,
                    audio_file_path=user_last_audio[message.chat.id]
                )

                if submit_result:
                    bot.send_message(
                        message.chat.id,
                        "Audio successfully submitted! 🎵",
                        reply_markup=telebot.types.ReplyKeyboardRemove()
                    )
                else:
                    bot.send_message(
                        message.chat.id,
                        "Submission failed.",
                        reply_markup=telebot.types.ReplyKeyboardRemove()
                    )

                # Clean up the audio file
                os.remove(user_last_audio[message.chat.id])
                del user_last_audio[message.chat.id]
            except Exception as e:
                bot.send_message(
                    message.chat.id,
                    f"Submission failed: {str(e)}",
                    reply_markup=telebot.types.ReplyKeyboardRemove()
                )

            # Reset user state
            user_states[message.chat.id] = None
        else:
            bot.send_message(
                message.chat.id,
                "No audio to submit. Please generate a new audio file first.",
                reply_markup=telebot.types.ReplyKeyboardRemove()
            )
    elif message.text.lower() == 'no':
        bot.send_message(
            message.chat.id,
            "No problem! Use /generate command again to create another music file.",
            reply_markup=telebot.types.ReplyKeyboardRemove()
        )
        # Clean up the last generated audio
        if message.chat.id in user_last_audio:
            os.remove(user_last_audio[message.chat.id])
            del user_last_audio[message.chat.id]

        # Reset user state
        user_states[message.chat.id] = None
    else:
        # If user doesn't select Submit or No
        bot.send_message(
            message.chat.id,
            "Please select 'Submit' or 'No'.",
            reply_markup=telebot.types.ReplyKeyboardRemove()
        )

@bot.message_handler(func=lambda message: True)
def handle_other_messages(message):
    """Handle messages that don't match any specific command"""
    bot.reply_to(message, "Please use /generate to create music or /about to learn more about the bot.")

def main():
    print("Bot is running...")
    bot.polling(none_stop=True)

if __name__ == '__main__':
    main()