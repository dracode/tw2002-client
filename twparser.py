#!/usr/bin/python3
import re
import sqlite3
import argparse
import queue
import time
import threading
from multiprocessing.pool import ThreadPool
import traceback
import sys

# variable for collating the multi-line output of route planning commands
routeList = None

# our SQLite database
database = None
DB_THREAD_ID = None
DEFAULT_DB_NAME = 'tw2002.db'
dbqueue = queue.Queue()
settings = {}

# verbosity level for parser output
verbose = 0

class PortStatus:
    operation = None
    prev_their_offer = None
    prev_our_offer = None
    final_offer = False

port_status = PortStatus()


# sync flag for threads to exit
QUITTING_TIME = False

port_class_numbers = {'BBS':1, 'BSB':2, 'SBB':3, 'SSB':4, 'SBS':5, 'BSS':6, 'SSS':7, 'BBB':8}
port_class_sales =   {1:'BBS', 2:'BSB', 3:'SBB', 4:'SSB', 5:'SBS', 6:'BSS', 7:'SSS', 8:'BBB'}

# pattern matching the port list from Computer Interrogation Mode (CIM)
portListRe = re.compile('^(?P<sector>[ 0-9]{3}[0-9]) (?P<ore_bs>[ -]) (?P<ore_amt>[ 0-9]{3}[0-9]) (?P<ore_pct>[ 0-9]{2}[0-9])% (?P<org_bs>[ -]) (?P<org_amt>[ 0-9]{3}[0-9]) (?P<org_pct>[ 0-9]{2}[0-9])% (?P<equ_bs>[ -]) (?P<equ_amt>[ 0-9]{3}[0-9]) (?P<equ_pct>[ 0-9]{2}[0-9])%$')

# pattern to match so we know what sector we're looking at if we see a Trader or Planet
workingSectorRe = re.compile("^Sector  : (?P<sector>[0-9]+) in .*\.$")

# pattern to match the list of warps out of each known sector from the CIM report or Computer Warps report (C, I)
warpListFromCIMRe = re.compile('^(?P<sector>[ 0-9]{3}[0-9])(?P<warps>(?: [ 0-9]{3}[0-9])+)$')
warpListFromCIRe = re.compile("^Sector (?P<sector>[0-9]+) has warps to sector\(s\) : (?P<warps>[0-9 \-]+)$")

# various patterns to match route planning, either via Computer Interrogation Mode (CIM) or Computer -> F Course Plotter (CF) mode
routeListFromCIMRe = re.compile("^FM > [0-9]+$")
routeListFromCFRe = re.compile("^The shortest path .* from sector [0-9]+ to sector [0-9]+ is:$")
routeListRestRe = re.compile("^(?:  TO)?[0-9 ()>]+$")
routeListCompleteCIMRe = re.compile("^FM > [0-9]+   TO > [0-9]+ (?P<route>[0-9 ()>]+)$")
routeListCompleteCFRe = re.compile("^The shortest path .* from sector [0-9]+ to sector [0-9]+ is: (?P<route>[0-9 ()>]+)$")

# maintain a list of deployed fighters, so we can calculate the nearest transwarp point for any given sector
clearFightersRe = re.compile("^\s*Deployed  Fighter  Scan")
saveFightersRe = re.compile("^ (?P<sector>[0-9 ]{4}[0-9])\s+[0-9]+\s+(?:Personal|Corp)\s+(?:Defensive|Offensive|Toll)")

# keep track of planet locations
planetListRe = re.compile("^\s*(?P<sector>[0-9 ]{4}[0-9])\s+T?\s+#(?P<id>[0-9]+)\s+(?P<name>.*?)\s+Class (?P<class>[A-Z]), .*(?P<citadel>No Citadel|Level [0-9])")

# auto-haggle triggers
portOperationRe = re.compile("^How many holds of .+ do you want to (?P<operation>buy|sell) \[[0-9,]+\]\?")
portFinalOfferRe = re.compile("^Our final offer is [0-9,]+ credits.$")
portPromptRe = re.compile(r"^Your offer \[(?P<offer>[0-9,]+)\] \?$")

# game information
maxSectorRe = re.compile("^\s+Maximum players [0-9]+, sectors (?P<maxSector>[0-9,]+), ports [0-9,]+, planets [0-9,]+\.")
stardockRe = re.compile("^\s*The StarDock is located in sector (?P<sector>[0-9,]+)\.$")

