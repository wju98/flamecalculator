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
import time
import numpy as np
import cv2

os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = r'equipstatreaderkey.json'
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
    await discord_client.change_presence(activity=discord.Game(name='!flamehelp | always in beta'))


"""
public commands:
!flamescore or !fs calculates the flame score of an equip and flame tier lines
!setratios or !flameratios or !ratios prints out the current flame ratios of the user.
!setsecondary, !settertiary, !setattack, !setallstat, !setmaxhp
!flamehelp lists out all commands that can be used
non public commands:
!debug same as !flamescore, but prints out extra information along the process of finding the flame score
!botstatistics command showing number of unique users and server count
!translate takes an image and spits out the text, for debugging purpose, but its also kinda cool to showoff to others
"""

stats = ['STR', 'DEX', 'INT', 'LUK', 'MaxHP', 'MaxMP', 'Weapon Attack', 'Magic Attack', 'Defense', 'Speed', 'Jump',
         'All Stats']
check_stats = ['STR', 'TR', 'DEX', 'EX', 'INT', 'NT', 'LUK', 'UK', 'MAXHP', 'AXHP', 'MAXMP', 'AXMP', 'ATTACK', 'TTACK',
              'MAGIC', 'AGIC', 'DEFENSE', 'EFENSE', 'SPEED', 'PEED', 'JUMP', 'UMP', 'ALL', 'AL', 'AI']
