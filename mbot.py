#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
MetrixBot for Telegram
A Telegram bot for blood pressure and pulse metrix.
by Eugene Kolonsky ekolonsky@gmail.com 2018

"""
from datetime import datetime
import configparser, codecs
import requests

# get configuration data from .ini file
config = configparser.ConfigParser()
def read_ini(filename):
   config.readfp(codecs.open(filename, encoding='cp1251'))

read_ini("mbot.ini")

TOKEN = config["TELEGRAM"]["TOKEN"]
print('Token: ', TOKEN)


HOST = config["INFLUX"]["HOST"]
DATABASE = config["INFLUX"]["DATABASE"]
USER = config["INFLUX"]["USER"]
PASSWORD = config["INFLUX"]["PASSWORD"]

MAX_BP    = int(config['LIMITS']['MAX_BP'])  # blood pressure figures over max are incorrect
MIN_BP    = int(config['LIMITS']['MIN_BP']) # figures lower min are incorrect
MAX_PULSE = int(config['LIMITS']['MAX_PULSE'])  # pulse figures over max are incorrect
MIN_PULSE = int(config['LIMITS']['MIN_PULSE'])  # pulse pressure figures over max are incorrect

import logging

from telegram import (ReplyKeyboardMarkup, ReplyKeyboardRemove, ParseMode)
from telegram.ext import (Updater, CommandHandler, MessageHandler, Filters, RegexHandler,
                          ConversationHandler)

from influxdb import InfluxDBClient

# Enable logging
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                    level=logging.INFO)

logger = logging.getLogger(__name__)

updater = Updater(token=TOKEN)
dispatcher = updater.dispatcher

client = InfluxDBClient(host=HOST, port=8086, ssl=True,
                        database=DATABASE, 
                        username=USER, 
                        password=PASSWORD)
try:
   client.query('SHOW MEASUREMENTS')
   print('Connected successfully to ', HOST)
except:
  print('No connection to  ', HOST)

# user action log
def store_user_action(user, message, content_type="talk"):
        json = [{"measurement": "talk",
                     "tags":   {
                               "user_id": user.id,
                               "content_type": content_type,
                               "channel_type": "telegram"
                               },
                     "fields": {
                               "message": message,
                               "username": user.first_name+' '+user.last_name,
                               }
               }]
        client.write_points(json)


# when session starts
def start(bot, update):
    chat_id = update.message.chat_id
    user= update.message.from_user
    store_user_action(user, '/start', 'command') # for later analysis

    read_ini("bot.ini") # read again to get actual data
    query = config['INFLUX']['SELECT_ALL_QUERY'].format(user.id)
    rs = client.query(query)
    num = len(list(rs.get_points()))
    if num > 0: # returning user
        reply = config['DIALOG']['Welcome returning'].format(num)
    else:             # new user
        reply = config['DIALOG']['Welcome first'].format(user.first_name)
    print('Welcome: ', reply)
    bot.send_message(chat_id=chat_id, text=reply)

# help command action
def helpme(bot, update):
    chat_id = update.message.chat_id
    user= update.message.from_user
    store_user_action(user, '/help', 'command') # for later analysis
    reply = config['DIALOG']['Help']
    bot.send_message(chat_id=chat_id, text=reply,
                         parse_mode=ParseMode.MARKDOWN)

# save command action
def save(bot, update):
    chat_id = update.message.chat_id
    user = update.message.from_user

    store_user_action(user, '/save', 'command')
    
    query = config['INFLUX']['SELECT_ALL_QUERY'].format(user.id)
    rs = list(client.query(query))    
    
    if len(rs) == 0:
        bot.send_message(chat_id=chat_id, text='No yet records to save.') 
        return    

    rs = rs[0] 
    filename = 'bp{}.csv'.format(user.id)
    with open(filename, 'w', encoding='cp1251') as csvfile:
       for record in rs:
           TIME  = record['time'][:16]
           SYS = record['VAD']
           DIA = record['NAD']
           PULSE = record['pulse']
           COMMENT = record['comment']
           line = u"{},   {}, {}, {}, {}\n".format(TIME, 
                                              "" if SYS == None else SYS, 
                                              "" if DIA == None else DIA, 
                                              "" if PULSE == None else PULSE,
                                              "" if COMMENT == None else COMMENT)
           csvfile.write(line)
#       csvfile.close() 
    bot.send_document(chat_id=chat_id, document=open(filename, 'rb'), 
                      filename='My blood pressure.csv')
    return
                         

# show grafics command
def grafana(bot, update):
    chat_id = update.message.chat_id
    user= update.message.from_user
    store_user_action(user, '/grafana', 'command')

    render_url = config['GRAFANA']['RENDER'].format(user.id)
    print(render_url)
    img_data = requests.get(render_url).content
    img_file = '{}.jpg'.format(user.id)
    with open(img_file, 'wb') as filehandler:
       filehandler.write(img_data)
       filehandler.close()
    bot.send_photo(chat_id=chat_id, photo=open(img_file, 'rb'))
    
    url = config['GRAFANA']['URL'].format(user.id)
    text = 'Live graphics on [my.metrix.online]({}). External link.'.format(url)      
    bot.send_message(chat_id=chat_id, text=text, 
                     parse_mode=ParseMode.MARKDOWN)


        

# delete last point
def del_last(bot, update):
    chat_id = update.message.chat_id
    user = update.message.from_user
    store_user_action(user, '/del', 'command')
    #username = "%s_%s [id:%d]"%(user.first_name, user.last_name, user.id)
    # do we have some records?
    query = config['INFLUX']['SELECT_LAST_POINT_QUERY'].format(user.id)
    rs = list(client.query(query))
    if len(rs) > 0: # yes, we have a point(s) to delete
       rs = rs[0][0] # unpack list, get last point
       timepoint = rs['time'] 
       query = config['INFLUX']['DEL_LAST_POINT_QUERY'].format(user.id, timepoint)
       client.query(query)
       text = 'Record {}/{} deleted.'.format(rs['VAD'], rs['NAD'])
    else:                # new user
           text = 'No yet records to delete.'

    bot.send_message(chat_id=chat_id, text=text)


# delete all points
def del_all(bot, update):
    chat_id = update.message.chat_id
    user = update.message.from_user
    store_user_action(user, '/cleanup', 'command')
    #username = "%s_%s [id:%d]"%(user.first_name, user.last_name, user.id)
    bot.send_message(chat_id=chat_id, text='About to delete all..')
    query = config['INFLUX']['DEL_ALL_QUERY'].format(user.id)
    client.query(query)
    bot.send_message(chat_id=chat_id, text='Done')

# проверка и разбор входящей строки
# хорошая строка содержит два или три целых числа
# из которых первое и второе - показатели давления
# третье - пульс (опицонально)     
# все остальное считается текстовым комментарием
def parse(message):  
    vad, nad, pulse = None, None, None
    words = message.split(' ')
    error_code = 0
    
    values = []
    others = []
    for word in words:
      if word.isdigit():
          values.append(int(word))
      else:
          others.append(word)
    if len(values) == 0: # just talk? ok
        error_code = -1
    elif len(values) == 1:
        error_code = 1  # ":( Sorry.. What is '%d'? Feed me 2 or 3 values"
    elif len(values) >= 2:
        vad, nad = values[0], values[1]
        if  MAX_BP > values[0] > values[1] > MIN_BP: # check correctness
            error_code = 0
        else:
            error_code = 1 # Is it blood pressure?
    if len(values) >= 3:
        if  MAX_PULSE > values[2] > MIN_PULSE: # check correctness
            pulse = values[2]
            
    return vad, nad, pulse, error_code, ' '.join(others)
        
# writing data to influx database
def write_data(user, vad, nad, pulse=None, comment=None):
     json = [{"measurement": "blood_pressure",
             "tags":   {
                       "user_id": user.id
                       },
             "fields": {
                       "VAD": vad, 
                       "NAD": nad,
                       "pulse": pulse,
                       "comment":comment
                       }
             }]
     client.write_points(json)

# talk with user if no digital data given
def talk(bot, update):
    # try to find intent
    # hello intent
    #  help intent
    # others, we do not understand yet
    chat_id = update.message.chat_id
    user = update.message.from_user
    message = update.message.text
    
    words = message.lower().strip('!:),*;-').split(' ')
    for word in words:
        if word in config['DICTIONARY']['Hello']:
          reply = config['DIALOG']['Hello'].format(user.first_name)
          bot.send_message(chat_id=chat_id, text=reply)
          return
        elif word in config['DICTIONARY']['Help']:
          helpme(bot, update)
          return
    reply = config['DIALOG']['Nocomprene']
    bot.send_message(chat_id=chat_id, text=reply)
    return
     
# main conversation cycle
def conversation(bot, update):
    chat_id = update.message.chat_id
    user = update.message.from_user
    message = update.message.text

    vad, nad, pulse, error_code, comment = parse(message)
    if error_code == 0: # all checks passed, data accepted
        write_data(user, vad, nad, pulse, comment)
        if pulse == None: #pulse is optional
            reply = config['DIALOG']['Gotit2'].format(vad, nad)
        else:
            reply = config['DIALOG']['Gotit3'].format(vad, nad, pulse)
        store_user_action(user, message, 'data_accepted') # for later analysis
    elif error_code == 1: # check not passed
        reply = config['DIALOG']['Check fail'].format(vad, nad)
        store_user_action(user, message, 'data_rejected') # for later analysis
    else: # no digits, just a talk
        talk(bot, update)
        store_user_action(user, message, 'talk') # for later analysis
        return   
    bot.send_message(chat_id=chat_id, text=reply)
    return

def error(bot, update, error):
    """Log Errors caused by Updates."""
    logger.warning('Update "%s" caused error "%s"', update, error)


dispatcher.add_handler(CommandHandler('start', start))
dispatcher.add_handler(CommandHandler('help', helpme))
dispatcher.add_handler(CommandHandler('del', del_last))
dispatcher.add_handler(CommandHandler('cleanup', del_all))
dispatcher.add_handler(CommandHandler('save', save))
dispatcher.add_handler(CommandHandler('grafana', grafana))

dispatcher.add_handler(MessageHandler(Filters.text, conversation))

dispatcher.add_error_handler(error)

print('Start polling..')
updater.start_polling()