# from https://stackoverflow.com/questions/14693701/how-can-i-remove-the-ansi-escape-sequences-from-a-string-in-python
def strip_ansi(inString):
    ansi_escape_8bit = re.compile(br'''
        (?: # either 7-bit C1, two bytes, ESC Fe (omitting CSI)
            \x1B
            [@-Z\\-_]
        |   # or a single 8-bit byte Fe (omitting CSI)
            [\x80-\x9A\x9C-\x9F]
        |   # or CSI + control codes
            (?: # 7-bit CSI, ESC [ 
                \x1B\[
            |   # 8-bit CSI, 9B
                \x9B
            )
            [0-?]*  # Parameter bytes
            [ -/]*  # Intermediate bytes
            [@-~]   # Final byte
        )
    ''', re.VERBOSE)
    return ansi_escape_8bit.sub(b'', inString)


def log(msg, logLevel):
    global verbose
    if(logLevel > verbose):
        return
    try:
        msg = 'String={}, groups={}'.format(repr(msg.string), repr(msg.groupdict()))
    except:
        pass
    print("[LogLevel {}]: {}".format(logLevel, msg), flush=True)

# function decorator that will pass off database write operations to the dedicated thread, if called from another thread
def dbWriteWrapper(func):
    def func_dbWriteWrapper(*args):
        if(threading.get_ident() != DB_THREAD_ID):
            dbqueue.put((func, *args))
            return
        return func(*args)
    return func_dbWriteWrapper

@dbWriteWrapper
def clear_fighter_locations():
    global database
    log("clear_fighter_locations", 1)
    c = database.cursor()
    c.execute('DELETE FROM fighters')
    database.commit()

@dbWriteWrapper
def save_fighter_location(match):
    global database
    sector = int(match.group('sector').strip())
    log("save_fighter_location: {}".format(sector), 1)

    c = database.cursor()
    c.execute('REPLACE INTO fighters (sector) VALUES(?)', (sector,))
    database.commit()

@dbWriteWrapper
def save_setting(key,value):
    global database

    c = database.cursor()
    c.execute('REPLACE INTO settings (key, value) VALUES(?, ?)', (key, value))
    database.commit()

@dbWriteWrapper
def save_warp_list(match):
    global database
    sector = int(match.group('sector').strip())
    warps = re.findall('[0-9]+', match.group('warps'))
    log("save_warp_list: {}, {}".format(sector, warps), 1)
    c = database.cursor()
    c.execute('''
        REPLACE into explored (sector)
        VALUES(?)
        ''', (sector,))
    for warp in warps:
        c.execute('''
            REPLACE INTO warps (source, destination)
            VALUES(?, ?)
            ''', (sector, int(warp))
        )
    database.commit()

@dbWriteWrapper
def save_port_list(match):
    global database
    log("save_port_list: {}".format(match.groups()), 1)
    port_class = (match.group('ore_bs') + match.group('org_bs') + match.group('equ_bs')).replace(' ', 'S').replace('-', 'B')

    c = database.cursor()
    c.execute('''
        REPLACE INTO ports (sector, class, ore_amt, ore_pct, org_amt, org_pct, equ_amt, equ_pct, last_seen)
        VALUES(?, ?, ?, ?, ?, ?, ?, ?, date('now'))
        ''', (
            int(match.group('sector').strip()),
            port_class,
            int(match.group('ore_amt').strip()),
            int(match.group('ore_pct').strip()),
            int(match.group('org_amt').strip()),
            int(match.group('org_pct').strip()),
            int(match.group('equ_amt').strip()),
            int(match.group('equ_pct').strip()),
            )
    )
    database.commit()

@dbWriteWrapper
def save_planet_list(match):
    global database
    log("save_planet_list: {}".format(match.groups()), 1)
    c = database.cursor()

    citadel = match.group('citadel').strip()[-1]
    if(citadel == 'l'): # "No Citadel"
        citadel = '0'
    c.execute('''
        REPLACE INTO planets (sector, id, name, class, citadel)
        VALUES(?, ?, ?, ?, ?)
        ''', (
            int(match.group('sector').strip()),
            int(match.group('id').strip()),
            match.group('name').strip(),
            match.group('class').strip(),
            int(citadel)
            )
    )
    database.commit()

@dbWriteWrapper
def save_route_list(match):
    global database
    route = re.findall('[0-9]+', match.group('route'))
    log("save_route_list: {}".format(route), 1)

    c = database.cursor()
    for i in range(len(route)-1):
        # print(route[i], route[i+1])
        c.execute('''
            REPLACE INTO warps (source, destination)
            VALUES(?, ?)
            ''', (int(route[i]), int(route[i+1]))
        )
    database.commit()


