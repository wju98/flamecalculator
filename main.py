import discord
import io
import os
from google.cloud import vision
from PIL import Image
import requests
import threading
from queue import Queue
import sqlite3
import config
import tier_calculator
import util
import numpy as np
import cv2

os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = config.file_path
google_client = vision.ImageAnnotatorClient()
discord_client = discord.Client()
conn = sqlite3.connect('users.db')


@discord_client.event
async def on_ready():
    c = conn.cursor()
    c.execute("CREATE TABLE IF NOT EXISTS users(discordid integer, secondary real, tertiary real, "
              "maxhp real, attack real, allstat real, PRIMARY KEY (discordid))")
    conn.commit()
    c.close()
    print('We have logged in as {0.user}'.format(discord_client))
    await discord_client.change_presence(activity=discord.Game(name='!flamehelp'))


"""
public commands:
!flamescore or !fs calculates the flame score of an equip and flame tier lines
!setratios or !flameratios or !ratios prints out the current flame ratios of the user.
!setsecondary, !settertiary, !setattack, !setallstat, !setmaxhp
!flamehelp lists out all commands that can be used
non public commands:
!debug same as !flamescore, but prints out extra information along the process of finding the flame score
!botstatistics command showing number of unique users and server count
"""

stats = ['STR', 'DEX', 'INT', 'LUK', 'MaxHP', 'MaxMP', 'Weapon Attack', 'Magic Attack', 'Defense', 'Speed', 'Jump',
         'All Stats']
check_stats = ['STR', 'TR', 'DEX', 'EX', 'INT', 'NT', 'LUK', 'UK', 'MAXHP', 'AXHP', 'MAXMP', 'AXMP', 'ATTACK', 'TTACK',
               'MAGIC', 'AGIC', 'DEFENSE', 'EFENSE', 'SPEED', 'PEED', 'JUMP', 'UMP', 'ALL', 'AL', 'AI']
flame_lines = ['STR', 'DEX', 'INT', 'LUK', 'STR+DEX', 'STR+INT', 'STR+LUK', 'DEX+INT', 'DEX+LUK', 'INT+LUK', 'MaxHP',
               'MaxMP', 'Attack', 'Magic Attack', 'Defense', 'Speed', 'Jump', 'All Stats', 'Item Level Reduction']
ignore_stats = ['BOSS', 'OSS', 'DAMAGE', 'AMAGE']


