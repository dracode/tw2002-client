#!/usr/bin/python3

import telnetlib
import sys
import select
import termios
import tty
import fcntl
import os
import socket
import argparse
import time
import threading
from contextlib import contextmanager

import twparser

settings = {}
settings['mute'] = False
settings['max_sector'] = 1000

DEFAULT_DB_NAME = 'tw2002.db'

# put the terminal into 'cbreak' mode instead of the normal 'cooked' mode, so we can get characters as they are typed
@contextmanager
def cbreak(stream):
    old_settings = termios.tcgetattr(stream)
    try:
        tty.setcbreak(stream.fileno())
        yield
    finally:
        termios.tcsetattr(stream, termios.TCSADRAIN, old_settings)

# from http://ballingt.com/nonblocking-stdin-in-python-3/
@contextmanager
def nonblocking(stream):
    orig = fcntl.fcntl(stream.fileno(), fcntl.F_GETFL)
    try:
        fcntl.fcntl(stream.fileno(), fcntl.F_SETFL, orig | os.O_NONBLOCK)
        yield
    finally:
        fcntl.fcntl(stream.fileno(), fcntl.F_SETFL, orig)


def connect(host, port):

    try:
        ip = socket.gethostbyname(host)
    except:
        print("telnet: could not resolve {}/{}: Name or service not known".format(host, port), file=sys.stderr)
        return 1

    print('Trying {}...'.format(ip))
    try:
        tn = telnetlib.Telnet(host, port)
    except:
        print("telnet: Unable to connect to remote host: Connection timed out", file=sys.stderr)
        return 2
    print('Connected to {}.'.format(host))

    return tn

def interactive_session(tn):
    global settings
    currentData = b''

    with cbreak(sys.stdin):
        with nonblocking(sys.stdin):
            noNewData = 0
            while(True):
                newData = b''
                try:
                    newData = tn.read_eager()
                except EOFError:
                    print("Connection closed by foreign host.")
                    break
                if(len(newData)):
                    noNewData = 0
                    if(twparser.verbose == 4):
                        print(("newData1", newData))
                    # print(newData.decode('utf-8'), flush=True, end='')
                    # sys.stdout.write(newData)
                    if(not settings['mute']):
                        os.write(1, newData)
                    newData = newData.replace(b'\r', b'')
                    currentData += newData
                    arr = currentData.splitlines(keepends=True)
                    if(twparser.verbose == 4):
                        print(("arr", arr))
                    for line in arr:
                        if(line[-1] == 0x0a): # ends with b'\n'
                            twparser.parse_game_line(line[:-1])
                    if(len(arr) and arr[-1][-1] != 0x0a):
                        currentData = arr[-1]
                    else:
                        currentData = b''

                    if(len(currentData)):
                        # print(("currentData", currentData))
                        # print(currentData, end='')
                        pass
                else:
                    noNewData += 1

                # if(False):
                if(select.select([sys.stdin,], [], [], 0.0)[0]):
                    # in non-blocking mode, read() will return b'' if no data is available
                    # we need non-blocking mode because select() doesn't tell us how much data is available;
                    # even if more than one input character is in the buffer, select() won't fire again until new input is received
                    userData = sys.stdin.buffer.read(1)
                    while(userData):
                        # translates backspace character into the one expected by tw2002
                        if(userData == b''): # secret escape char
                            user_command(tn)
                            # twparser.verbose += 1
                            # if(twparser.verbose == 4):
                            #     settings['mute'] = True
                            # if(twparser.verbose > 4):
                            #     twparser.verbose = 0
                            #     settings['mute'] = False
                            # print("VERBOSE LEVEL CHANGED: {}".format(twparser.verbose), flush=True)
                            break
                        if(userData == b'\x7f'): # Backspace
                            userData = b'\x08' # ctrl-H
                        # translate newline into CR-LF, as expected by telnet protocol
                        if(userData == b'\n'):
                            userData = b'\r\n'
                        # print(('userData', userData), flush=True)
                        tn.write(userData)
                        userData = sys.stdin.buffer.read(1)
                # we haven't seen any data recently, so give the CPU a break...
                if(noNewData > 5):
                    time.sleep(0.1)
                        
def do_ztm(tn):
    tn.write(b'QQQQQQQQN^')
    for x in range(2, settings['max_sector']+1):
        cmd = 'F{}\r\n{}\r\n'.format(1, x)
        tn.write(cmd.encode('utf-8'))
        time.sleep(0.2)
        cmd = 'F{}\r\n{}\r\n'.format(x, 1)
        tn.write(cmd.encode('utf-8'))
        time.sleep(0.2)
        cmd = 'F{}\r\n{}\r\n'.format(x-1, x)
        tn.write(cmd.encode('utf-8'))
    tn.write(b'Q')
    
def user_command(tn):
    global settings

    while(True):
        userData = sys.stdin.buffer.read(1)
        if(not userData):
            time.sleep(0.1)
            continue
        # change Verbose level
        if(userData >= b'0' and userData <= b'4'):
            twparser.verbose = int(userData)
            if(twparser.verbose == 4):
                settings['mute'] = True
            else:
                settings['mute'] = False
            print("VERBOSE LEVEL CHANGED: {}".format(twparser.verbose), flush=True)
        if(userData == b'z' or userData == b'Z'):
            threading.Thread(target=do_ztm, args=(tn,)).start()
        break

        

if(__name__ == '__main__'):
    try:
        parser = argparse.ArgumentParser(description='A telnet emulator client for playing TW2002.  This client will database ports, warps, and the locations of your fighters and planets for use with analytical tools.')
        parser.add_argument('--database', '-d', dest='db', default=DEFAULT_DB_NAME, help='SQLite database file to use; default "{}"'.format(DEFAULT_DB_NAME))
        parser.add_argument('host', help='Hostname or IP address of the game server.')
        parser.add_argument('port', help='Port where the game is running.')

        args = parser.parse_args()
        # print(args)

        twparser.database_connect(args.db)

        telnetConnection = connect(args.host, args.port)

        if(telnetConnection):
            interactive_session(telnetConnection)

    finally:
        twparser.quit()
