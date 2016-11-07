#!/usr/bin/env python3
'''
IRC Bot for #Orga2.
'''

import ast
import csv
import datetime
import operator as op
import random
import re
import traceback
import shelve
import socket
import sys

DB_FILE = 'nicks.db'
ASM_FILE = 'asm.csv'
PHRASES_FILE = 'noit.txt'


LOGFILE = 'furfi.log'

HOST = 'irc.freenode.org'
PORT = 6667

NICK = 'furfi'
IDENT = 'furfi2'
REALNAME = 'Furfi the Second'
MASTER = 'godel'
CHANNEL = '#Orga2'

OPERATORS = {
    ast.Add: op.add,
    ast.Sub: op.sub,
    ast.Mult: op.mul,
    ast.Div: op.truediv,
    ast.Mod: op.mod,
    ast.BitXor: op.xor,
    ast.BitAnd: op.and_,
    ast.BitOr: op.or_,
    ast.RShift: op.rshift,
    ast.LShift: op.lshift,
    ast.Invert: op.inv,
    ast.USub: op.neg
}

asm_instr = {}
phrases = []

# This could be done faster with a priority queue.
top_words = []
top_upvotes = []

seen_dict = {}
connected = set()

def eval_expr(expr):
    return eval_(ast.parse(expr, mode='eval').body)

def eval_(node):
    if isinstance(node, ast.Num):
        return node.n
    elif isinstance(node, ast.BinOp):
        return OPERATORS[type(node.op)](eval_(node.left), eval_(node.right))
    elif isinstance(node, ast.UnaryOp):
        return OPERATORS[type(node.op)](eval_(node.operand))
    else:
        raise TypeError(node)


def update_db(user, line):
    user_value = {'words': 0, 'upvotes': 0}
    if user in db:
        user_value = db[user]
    user_value['words'] += len(line)
    top_words.append((user_value['words'], user))
    db[user] = user_value
    full_line = ' '.join(line)
    pattern = re.compile('(\S+\+\+)|(\S+: *\+\+)')
    for match in re.finditer(pattern, full_line):
        upvoted_user = match.group(0).split(':')[0].split('+')[0]
        if upvoted_user != user:
            upvoted_user_value = {'words': 0, 'upvotes': 0}
            if upvoted_user in db:
                upvoted_user_value = db[upvoted_user]
            upvoted_user_value['upvotes'] += 1
            db[upvoted_user] = upvoted_user_value
            top_upvotes.append((upvoted_user_value['upvotes'], upvoted_user))
    update_top_cache()

def remove_dups(top_list):
    nicks = set(map(lambda x: x[1], top_list))
    return [(max([e[0] for e in top_list if e[1] == nick]), nick)
            for nick in nicks]


def update_top_cache():
    global top_words, top_upvotes
    top_words = sorted(remove_dups(top_words), reverse=True)[:10]
    top_upvotes = sorted(remove_dups(top_upvotes), reverse=True)[:10]

def say(message, user=''):
    message = message if user == '' else '%s: %s' % (user, message)
    s.send(bytes('PRIVMSG %s :%s \r\n' % (CHANNEL, message), 'UTF-8'))

def getasminfo(instr):
    return '[%s] Descripción: %s. Más info: %s' % (
        instr,
        asm_instr[instr][1],
        asm_instr[instr][0])

def levenshtein(string1, string2):
    len1 = len(string1) + 1
    len2 = len(string2) + 1

    tbl = {}
    for i in range(len1):
        tbl[i, 0] = i
    for j in range(len2):
        tbl[0, j] = j
    for i in range(1, len1):
        for j in range(1, len2):
            cost = 0 if string1[i-1] == string2[j-1] else 1
            tbl[i, j] = min(tbl[i, j-1]+1, tbl[i-1, j]+1, tbl[i-1, j-1]+cost)

    return tbl[i, j]


def furfi(user):
    say('Para ver todo lo que puedo hacer, decí "!help".', user)

def manual(user):
    say('Acá tenés todos los manuales.', user)
    say('Introducción: %s' % 'http://goo.gl/50IZdI')
    say('Instrucciones (A-Z): %s' % 'http://goo.gl/l3GxUm')
    say('System Programming (TP3): %s' % 'http://goo.gl/VxFcxU')

def asm(user, parsed):
    if len(parsed) <= 1:
        say('No pude encontrar esa instrucción.', user)
        return
    instr = parsed[1].upper()
    if instr in asm_instr:
        say(getasminfo(instr), user)
    else:
        possibles = list(
            filter(lambda x: levenshtein(instr, x) < 2, asm_instr.keys()))
        if len(possibles) == 0:
            say('No pude encontrar esa instrucción.', user)
        else:
            say('No pude encontrar esa instrucción. ' \
                'Quizás quisiste decir:', user)
            for instr in possibles:
                say(getasminfo(instr))

def evalchat(user, parsed):
    expr = ' '.join(parsed[1:])
    if expr == '':
        return
    try:
        result = eval_expr(expr)
        say('dec: %d      hex: %s' % (result, hex(result)), user)
    except:
        say('Error evaluando.', user)

def wordschat(user):
    if user in db:
        user_value = db[user]
        say('Dijiste %d palabras en total.' % user_value['words'], user)
    else:
        say('No hay información en la db.', user)

def upvotes(user):
    if user in db:
        user_value = db[user]
        say('Tenés %d upvotes en total.' % user_value['upvotes'], user)
    else:
        say('No hay información en la db.', user)

