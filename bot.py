import logging

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (Updater, PicklePersistence, CommandHandler, Defaults, CallbackContext, MessageHandler,
                          Filters, CallbackQueryHandler)

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                    level=logging.INFO, filename="log.log")


def start(update: Update, context: CallbackContext):
    chat_id = update.effective_chat.id
    update.effective_message.reply_text(f"Hey, please add me to a group or channel and send a message with this "
                                        f"number (the - is part of it if its there): <code>{chat_id}</code>")
    bot_data = context.bot_data
    # test if first run
    if "to_connect" not in bot_data:
        bot_data["to_connect"] = []
    bot_data["to_connect"].append(chat_id)


def get_id(update: Update, context: CallbackContext):
    bot_data = context.bot_data
    # if its not even there, no need to worry about it
    if "to_connect" not in bot_data:
        return
    origin = int(update.effective_message.text)
    if origin not in bot_data["to_connect"]:
        return
    t = "Great, the chat is connected. Now you need to send me the names of the contestants. I accept 4 different " \
        "types of names: A normal text, a username, an inline mention or an inline url. Any other formatting will be " \
        "treated as normal text. Seperate the entries with a comma, followed by a whitespace. This would be valid " \
        "input: Poolitzer, @poolitzer, <a href=\"https://t.me/s/pooltalks\">inline URL</a>, " \
        "<a href=\"tg://user?id=208589966\">inline mention of Poolitzer</a>. Make sure all names are unique."
    context.bot.send_message(origin, t)
    # test if its first run
    if "connected" not in bot_data:
        bot_data["connected"] = {}
        bot_data["wait_names"] = []
    chat_id = update.effective_chat.id
    bot_data["connected"][origin] = chat_id
    bot_data["wait_names"].append(origin)
    bot_data["to_connect"].remove(origin)


def init_names(update: Update, context: CallbackContext):
    bot_data = context.bot_data
    if "wait_names" not in bot_data:
        return
    chat_id = update.effective_chat.id
    if chat_id not in bot_data["wait_names"]:
        return
    message = update.effective_message
    names = message.text.split(", ")
    # check if unique
    if len(names) > len(set(names)):
        t = "Hey, sorry, you have names in there which aren't unique. Please try again."
        message.reply_text(t)
        return
    users = {}
    for entity in message.parse_entities(["text_link", "text_mention"]):
        if entity.url:
            url = entity.url
        else:
            url = f"tg://user?id={entity.user.id}"
        text = message.parse_entities(["text_link", "text_mention"])[entity]
        users[text] = {"url": url, "count": 0}
        names.remove(text)
    for name in names:
        users[name] = {"count": 0}
    string = create_contestant_list(users)
    message_id = context.bot.send_message(bot_data['connected'][chat_id], string).message_id
    id_users = {}
    buttons = []
    string = ""
    x = 0
    for user in users:
        id_users[x] = user
        buttons.append(InlineKeyboardButton(text=str(x), callback_data=str(x)))
        string += f"{x}: <a href=\"{users[user]['url']}\">{user}</a>\n" if 'url' in users[user] \
            else f"{x}: {user}\n"
        x += 1
    t = "Great, got the names. Now we reached the main setup. You have the following possibilities to add a point to " \
        "each contestant: Press the belonging button below or send me a list of the ids, with the known comma " \
        "whitespace seperators. You can also type out the name and send it instead of the id, this is case sensitive " \
        "though.\n\n" + string
    message.reply_text(t, reply_markup=InlineKeyboardMarkup(build_menu(buttons, 5)))
    context.chat_data.update({"finished": message_id, "users": users, "id_users": id_users})
    bot_data["wait_names"].remove(chat_id)


def callback_query_handler(update: Update, context: CallbackContext):
    query = update.callback_query
    chat_data = context.chat_data
    user_id = int(query.data)
    name = chat_data["id_users"][user_id]
    chat_data["users"][name]["count"] += 1
    edit_connected(chat_data["users"], context.bot, chat_data["finished"],
                   context.bot_data["connected"][update.effective_chat.id])
    query.answer(f"Got it. Contestant {name} got a point.")


def users_handler(update: Update, context: CallbackContext):
    chat_data = context.chat_data
    if "finished" not in chat_data:
        return
    name_list = []
    for user_id in update.effective_message.text.split(", "):
        try:
            name_list.append(chat_data["id_users"][int(user_id)])
        except ValueError:
            if user_id in chat_data["users"]:
                name_list.append(user_id)
            else:
                update.effective_message.reply_text(f"Sorry, {user_id} isn't an id or a valid name. Fix it ;P")
                return
        except KeyError:
            update.effective_message.reply_text(f"Sorry, {user_id} is a wrong id. Fix it ;P")
            return
    if not name_list:
        return
    for name in name_list:
        chat_data["users"][name]["count"] += 1
    edit_connected(chat_data["users"], context.bot, chat_data["finished"],
                   context.bot_data["connected"][update.effective_chat.id])
    update.effective_message.reply_text(f"Successfully gave these contestants a point: {', '.join(name_list)}")


def edit_connected(users, bot, message_id, chat_id):
    # sorting turns it into a tuple
    string_list = sorted(users.items(), key=lambda single_user: single_user[1]["count"], reverse=True)
    string = ""
    max_digits = len(str(string_list[0][1]["count"]))
    for user in string_list:
        new_string = f"<code>{user[1]['count']}</code> - <a href=\"{user[1]['url']}\">{user[0]}</a>\n" if 'url' \
                                                                                                        in user[1] \
                     else f"<code>{user[1]['count']}</code> - {user[0]}\n"
        current_digits = len(str(user[1]["count"]))
        if max_digits != current_digits:
            new_string = "<code>" + "".rjust(max_digits - current_digits) + new_string[6:]
        string += new_string
    bot.edit_message_text(text=string, message_id=message_id, chat_id=chat_id)


def build_menu(buttons,
               n_cols,
               header_buttons=None,
               footer_buttons=None):
    menu = [buttons[i:i + n_cols] for i in range(0, len(buttons), n_cols)]
    if header_buttons:
        menu.insert(0, [header_buttons])
    if footer_buttons:
        menu.append([footer_buttons])
    return menu


def create_contestant_list(users):
    string = ""
    for user in users:
        string += f"{users[user]['count']}: <a href=\"{users[user]['url']}\">{user}</a>\n" if 'url' in users[user] \
            else f"{users[user]['count']}: {user}\n"
    return string


def main():
    persistence = PicklePersistence("pickle_file")
    updater = Updater(token="TOKEN", use_context=True, persistence=persistence,
                      defaults=Defaults(parse_mode="HTML"))
    dp = updater.dispatcher
    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(MessageHandler(Filters.regex(r"^(-\d+|\d+)$") & (~ Filters.private) &
                                  (Filters.update.message | Filters.update.channel_post), get_id))
    dp.add_handler(MessageHandler(Filters.text, init_names))
    dp.add_handler(CallbackQueryHandler(callback_query_handler))
    dp.add_handler(MessageHandler(Filters.text, users_handler), group=1)
    updater.start_polling()
    updater.idle()


if __name__ == '__main__':
    main()