def parse_partial_line(line):
    global port_status

    try:
        strippedLine = strip_ansi(line).decode('utf-8').rstrip()
    except:
        return
    log("parse_partial_line: {}".format((strippedLine,)), 3)

    portPrompt = portPromptRe.match(strippedLine)
    if(portPrompt):
        their_offer = int(portPrompt.group('offer').replace(',',''))
        our_offer = their_offer
        if(port_status.prev_their_offer == None):
            if(port_status.operation == 'sell'):
                our_offer *= 1.07
            else:
                our_offer *= 0.95
        elif(their_offer == port_status.prev_their_offer):
            # clearly something has gone awry
            return None
        else:
            mult = 0.3
            if(port_status.final_offer):
                mult = 0.5
            delta = port_status.prev_our_offer - their_offer
            our_offer = port_status.prev_our_offer - (delta * mult)
        port_status.prev_their_offer = their_offer
        port_status.prev_our_offer = our_offer
        port_status.final_offer = False
        return('{}'.format(int(our_offer)).encode('utf-8'))

def parse_complete_line(line):
    global routeList
    global port_status
    try:
        strippedLine = strip_ansi(line).decode('utf-8').rstrip()
    except:
        return
    log("parse_complete_line: {}".format((strippedLine,)), 3)

    workingSector = workingSectorRe.match(strippedLine)
    if(workingSector):
        settings['working_sector'] = int(workingSector.group('sector'))
        return

    stardock = stardockRe.match(strippedLine)
    if(stardock):
        log("stardock: {}".format(stardock), 2)
        sd = int(stardock.group('sector').replace(',',''))
        if(not 'stardock' in settings or settings['stardock'] != sd):
            settings['stardock'] = sd
            save_setting('stardock', sd)
        return

    maxSector = maxSectorRe.match(strippedLine)
    if(maxSector):
        log("maxSector: {}".format(maxSector), 2)
        max_sector = int(maxSector.group('maxSector').replace(',',''))
        if(not 'max_sector' in settings or settings['max_sector'] != max_sector):
            settings['max_sector'] = max_sector
            save_setting('max_sector', max_sector)
        return

    portOperation = portOperationRe.match(strippedLine)
    if(portOperation):
        log("portOperation: {}".format(portOperation), 2)
        port_status.operation = portOperation.group('operation')
        port_status.prev_their_offer = None
        return

    portFinalOffer = portFinalOfferRe.match(strippedLine)
    if(portFinalOffer):
        log("portFinalOffer: {}".format(portFinalOffer), 2)
        port_status.final_offer = True
        return

    clearFighters = clearFightersRe.match(strippedLine)
    if(clearFighters):
        log("clearFighters: {}".format(clearFighters), 2)
        clear_fighter_locations()
        return

    saveFighters = saveFightersRe.match(strippedLine)
    if(saveFighters):
        log("saveFighters: {}".format(saveFighters), 2)
        save_fighter_location(saveFighters)

    warpList = warpListFromCIMRe.match(strippedLine)
    if(warpList):
        # print(strippedLine, warpList.groups())
        save_warp_list(warpList)
        return

    warpList = warpListFromCIRe.match(strippedLine)
    if(warpList):
        save_warp_list(warpList)
        return

    portList = portListRe.match(strippedLine)
    if(portList):
        # print(strippedLine, portList.groups())
        save_port_list(portList)
        return

    planetList = planetListRe.match(strippedLine)
    if(planetList):
        log("planetList: {}".format(planetList.groups()), 2)
        save_planet_list(planetList)

    if(routeList): # we've already seen the "FM" line, let's look for the rest of the message
        if(len(strippedLine) == 0):
            strippedLine = routeList
            routeList = None
        else:
            if(routeListRestRe.match(strippedLine)):
                routeList += " " + strippedLine
            else:
                routeList = None

    routeListComplete = routeListCompleteCIMRe.match(strippedLine)
    if(routeListComplete):
        save_route_list(routeListComplete)
        return
    routeListComplete = routeListCompleteCFRe.match(strippedLine)
    if(routeListComplete):
        save_route_list(routeListComplete)
        return
 
    # route listings are multi-line.  accumulate the lines, then we'll process it once it's complete
    routeListFrom = routeListFromCIMRe.match(strippedLine)
    if(routeListFrom):
        routeList = strippedLine
        return
    routeListFrom = routeListFromCFRe.match(strippedLine)
    if(routeListFrom):
        routeList = strippedLine
        return