def topwords(user):
    users = ', '.join(map(lambda x: '%s: %d' % (x[1], x[0]),
        filter(lambda x: x[0] > 0, top_words)))
    say('Los usuarios que más hablaron son: %s' % users, user)

def topupvotes(user):
    users = ', '.join(map(lambda x: '%s: %d' % (x[1], x[0]),
        filter(lambda x: x[0] > 0, top_upvotes)))
    say('Los usuarios que más upvotes tienen son: %s' % users, user)


def helpchat(user):
    say('Comandos que acepto:', user)
    say('!asm <instruccion> - Información sobre una instrucción.')
    say('!eval <expresión>  - Evaluar una expresión.')
    say('!help              - Ver este mensaje.')
    say('!manuales          - Link a los manuales.')
    say('!noittip           - Escuchar un tip de noit.')

def noittip(user):
    say(phrases[random.randint(0, len(phrases) - 1)], user)

def seen(user):
    if user in connected:
        say('%s esta conectado, no lo ves?' % user)
    elif user in seen_dict:
        say('La última vez que vi a %s fue en %s y se fue con motivo "%s".' % \
            (user,
             seen_dict[user]['time'].isoformat(' '),
             seen_dict[user]['message']))
    else:
        say('Ni idea, loco.')

def init_structures():
    for line in open(PHRASES_FILE, 'r').readlines():
        phrases.append(line)
    with open(ASM_FILE) as csvfile:
        asmreader = csv.reader(csvfile)
        for row in asmreader:
            asm_instr[row[0]] = (row[1], row[2])
    for user in db.keys():
        user_value = db[user]
        top_words.append((user_value['words'], user))
        top_upvotes.append((user_value['upvotes'], user))
    update_top_cache()

def get_user(line):
    return ((line[0].split('!'))[0])[1:]

def get_message(line):
    temp = ' '.join(line[3:])
    return temp[1:]

def get_connected(line):
    users = line[5:]
    if len(users) > 0:
        users = [users[0][1:]] + users[1:]
        for user in users:
            real_user = user[1:] if user[0] == '@' else user
            connected.add(real_user.lower())

def main():
    readbuffer = ''
    while 1:
        readbuffer = readbuffer+s.recv(1024).decode('UTF-8')
        temp = str.split(readbuffer, '\n')
        readbuffer = temp.pop()
        last_line = []

        for line in temp:
            line = str.rstrip(line)
            line = str.split(line)
            log.write(str(line) + '\n')
            log.flush()
            if line[-4:] == [':End', 'of', '/NAMES', 'list.'] and \
                  line[-5] == CHANNEL:
                get_connected(last_line)
            if line[0] == 'PING':
                s.send(bytes('PONG %s\r\n' % line[1], 'UTF-8'))
            if line[1] == 'NOTICE':
                if line[-1] in ['SIGTERM']:
                    raise
            elif line[1] == 'QUIT':
                message = get_message(line)
                user = get_user(line).lower()
                seen_dict[user] = {
                    'time' : datetime.datetime.now(
                        tz=datetime.timezone(datetime.timedelta(hours=-3))),
                    'message' : (' '.join(line[2:]))[1:],
                }
                connected.discard(user)
            elif line[1] == 'JOIN':
                user = get_user(line).lower()
                connected.add(user)
                if user in seen_dict.keys():
                    del seen_dict[user]
            elif line[1] == 'PRIVMSG':
                message = get_message(line)
                user = get_user(line)
                chan = line[2]
                if chan != CHANNEL and user != MASTER:
                    say('Hablame por %s por favor.' % CHANNEL, user)
                    continue
                parsed = message.split()
                update_db(user, parsed)
                if len(parsed) == 0:
                     pass
                elif parsed[0] == 'furfi:':
                    furfi(user)
                elif parsed[0] == '!manual' or parsed[0] == '!manuales':
                    manual(user)
                elif parsed[0] == '!asm':
                    asm(user, parsed)
                elif parsed[0] == '!eval':
                    evalchat(user, parsed)
                elif parsed[0] == '!noittip':
                    noittip(user)
                elif parsed[0] == '!words':
                    wordschat(user)
                elif parsed[0] == '!upvotes':
                    upvotes(user)
                elif parsed[0] == '!topwords':
                    topwords(user)
                elif parsed[0] == '!topupvotes':
                    topupvotes(user)
                elif parsed[0] == '!help':
                    helpchat(user)
                elif parsed[0] == '!seen' and len(parsed) > 1:
                    seen(parsed[1].lower())
                elif parsed[0] == '!say' and user == MASTER:
                    say(' '.join(parsed[1:]))
            last_line = line


if __name__ == '__main__':
    db = shelve.open(DB_FILE, flag='c', writeback=False)

    log = open('furfi.log', 'a')
    s = socket.socket()
    s.connect((HOST, PORT))
    s.send(bytes('NICK %s\r\n' % NICK, 'UTF-8'))
    s.send(bytes('USER %s %s bla :%s\r\n' % (IDENT, HOST, REALNAME), 'UTF-8'))
    s.send(bytes('JOIN %s\r\n' % CHANNEL, 'UTF-8'))
    s.send(bytes('PRIVMSG %s :Hello Master\r\n' % MASTER, 'UTF-8'))
    init_structures()
    try:
        s.send(bytes('NAMES\r\n', 'UTF-8'))
        main()
    except BaseException as e: 
        log.write('ERROR HAPPENED\n' + traceback.format_exc() + '\n') 
    db.sync()
    db.close()