flame_lines = ['STR', 'DEX', 'INT', 'LUK', 'STR+DEX', 'STR+INT', 'STR+LUK', 'DEX+INT', 'DEX+LUK', 'INT+LUK', 'MaxHP',
              'MaxMP', 'Attack', 'Magic Attack', 'Defense', 'Speed', 'Jump', 'All Stats']
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
        userinput = getUserInputFromCommand(message.content)
        if not message.attachments and not userinput:
            await message.channel.send('No image was attached. To use this command, attach an image with the message' +
                                       ' or include the URL of the image.')
            return
        if message.attachments:
            imageURL = message.attachments[0].url
        else:
            imageURL = userinput

        # if imageURL[-4:] != '.png' and imageURL[-5:] != '.jpeg':
        #     imageURL = imageURL + ".png"

        try:
            im = Image.open(requests.get(imageURL, stream=True).raw)
        except:
            await message.channel.send('Invalid URL')
            return

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

        queoriginal = Queue()
        originalthread = threading.Thread(target=lambda q, arg1: q.put(getTextFromUrlForThread(arg1)),
                                          args=(queoriginal, (message, True)))
        originalthread.start()

        filteredcropped = res[top:bottom, left:right]
        cv2.imwrite('filteredcropped.png', filteredcropped)
        if debug_mode:
            await message.channel.send(file=discord.File('filteredcropped.png'))

        result, valid = getNumberFromImage('filteredcropped.png')

        if not valid:
            await message.channel.send(result)
            return
        if debug_mode:
            totaltext = result.text_annotations[0].description
            await message.channel.send(totaltext)

        minytonumber = {}
        for currline in result.text_annotations[1:]:
            currnumber = getSingleValueFromLine(currline.description)
            if currnumber > 0:
                miny = minyfromvertices(currline.bounding_poly.vertices) + top
                minytonumber[miny] = currnumber

        if not minytonumber or not result.text_annotations:
            await message.channel.send('No flame was detected.')
            return

        if debug_mode:
            await message.channel.send(minytonumber)

        originalthread.join()
        originaltext, originalvalid = queoriginal.get()

        if not originalvalid:
            await message.channel.send(originaltext)
            return

        minys = minytonumber.keys()
        numberofflamevalues = len(minys)
        target = min(minys) - 5
        currminy = 0
        i = 0
        while currminy < target:
            i += 1
            currminy = originaltext.text_annotations[i].bounding_poly.vertices[0].y

        stattoflamevalue = {}
        target = max(minys) + 5
        while minys and currminy < target and i < len(originaltext.text_annotations):
            currstat = originaltext.text_annotations[i].description.split(':')[0].upper()
            currminy = minyfromvertices(originaltext.text_annotations[i].bounding_poly.vertices)

            for offset in [0, -1, 1, -2, 2, -3, 3, -4, 4, -5, 5]:
                offsety = currminy + offset
                if offsety in minys:
                    if currstat in check_stats and currstat not in stattoflamevalue.keys():
                        stattoflamevalue[currstat] = minytonumber[offsety]
                        del minytonumber[offsety]
                    elif currstat[1:] in check_stats and currstat[1:] not in stattoflamevalue.keys():
                        stattoflamevalue[currstat[1:]] = minytonumber[offsety]
                        del minytonumber[offsety]
                    elif currstat in ignore_stats or currstat[1:] in ignore_stats:
                        numberofflamevalues -= 1
                        del minytonumber[offsety]
            minys = minytonumber.keys()
            i += 1

        if len(stattoflamevalue.keys()) < numberofflamevalues:
            await message.channel.send('Mouse is covering the equip\'s stats.')
            return

        if debug_mode:
            await message.channel.send(str(stattoflamevalue))

        # str, dex, int, luk, maxhp, maxmp, att, matt, def, speed, jump, allstat
        equipstats = [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]
        for k in stattoflamevalue.keys():
            value = stattoflamevalue[k]
            if k in check_stats:
                index = min(check_stats.index(k) // 2, 11)
                equipstats[index] += value
        if debug_mode:
            await message.channel.send(str(equipstats))

        try:
            i = originaltext.text_annotations[0].description.index('LEV')
            levelline = originaltext.text_annotations[0].description[i:]
            i = levelline.index('\n')
            levelline = levelline[:i]
            levelnumbers = getMultiValuesFromLine(levelline)
            if len(levelnumbers) > 2 and (levelnumbers[1] - levelnumbers[0]) % 5 == 0 and 0 < (levelnumbers[1] - levelnumbers[0]) < 40:
                levelnumber = levelnumbers[1]
            else:
                levelnumber = levelnumbers[0]
            if debug_mode:
                await message.channel.send('Item Level: ' + str(levelnumber))

            identifiedflame = tier_calculator.analyze_flame(equipstats, levelnumber)
            if debug_mode:
                await message.channel.send(identifiedflame)

            if not identifiedflame:
                flametierreadable = 'Unable to determine flame tier. Did not read item level or flame correctly.'
            else:
                flametierreadable = ''
                for i in range(18):
                    if identifiedflame[i] != 0:
                        flametierreadable += 'T' + str(identifiedflame[i]) + ' ' + flame_lines[i] + ', '
                flametierreadable = flametierreadable[:-2]
        except Exception:
            flametierreadable = 'Unable to detect level of item.'
        equipstatsreadable = ''
        percent = False
        for i in range(12):
            value = equipstats[i]
            if value > 0:
                equipstatsreadable += stats[i] + ': ' + str(value) + ', '
                if i == 11:
                    percent = True
        equipstatsreadable = equipstatsreadable[:-2]
        if percent:
            equipstatsreadable += '%'

        flamescore = [0, 0, 0, 0]  # str, dex, int, luk
        curruser = getCurrentUserFromUsername(message.author)
        flamescore[0] = equipstats[0] + (equipstats[1] * curruser[1]) + (equipstats[6] * curruser[4]) + (
                equipstats[11] * curruser[5])
        flamescore[1] = equipstats[1] + (equipstats[0] * curruser[1]) + (equipstats[6] * curruser[4]) + (
                equipstats[11] * curruser[5])
        flamescore[2] = equipstats[2] + (equipstats[3] * curruser[1]) + (equipstats[7] * curruser[4]) + (
                equipstats[11] * curruser[5]) + ((equipstats[4] + equipstats[5]) * curruser[3] / 1000)
        flamescore[3] = equipstats[3] + (equipstats[1] * curruser[1]) + (equipstats[6] * curruser[4]) + (
                equipstats[11] * curruser[5]) + (equipstats[0] * curruser[2])
        flamescorereadable = str(round(max(flamescore), 2)) + ' ' + stats[flamescore.index(max(flamescore))]

        embed = discord.Embed()
        embed.add_field(name="Flame Stats", value=equipstatsreadable, inline=False)
        embed.add_field(name="Flame Tiers", value=flametierreadable, inline=False)
        embed.add_field(name="Flame Score", value=flamescorereadable, inline=False)
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
        embed.add_field(name="!settertiary", value="Changes the user\'s tertiary ratio. The value specified should"
                                                   " represent how much 1 tertiary stat is worth in terms of main stat."
                        , inline=False)
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
        if message.author.id != 258064566456549387:
            return
        c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM users")
        numberofusers = c.fetchone()[0]
        c.close()
        botstats = 'Number of Users: ' + str(numberofusers) + '\n' \
                                                              'Server Count: ' + str(len(discord_client.guilds))
        await message.channel.send(botstats)
        activeservers = discord_client.guilds
        for guild in activeservers:
            print(guild.name)
        return

    if message.content.startswith('!translate'):
        starttime = time.time()
        texts, validurl = getTextFromURL(message)
        print('this function took ' + str(time.time() - starttime) + ' seconds to run.')
        if not validurl:
            await message.channel.send(texts)
            return
        await message.channel.send("```\n" + str(texts) + "```")
        return

    if message.content.startswith('!flameratio') or message.content.startswith('!setratio') or message.content.startswith(
            '!ratio'):
        embed = getEmbedRatioFromUser(message.author)
        await message.channel.send(embed=embed)
        return

    if message.content.startswith('!setsecondary'):
        returnmessage = setSpecifiedRatio(' secondary stat', message)
        if isinstance(returnmessage, str):
            await message.channel.send(returnmessage)
        else:
            await message.channel.send(embed=returnmessage)
        return

    if message.content.startswith('!settertiary'):
        returnmessage = setSpecifiedRatio(' tertiary stat', message)
        if isinstance(returnmessage, str):
            await message.channel.send(returnmessage)
        else:
            await message.channel.send(embed=returnmessage)
        return

    if message.content.startswith('!setmaxhp'):
        returnmessage = setSpecifiedRatio(' maxhp', message)
        if isinstance(returnmessage, str):
            await message.channel.send(returnmessage)
        else:
            await message.channel.send(embed=returnmessage)
        return

    if message.content.startswith('!setattack'):
        returnmessage = setSpecifiedRatio(' attack', message)
        if isinstance(returnmessage, str):
            await message.channel.send(returnmessage)
        else:
            await message.channel.send(embed=returnmessage)
        return

    if message.content.startswith('!setallstat'):
        returnmessage = setSpecifiedRatio('% all stat', message)
        if isinstance(returnmessage, str):
            await message.channel.send(returnmessage)
        else:
            await message.channel.send(embed=returnmessage)
        return


def getTextFromURL(message, bounds=False):
    userinput = getUserInputFromCommand(message.content)
    if not message.attachments and not userinput:
        return 'No image was attached', False
    if message.attachments:
        imageURL = message.attachments[0].url
    else:
        imageURL = userinput

    im = Image.open(requests.get(imageURL, stream=True).raw)
    original = cv2.cvtColor(np.array(im), cv2.COLOR_RGB2BGR)
    cv2.imwrite('imagefromurl.png', original)
    file_name = os.path.abspath('imagefromurl.png')
    with io.open(file_name, 'rb') as image_file:
        content = image_file.read()

    gearimage = vision.Image(content=content)
    response = google_client.text_detection(image=gearimage, image_context={"language_hints": ["en"]}, )
    if len(response.error.message) > 0:
        return response.error.message, False
    if bounds:
        return response, True
    return response.text_annotations[0].description, True


def getTextFromUrlForThread(msgandlen):
    return getTextFromURL(msgandlen[0], msgandlen[1])


def getTextFromImage(filename, number=False):
    if '' == None:
        return 'No image was attached', False
    file_name = os.path.abspath(filename)

    with io.open(file_name, 'rb') as image_file:
        content = image_file.read()

    gearimage = vision.Image(content=content)
    language = "en"
    # apparently, some people experimented on stackoverflow claiming Chinese/Korean works better for reading numbers
    # than English. Kinda makes sense I guess because "O" and "0", "1" and "l" look very similar.
    if number:
        language = "zh"
    response = google_client.text_detection(image=gearimage, image_context={"language_hints": [language]}, )
    if len(response.error.message) > 0:
        return response.error.message, False

    return response, True


def getNumberFromImage(filename):
    return getTextFromImage(filename, True)


def getSingleValueFromLine(line):
    value = 0
    for char in line:
        if char.isdigit():
            value *= 10
            value += int(char)
        if value > 0 and not char.isdigit():
            break

    return value


def getMultiValuesFromLine(line):
    value = 0
    listtostore = []
    for i in range(len(line)):
        if line[i].isdigit():
            value *= 10
            value += int(line[i])
        if line[i] == 'l':
            value *= 10
            value += 1
        if line[i] == 'o' or line[i] == 'O':
            value *= 10
        if line[i] == 's' or line[i] == 'S':
            value *= 10
            value += 5
        if value and ((not line[i].isdigit() and (
                line[i] != 'l' or line[i] != 'o' or line[i] != 'O' or line[i] != 's' or line[
            i] != 'S')) or i + 1 == len(line)):
            listtostore.append(threedigitslong(value))
            value = 0
    return listtostore


def threedigitslong(number):
    if number > 999:
        return threedigitslong(number // 10)
    return number

def minyfromvertices(vertices):
    miny = vertices[0].y
    for i in range(1, 4):
        miny = min(miny, vertices[i].y)
    return miny


# gets the current user from the username, if username doesn't exist then create a new user using that username
# parameter: username of the user
# return: user
def getCurrentUserFromUsername(discorduser):
    c = conn.cursor()
    c.execute(f"SELECT * FROM users WHERE discordid = {discorduser.id}")
    result = c.fetchone()
    if result is None:
        sql = ("INSERT INTO users(discordid, secondary, tertiary, maxhp, attack, allstat) VALUES(?, ?, ?, ?, ?, ?)")
        val = (discorduser.id, 0.12, 0, 0, 3, 8)
        c.execute(sql, val)
        conn.commit()
        c.close()
        return getCurrentUserFromUsername(discorduser)
    c.close()
    return result


# sets the specified ratio of a user's flame ratios
# parameter: type of ratio to be set, message
# return: message that describes the outcome of this method
def setSpecifiedRatio(ratiotype, message):
    currentuser = getCurrentUserFromUsername(message.author)
    userinput = getUserInputFromCommand(message.content)
    if not userinput:
        if ratiotype == ' maxhp':
            return 'For Kanna only: Specify a value for how much 1000 maxHP is equivalent to INT.'
        return 'Specify a value for how much 1' + ratiotype + ' is equivalent to your main stat.'

    testvalue = userinput.replace('.', '1')
    if not testvalue.isdigit():
        if ratiotype == 'maxhp':
            return 'For Kanna only: Specify a value for how much 1000 maxHP is equivalent to INT.'
        return 'Specify a value for how much 1' + ratiotype + ' is equivalent to your main stat.'

    if ratiotype == ' secondary stat':
        sql = ("UPDATE users SET secondary = ? where discordid = ?")
        ratiotype = 'Secondary'

    if ratiotype == ' tertiary stat':
        sql = ("UPDATE users SET tertiary = ? where discordid = ?")
        ratiotype = 'Tertiary'

    if ratiotype == ' maxhp':
        sql = ("UPDATE users SET maxhp = ? where discordid = ?")
        ratiotype = 'MaxHP'

    if ratiotype == ' attack':
        sql = ("UPDATE users SET attack = ? where discordid = ?")
        ratiotype = 'Attack'

    if ratiotype == '% all stat':
        sql = ("UPDATE users SET allstat = ? where discordid = ?")
        ratiotype = 'All Stat'

    c = conn.cursor()
    val = (float(userinput), currentuser[0])
    c.execute(sql, val)
    conn.commit()
    c.close()
    title = ratiotype + ' Ratio has been updated'
    embed = getEmbedRatioFromUser(message.author, title)
    return embed


def getEmbedRatioFromUser(discorduser, title='Flame Ratios'):
    curruser = getCurrentUserFromUsername(discorduser)
    embed = discord.Embed(title=discorduser.display_name + '\'s ' + title)
    embed.add_field(name="Secondary Ratio", value=str(curruser[1]), inline=False)
    embed.add_field(name="Tertiary Ratio", value=str(curruser[2]), inline=False)
    embed.add_field(name="MaxHP Ratio", value=str(curruser[3]), inline=False)
    embed.add_field(name="Attack Ratio", value=str(curruser[4]), inline=False)
    embed.add_field(name="All Stat Ratio", value=str(curruser[5]), inline=False)
    embed.set_footer(text="The following commands can be used to change the ratios: !setsecondary, !settertiary," + \
                          " !setmaxhp, !setattack, !setallstat")
    return embed


# gets the custom user value the user inputs when using a command. if no value exists, will return an empty string
# parameter: message.content, the actual string of whatever the user typed
# return: everything after the space that separates the command from the user parameter
def getUserInputFromCommand(message):
    result = message.split()
    if len(result) < 2:
        return ''
    else:
        return result[1]


discord_client.run(config.TOKEN)