def dbqueue_service(dbname):
    global database
    global dbqueue
    global QUITTING_TIME
    global DB_THREAD_ID

    DB_THREAD_ID = threading.get_ident()

    database = sqlite3.connect(dbname)

    didWork = False
    while(True):
        try:
            func, *args = dbqueue.get(block=False)
            if(len(args)):
                logStr = "dbqueue_service: {}({})".format(func.__name__, *args)
                try:
                    logStr = "dbqueue_service: {}({})".format(func.__name__, ', '.join([repr(x.groupdict()) for x in args]))
                except:
                    traceback.print_exc()
                    pass
                log(logStr, 1)
                func(*args)
            else:
                log("dbqueue_service: {}()".format(func.__name__),1)
                func()
            didWork += 1
        except queue.Empty:
            if(didWork):
                if(didWork > 1):
                    # if we had a queue, flash the screen to indicate that all database operations are complete
                    print("\x1b[?5h\x1b[?5l", flush=True, end='')
                didWork = 0
            if(QUITTING_TIME):
                break
            time.sleep(1)
        except Exception:
            traceback.print_exc()

def dbqueue_monitor():
    global dbqueue
    global QUITTING_TIME

    cnt = 0
    while(True):
        cnt += 1
        if((cnt % 10) == 0):
            log("dbqueue_monitor: {} queued items".format(dbqueue.qsize()), 1)
        if(QUITTING_TIME):
            break
        time.sleep(1)

def database_connect(dbname):
    initdb = sqlite3.connect(dbname)

    cursor = initdb.cursor()
    cursor.execute('''
            CREATE TABLE IF NOT EXISTS ports (
                sector INTEGER PRIMARY KEY,
                class TEXT,
                ore_amt INTEGER,
                ore_pct INTEGER,
                org_amt INTEGER,
                org_pct INTEGER,
                equ_amt INTEGER,
                equ_pct INTEGER,
                last_seen INTEGER
            );
            ''')

    cursor.execute('''
            CREATE TABLE IF NOT EXISTS warps (
                source INTEGER,
                destination INTEGER,
                PRIMARY KEY (source, destination)
            );
            ''')

    cursor.execute('''
            CREATE TABLE IF NOT EXISTS explored (
                sector INTEGER PRIMARY KEY
            );
            ''')

    cursor.execute('''
            CREATE TABLE IF NOT EXISTS planets (
                sector INTEGER,
                id INTEGER PRIMARY KEY,
                name TEXT,
                class TEXT,
                citadel INTEGER
            );
            ''')


    cursor.execute('''
            CREATE TABLE IF NOT EXISTS fighters (
                sector INTEGER PRIMARY KEY
            );
            ''')

    cursor.execute('''
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT
            );
            ''')


    for k,v in cursor.execute('''
            SELECT key, value
            FROM settings
            '''):
        settings[k]=v

    # print(settings)
    cursor.close()
    initdb.commit()

    del cursor
    del initdb

    # pool = ThreadPool(processes=1)
    # pool.apply_async(dbqueue_service, (dbname,))

    # pool = ThreadPool(processes=1)
    # pool.apply_async(dbqueue_monitor)
    dbq_s = threading.Thread(target=dbqueue_service, args=(dbname,))
    dbq_s.start()


    dbq_m = threading.Thread(target=dbqueue_monitor)
    dbq_m.start()



def quit():
    global dbqueue
    global QUITTING_TIME

    if(dbqueue.qsize() > 0):
        print("Parsing complete.\nWaiting for database writes to finish...")
    QUITTING_TIME = True


if(__name__ == '__main__'):
    try:
        parser = argparse.ArgumentParser(description='A TW2002 log parsing utility.  This tool will database ports, warps, and the locations of your fighters and planets for use with analytical tools.')
        parser.add_argument('--database', '-d', dest='db', default=DEFAULT_DB_NAME, help='SQLite database file to use; default "{}"'.format(DEFAULT_DB_NAME))
        parser.add_argument('--verbose', '-v', type=int, nargs='?', default=0, help='Verbose level for parser feedback (1-3)')
        parser.add_argument('filename', nargs='+', type=argparse.FileType('rb'), help='Name of the game log file(s) to parse')

        args = parser.parse_args()

        verbose = args.verbose

        database_connect(args.db)

        for f in args.filename:
            for line in f:
                parse_complete_line(line)
    finally:
        quit()