@discord_client.event
async def on_message(message):
    if message.author == discord_client.user:
        return

    if message.content.startswith('!flamescore') or message.content.startswith('!fs') \
            or message.content.startswith('!debug'):
        debug_mode = False
        if message.content.startswith('!debug'):
            debug_mode = True
        user_input = util.get_user_input_from_message(message.content)
        if not message.attachments and not user_input:
            await message.channel.send('No image was attached. To use this command, attach an image with the message' +
                                       ' or include the URL of the image.')
            return
        if message.attachments:
            imageURL = message.attachments[0].url
        else:
            imageURL = user_input

        try:
            im = Image.open(requests.get(imageURL, stream=True).raw)
        except Exception:
            await message.channel.send('Invalid URL')
            return

        # start processing the original image using cloud vision API on separate thread, slowest step of this command
        original = cv2.cvtColor(np.array(im), cv2.COLOR_RGB2BGR)
        cv2.imwrite('imagefromurl.png', original)
        queue_original = Queue()
        original_thread = threading.Thread(target=lambda q, arg1: q.put(get_text_from_image(arg1)),
                                           args=(queue_original, 'imagefromurl.png'))
        original_thread.start()

        # filter and crop image to only the flame numbers on image
        original = cv2.cvtColor(np.array(im), cv2.COLOR_RGB2HSV)
        height, width, _ = original.shape
        lower = np.array([33, 210, 75])
        upper = np.array([41, 255, 255])
        mask = cv2.inRange(original, lower, upper)
        res = cv2.bitwise_and(original, original, mask=mask)
        letterY, letterX = np.where(np.all(res != [0, 0, 0], axis=2))
        res = cv2.cvtColor(res, cv2.COLOR_HSV2BGR)
        try:
            top, bottom = max(np.amin(letterY) - 3, 0), min(np.amax(letterY) + 3, height)
            left, right = max(np.amin(letterX) - 3, 0), min(np.amax(letterX) + 3, width)
        except Exception:
            await message.channel.send('No flame was detected.')
            return

        filtered_cropped = res[top:bottom, left:right]
        cv2.imwrite('filteredcropped.png', filtered_cropped)
        if debug_mode:
            await message.channel.send(file=discord.File('filteredcropped.png'))

        result, valid = get_text_from_image('filteredcropped.png', True)

        # begin processing filtercropped image for its text
        if not valid:
            await message.channel.send(result)
            return
        if debug_mode:
            await message.channel.send(result.text_annotations[0].description)

        # min_y represents the smallest y value from the bounding box for each number. It can also be viewed as the
        # number of pixels from the top of the original image to the top of the number.
        min_y_to_number = {}
        for curr_line in result.text_annotations[1:]:
            curr_number = 0
            for char in curr_line.description:
                if char.isdigit():
                    curr_number *= 10
                    curr_number += int(char)
                if curr_number > 0 and not char.isdigit():
                    break

            if curr_number > 0:
                miny = util.min_y_from_vertices(curr_line.bounding_poly.vertices) + top
                min_y_to_number[miny] = curr_number

        if not min_y_to_number or not result.text_annotations:
            await message.channel.send('No flame was detected.')
            return

        if debug_mode:
            await message.channel.send(min_y_to_number)

        original_thread.join()
        original_text, original_valid = queue_original.get()

        # if error from the OCR, print out the error message from the API.
        if not original_valid:
            await message.channel.send(original_text)
            return

        list_of_min_y = min_y_to_number.keys()
        num_of_flame_values = len(list_of_min_y)
        min_target = min(list_of_min_y) - 5
        max_target = max(list_of_min_y) + 5
        curr_min_y = 0
        i = 0
        # traverse curr_min_y to where the first flame value appears in the original image
        while curr_min_y < min_target or curr_min_y > max_target:
            i += 1
            curr_min_y = original_text.text_annotations[i].bounding_poly.vertices[0].y

        stat_to_flame_value = {}
        # traverse through the remaining text in the original image to match the relevant stats to its flame values.
        while list_of_min_y and i < len(original_text.text_annotations):
            curr_stat = original_text.text_annotations[i].description.split(':')[0].upper()
            curr_min_y = util.min_y_from_vertices(original_text.text_annotations[i].bounding_poly.vertices)

            for offset in [0, -1, 1, -2, 2, -3, 3, -4, 4, -5, 5, -6, 6, -7, 7]:
                offset_y = curr_min_y + offset
                if offset_y in list_of_min_y:
                    if curr_stat in check_stats and curr_stat not in stat_to_flame_value.keys():
                        stat_to_flame_value[curr_stat] = min_y_to_number[offset_y]
                        del min_y_to_number[offset_y]
                    elif curr_stat[1:] in check_stats and curr_stat[1:] not in stat_to_flame_value.keys():
                        stat_to_flame_value[curr_stat[1:]] = min_y_to_number[offset_y]
                        del min_y_to_number[offset_y]
                    elif curr_stat in ignore_stats or curr_stat[1:] in ignore_stats:
                        num_of_flame_values -= 1
                        del min_y_to_number[offset_y]
            list_of_min_y = min_y_to_number.keys()
            i += 1

        if len(stat_to_flame_value.keys()) < num_of_flame_values:
            await message.channel.send('Mouse is covering the equip\'s stats.')
            return

        if debug_mode:
            await message.channel.send(str(stat_to_flame_value))

        # str, dex, int, luk, maxhp, maxmp, att, matt, def, speed, jump, all stat
        equip_stats = [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]
        for k in stat_to_flame_value.keys():
            value = stat_to_flame_value[k]
            if k in check_stats:
                index = min(check_stats.index(k) // 2, 11)
                equip_stats[index] += value
        if debug_mode:
            await message.channel.send(str(equip_stats))

        # get item level for flame tier calculation
        equip_stats.append(0)
        try:
            i = original_text.text_annotations[0].description.index('LEV')
            line_with_level_num = original_text.text_annotations[0].description[i:]
            i = line_with_level_num.index('\n')
            line_with_level_num = line_with_level_num[:i]
            level_numbers = util.get_values_from_line(line_with_level_num)
            level_number = level_numbers[0]
            if len(level_numbers) > 2 and (level_numbers[1] - level_numbers[0]) % 5 == 0 and 0 < (
                    level_numbers[1] - level_numbers[0]) < 40:
                level_number = level_numbers[1]
                equip_stats[12] = level_numbers[1] - level_numbers[0]

            if debug_mode:
                await message.channel.send('Item Level: ' + str(level_number))

            identified_flame = tier_calculator.analyze_flame(equip_stats, level_number)
            if debug_mode:
                await message.channel.send(identified_flame)

            if not identified_flame:
                flame_tiers_for_embed = 'Unable to determine flame tier. Did not read item level or flame correctly.'
            else:
                flame_tiers_for_embed = ''
                for i in range(19):
                    if identified_flame[i] != 0:
                        flame_tiers_for_embed += 'T' + str(identified_flame[i]) + ' ' + flame_lines[i] + ', '
                flame_tiers_for_embed = flame_tiers_for_embed[:-2]
        except Exception:
            flame_tiers_for_embed = 'Unable to detect level of item.'
        equip_stats_for_embed = ''
        percent = False
        for i in range(12):
            value = equip_stats[i]
            if value > 0:
                equip_stats_for_embed += stats[i] + ': ' + str(value) + ', '
                if i == 11:
                    percent = True
        equip_stats_for_embed = equip_stats_for_embed[:-2]
        if percent:
            equip_stats_for_embed += '%'
        if equip_stats[12] > 0:
            equip_stats_for_embed += ', ' + 'Item Level Reduction: -' + str(equip_stats[12])

        flame_score = [0, 0, 0, 0]  # str, dex, int, luk
        curr_user = get_stored_ratios_from_username(message.author)
        flame_score[0] = equip_stats[0] + (equip_stats[1] * curr_user[1]) + (equip_stats[6] * curr_user[4]) + (
                equip_stats[11] * curr_user[5])
        flame_score[1] = equip_stats[1] + (equip_stats[0] * curr_user[1]) + (equip_stats[6] * curr_user[4]) + (
                equip_stats[11] * curr_user[5])
        flame_score[2] = equip_stats[2] + (equip_stats[3] * curr_user[1]) + (equip_stats[7] * curr_user[4]) + (
                equip_stats[11] * curr_user[5]) + ((equip_stats[4] + equip_stats[5]) * curr_user[3] / 1000)
        flame_score[3] = equip_stats[3] + (equip_stats[1] * curr_user[1]) + (equip_stats[6] * curr_user[4]) + (
                equip_stats[11] * curr_user[5]) + (equip_stats[0] * curr_user[2])
        flame_score_for_embed = str(round(max(flame_score), 2)) + ' ' + stats[flame_score.index(max(flame_score))]

        embed = discord.Embed()
        embed.add_field(name="Flame Stats", value=equip_stats_for_embed, inline=False)
        embed.add_field(name="Flame Tiers", value=flame_tiers_for_embed, inline=False)
        embed.add_field(name="Flame Score", value=flame_score_for_embed, inline=False)
        await message.channel.send(embed=embed)
        return

    if message.content.startswith('!flamehelp'):
        embed = discord.Embed(title="Available Commands")
        embed.add_field(name="!flamescore or !fs", value="Calculates the flame score of an item. An image of the item"
                                                         " must be attached to the message or the URL of the image must"
                                                         " be sent with the message.", inline=False)
        embed.add_field(name="!ratios or !setratios", value="Shows the user\'s flame ratios that are used when"
                                                            " calculating an item\'s flame score.", inline=False)
        embed.add_field(name="!setsecondary", value="Changes the user\'s secondary ratio. The value specified should"
                                                    " represent how much 1 secondary stat is worth in terms of main"
                                                    " stat.", inline=False)
        embed.add_field(name="!settertiary", value="Changes the user\'s tertiary ratio. The value specified should "
                                                   "represent how much 1 tertiary stat is worth in terms of main "
                                                   "stat.", inline=False)
        embed.add_field(name="!setmaxhp", value="Changes the user\'s maxHP ratio. The value specified should "
                                                "represent how much 1000 maxHP is worth in terms of main stat.",
                        inline=False)
        embed.add_field(name="!setattack", value="Changes the user\'s attack ratio. The value specified should "
                                                 "represent how much 1 attack is worth in terms of main stat.",
                        inline=False)
        embed.add_field(name="!setallstat", value="Changes the user\'s all stat ratio. The value specified should "
                                                  "represent how much 1% all stat is worth in terms of main stat.",
                        inline=False)
        await message.channel.send(embed=embed)
        return

    if message.content.startswith('!botstatistics'):
        if message.author.id != config.owner:
            return
        c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM users")
        number_of_users = c.fetchone()[0]
        c.close()
        bot_stats = 'Number of Users: ' + str(number_of_users) + '\n' + 'Server Count: ' + str(
            len(discord_client.guilds))
        await message.channel.send(bot_stats)
        active_servers = discord_client.guilds
        for guild in active_servers:
            print(guild.name)
        return

    if message.content.startswith('!flameratio') or message.content.startswith('!setratio') \
            or message.content.startswith('!ratio'):
        embed = get_embed_ratio_of_user(message.author)
        await message.channel.send(embed=embed)
        return

    if message.content.startswith('!setsecondary'):
        return_message = set_specified_ratio(' secondary stat', message)
        if isinstance(return_message, str):
            await message.channel.send(return_message)
        else:
            await message.channel.send(embed=return_message)
        return

    if message.content.startswith('!settertiary'):
        return_message = set_specified_ratio(' tertiary stat', message)
        if isinstance(return_message, str):
            await message.channel.send(return_message)
        else:
            await message.channel.send(embed=return_message)
        return

    if message.content.startswith('!setmaxhp'):
        return_message = set_specified_ratio(' maxhp', message)
        if isinstance(return_message, str):
            await message.channel.send(return_message)
        else:
            await message.channel.send(embed=return_message)
        return

    if message.content.startswith('!setattack'):
        return_message = set_specified_ratio(' attack', message)
        if isinstance(return_message, str):
            await message.channel.send(return_message)
        else:
            await message.channel.send(embed=return_message)
        return

    if message.content.startswith('!setallstat'):
        return_message = set_specified_ratio('% all stat', message)
        if isinstance(return_message, str):
            await message.channel.send(return_message)
        else:
            await message.channel.send(embed=return_message)
        return


def get_text_from_image(file_name, number=False):
    """
    Given the path to a file and uses Google Cloud Vision API to translate the image into text. Returns the JSON object
    and a boolean describing whether the OCR was successful or not.

    :param file_name: A string that represents the path and filename of the image.
    :param number: True if the OCR wants to prioritize numbers over characters.
    :return: JSON object of the result and a boolean representing if the OCR was successful.
    """
    file_name = os.path.abspath(file_name)

    with io.open(file_name, 'rb') as image_file:
        content = image_file.read()

    gear_image = vision.Image(content=content)
    # apparently, some people experimented on stackoverflow claiming Chinese/Korean works better for reading numbers
    # than English. Kinda makes sense I guess because "O" and "0", "1" and "l" look very similar.
    if number:
        response = google_client.text_detection(image=gear_image, image_context={"language_hints": ["zh"]}, )
    else:
        response = google_client.document_text_detection(image=gear_image)
    if len(response.error.message) > 0:
        return response.error.message, False

    return response, True


def get_embed_ratio_of_user(discord_user, title='Flame Ratios'):
    """
    Creates a discord embed message of the user's ratios.

    :param discord_user: Discord user object, usually from message.author.
    :param title: Optional String to change the title on the embed message.
    :return: Discord Embed message with the user's ratios.
    """
    curr_user = get_stored_ratios_from_username(discord_user)
    embed = discord.Embed(title=discord_user.display_name + '\'s ' + title)
    embed.add_field(name="Secondary Ratio", value=str(curr_user[1]), inline=False)
    embed.add_field(name="Tertiary Ratio", value=str(curr_user[2]), inline=False)
    embed.add_field(name="MaxHP Ratio", value=str(curr_user[3]), inline=False)
    embed.add_field(name="Attack Ratio", value=str(curr_user[4]), inline=False)
    embed.add_field(name="All Stat Ratio", value=str(curr_user[5]), inline=False)
    embed.set_footer(text="The following commands can be used to change the ratios: !setsecondary, !settertiary," +
                          " !setmaxhp, !setattack, !setallstat")
    return embed


def set_specified_ratio(ratio_type, message):
    """
    Sets the ratio specified by the message. Changes the ratio of the user that sent the message to the value that
    is specified in the message.

    :param ratio_type: String specifying which ratio is being set.
    :param message: Discord Message object that was sent.
    :return: Embed message that describes what changed and the user's ratios.
    """
    current_user = get_stored_ratios_from_username(message.author)
    user_input = util.get_user_input_from_message(message.content)
    if not user_input:
        if ratio_type == ' maxhp':
            return 'For Kanna only: Specify a value for how much 1000 maxHP is equivalent to INT.'
        return 'Specify a value for how much 1' + ratio_type + ' is equivalent to your main stat.'

    number_check = user_input.replace('.', '1')
    if not number_check.isdigit():
        if ratio_type == 'maxhp':
            return 'For Kanna only: Specify a value for how much 1000 maxHP is equivalent to INT.'
        return 'Specify a value for how much 1' + ratio_type + ' is equivalent to your main stat.'

    if ratio_type == ' secondary stat':
        sql = "UPDATE users SET secondary = ? where discordid = ?"
        ratio_type = 'Secondary'

    if ratio_type == ' tertiary stat':
        sql = "UPDATE users SET tertiary = ? where discordid = ?"
        ratio_type = 'Tertiary'

    if ratio_type == ' maxhp':
        sql = "UPDATE users SET maxhp = ? where discordid = ?"
        ratio_type = 'MaxHP'

    if ratio_type == ' attack':
        sql = "UPDATE users SET attack = ? where discordid = ?"
        ratio_type = 'Attack'

    if ratio_type == '% all stat':
        sql = "UPDATE users SET allstat = ? where discordid = ?"
        ratio_type = 'All Stat'

    c = conn.cursor()
    val = (float(user_input), current_user[0])
    c.execute(sql, val)
    conn.commit()
    c.close()
    title = ratio_type + ' Ratio has been updated'
    return get_embed_ratio_of_user(message.author, title)


def get_stored_ratios_from_username(discord_user):
    """
    Gets the user's ratios when given the user object. If user is not in the database, an entry will be created with
    default ratio values and those values will be returned instead.

    :param discord_user: Discord User object, usually should be message.author
    :return: The user's ratios as a list in the following format: [discord id, secondary, tertiary, maxhp, attack,
        all stat].
    """
    c = conn.cursor()
    c.execute(f"SELECT * FROM users WHERE discordid = {discord_user.id}")
    result = c.fetchone()
    if result is None:
        sql = "INSERT INTO users(discordid, secondary, tertiary, maxhp, attack, allstat) VALUES(?, ?, ?, ?, ?, ?)"
        val = (discord_user.id, 0.12, 0, 0, 3, 8)
        c.execute(sql, val)
        conn.commit()
        c.close()
        return get_stored_ratios_from_username(discord_user)
    c.close()
    return result


discord_client.run(config.TOKEN)
