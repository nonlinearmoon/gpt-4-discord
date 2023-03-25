import utils
import discord
from discord.ext import commands

with open("discord-token.txt", "r") as f:
    DISCORD_TOKEN = f.read().strip()

intents = discord.Intents.default()
intents.typing = False
intents.presences = False
bot = commands.Bot(command_prefix='!', intents=intents)

MAX_MESSAGE_LENGTH = 2000

from public_modes import SYSTEM_MESSAGES_PUBLIC
try:
    from root_modes import SYSTEM_MESSAGES_ROOT_OBFUSCATE, SYSTEM_MESSAGES_ROOT_NORMAL
except:
    SYSTEM_MESSAGES_ROOT_OBFUSCATE = {}
    SYSTEM_MESSAGES_ROOT_NORMAL = {}

SYSTEM_MESSAGES = {**SYSTEM_MESSAGES_PUBLIC, **SYSTEM_MESSAGES_ROOT_OBFUSCATE, **SYSTEM_MESSAGES_ROOT_NORMAL}

@bot.event
async def on_message(message):
    if message.author == bot.user:
        return

    if message.guild.name == "Cyborgism" and message.channel.name != "prompt-libraries":
        return

    if bot.user in message.mentions:
        print("Request received!")
        utils.log_request(message)
        input_content = message.content.replace(f'<@{bot.user.id}>', '').strip()
        
        if input_content.startswith("/help"):
            await utils.handle_help(message, MAX_MESSAGE_LENGTH)
            return

        if(isinstance(message.channel, discord.channel.Thread)):
            await message.add_reaction('\N{HOURGLASS}')
            thread = message.channel
        else:
            try:
                thread = await message.create_thread(name=input_content, auto_archive_duration=60)
            except Exception as e:
                print(repr(e))
                await message.channel.send("Oops, something went wrong when I was crafting a thread. Check my logs!")
                return

        MAX_TOKENS = 1028
        if message.author.name == "Jozdien":
            MAX_TOKENS = 6000

        if message.attachments:
            for attachment in message.attachments:
                # Check if attachment is a text file
                if attachment.filename.endswith('.txt'):
                    file_content = await attachment.read()
                    decoded_content = file_content.decode('utf-8')
                    # Character limit for text file input
                    if len(decoded_content) < 30000:
                        input_content = f"{input_content}\n\n{decoded_content}"
                        # Rough estimate of limit of output tokens to not go over the limit
                        MAX_TOKENS = 8000 - len(decoded_content) // 4
                    else:
                        await thread.send("Sorry, the text file you attached is too long. Please send a file under 20,000 characters.")
                        await message.remove_reaction('\N{HOURGLASS}', bot.user)
                        await thread.edit(locked=True, archived=True)
                        return
                # If attachment is an image, if we have multimodal GPT-4
                else:
                    image_bytes = await attachment.read()
                    input_content.append({"image": image_bytes})

        keyword, user_msg = utils.parse_input_content(input_content, SYSTEM_MESSAGES)

        messages = []
        if keyword:
            messages.append({"role": "system", "content": SYSTEM_MESSAGES[keyword]})
        if keyword == "/lw":
            user_msg = utils.process_lw(user_msg)
            if user_msg == -1:
                await thread.send("Please give me a link to summarize, I cannot read your messages otherwise :(")
                await message.remove_reaction('\N{HOURGLASS}', bot.user)
                await thread.edit(locked=True, archived=True)
                return
            elif user_msg == -2:
                await thread.send("Sorry, the web parser failed, please try again!")
                await message.remove_reaction('\N{HOURGLASS}', bot.user)
                await thread.edit(locked=True, archived=True)
                return
            MAX_TOKENS = 8000 - len(user_msg) // 4

        messages.append({"role": "user", "content": user_msg})

        try:
            completion = utils.create_response(messages, MAX_TOKENS)
        except Exception as e:
            # No multimodal access to GPT-4
            if repr(e) == "TypeError('Object of type bytes is not JSON serializable')":
                await thread.send("Sorry, you don't have multimodal access with me yet.")
                await message.remove_reaction('\N{HOURGLASS}', bot.user)
                await thread.edit(locked=True, archived=True)
                return
            # Rate limiting
            if repr(e) == "RateLimitError(message='The server had an error while processing your request. Sorry about that!', http_status=429, request_id=None)":
                await thread.send("Sorry, you're sending a lot of requests, I need to cool down. Please resend your request after a few seconds!")
                await message.remove_reaction('\N{HOURGLASS}', bot.user)
                await thread.edit(locked=True, archived=True)
                return
            print(repr(e))
            await thread.send("An error has occurred, please check my logs!")
            await message.remove_reaction('\N{HOURGLASS}', bot.user)
            await thread.edit(locked=True, archived=True)
            return

        response = completion.choices[0].message.content

        utils.log(message, messages, response, completion)

        if keyword == "/timestamp":
            await message.channel.send(f"<t:{utils.convert_to_unix(response)}:t>")
            await message.remove_reaction('\N{HOURGLASS}', bot.user)
            await thread.delete()
            return
        if keyword in ["/no-filter", "/no-filter-hard", "/no-filter-conv", "/no-filter-role"] or keyword in SYSTEM_MESSAGES_ROOT_OBFUSCATE:
            response = utils.de_obfuscate(keyword, response)
            if response == -1:
                await thread.send("An error occurred while de-obfuscating the text, please check my logs!")
                await message.remove_reaction('\N{HOURGLASS}', bot.user)
                await thread.edit(locked=True, archived=True)
                return

        for i in range(0, len(response), MAX_MESSAGE_LENGTH):
            await thread.send(response[i:i + MAX_MESSAGE_LENGTH])
        
        await message.remove_reaction('\N{HOURGLASS}', bot.user)
        await thread.edit(archived=True)

bot.run(DISCORD_TOKEN)