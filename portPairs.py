#!/usr/bin/python3
import sqlite3
import twpath
import re
import argparse


port_class_numbers = {'BBS':1, 'BSB':2, 'SBB':3, 'SSB':4, 'SBS':5, 'BSS':6, 'SSS':7, 'BBB':8}
port_class_sales =   {1:'BBS', 2:'BSB', 3:'SBB', 4:'SSB', 5:'SBS', 6:'BSS', 7:'SSS', 8:'BBB'}

DEFAULT_DB_NAME = 'tw2002.db'

DIRECT = '  *** Direct warp available ***'
 
class Port:
    sector = None;
    port_class = None;
    ore_amt = None;
    ore_pct = None;
    org_amt = None;
    org_pct = None;
    equ_amt = None;
    equ_pct = None;
    last_seen = None;
    warps = None

    def __init__(self, args):
        self.sector, self.port_class, self.ore_amt, self.ore_pct, self.org_amt, self.org_pct, self.equ_amt, self.equ_pct, self.last_seen = args
        self.warps = {}

    def __repr__(self):
        return "Sector: {:4}  Class: {} ({})   Ore: {:4} {:3}%  Org: {:4} {:3}%  Equ: {:4} {:3}%".format(
                self.sector, port_class_numbers[self.port_class], self.port_class,
                self.ore_amt, self.ore_pct,
                self.org_amt, self.org_pct,
                self.equ_amt, self.equ_pct,
                )



def port_score(portA, portB, port_type):
    pct_score = 0
    amt_score = 0
    if(port_type[0] != "?"):
        pct_score += portA.ore_pct + portB.ore_pct
        amt_score += portA.ore_amt + portB.ore_amt
    if(port_type[1] != "?"):
        pct_score += portA.org_pct + portB.org_pct
        amt_score += portA.org_amt + portB.org_amt
    if(port_type[2] != "?"):
        pct_score += portA.equ_pct + portB.equ_pct
        amt_score += portA.equ_amt + portB.equ_amt
    return (pct_score, amt_score)

def main(dbname, port_type_A, port_type_B, commissioned=False):
    database = sqlite3.connect(dbname)

    ports = {}

    conn = database.cursor()

    port_type_A = port_type_A.upper()
    port_type_B = port_type_B.upper()

    ptA_regex = "^" + port_type_A.replace("?", ".") + "$"
    ptB_regex = "^" + port_type_B.replace("?", ".") + "$"

    fedSpace = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
    if(commissioned):
        starDock = None
        try:
            for sd in conn.execute('SELECT value FROM settings WHERE key=?', ('stardock',)):
                starDock = int(sd[0])
        except:
            pass
        if(starDock):
            fedSpace.append(starDock)

    # get a list of all ports
    for port in conn.execute('SELECT * FROM ports'):
        p = Port(port)
        ports[p.sector] = p

    # find all the neighboring ports
    for sector in ports:
        for warp in conn.execute('SELECT destination FROM warps WHERE source=?', (sector,)):
            warp = warp[0]
            # print(sector, warp)
            if(warp in ports):
                ports[sector].warps[warp] = True
        # print(sector, ports[sector].warps)

    # find neighboring ports that offer complementary sales of Org and Equ
    candidates = {}
    for sector in ports:
        portA = ports[sector]
        # if(portA.port_class[1:] != 'SB'):
        if(not re.match(ptA_regex, portA.port_class)):
            continue
        for warp in portA.warps:
            portB = ports[warp]
            # if(portB.port_class[1:] == 'BS'):
            if(re.match(ptB_regex, portB.port_class)):
                candidates[tuple(sorted([sector, warp]))] = True


    twpath.connect_database(dbname)

    fighters = twpath.fighter_locations()
    if(commissioned):
        fighters += fedSpace

    blind_warps = twpath.blind_warps()

    for a_b in sorted(candidates.keys(), key=lambda a_b:port_score(ports[a_b[0]], ports[a_b[1]], port_type_A)):
        for p in a_b:
            fRoute = None
            if(len(fighters)):
                fRoute = [str(s) for s in twpath.dijkstra(p, fighters, reverse=True)[0]]
            print(ports[p], end='')
            if(fRoute is None):
                print('')
            elif(len(fRoute) > 1):
                print("\n\t\tRoute from nearest safe warp ({} hops):\t{}".format(len(fRoute)-1, ' > '.join(fRoute)))
            else:
                print(DIRECT)
            if(len(blind_warps)):
                bRoute = [str(s) for s in twpath.dijkstra(p, blind_warps, reverse=True)[0]]
                if(fRoute is None or len(bRoute) < len(fRoute)):
                    print("\t\tNearest explored blind warp ({} hops):\t{}".format(len(bRoute)-1, ' > '.join(bRoute)))

        print('')

if(__name__ == '__main__'):
    parser = argparse.ArgumentParser(description='Find pairs of adjacent ports that will buy/sell your desired commodities.  One port of the pair will match what you specify in the command, and the other will be the opposite.')
    parser.add_argument('--database', '-d', dest='db', default=DEFAULT_DB_NAME, help='SQLite database file to use; default "{}"'.format(DEFAULT_DB_NAME))
    parser.add_argument('--commissioned', '-c', action='store_true', help='If you have a Commission, FedSpace sectors will be factored in for the nearest safe warp location')
    parser.add_argument('--port-type', '-p', default="?BS", help='Specify a port type by listing desired commodities in the following order: Ore Org Equ, specifying Buy (B) Sell (S) or don\'t care (?).  e.g., "?S?" for a port that sells Organics.  Can specify both port types, if desired, e.g., "SBS-SSB".  Default: "?BS".')

    args = parser.parse_args()
    # print(args)

    if(args.port_type):
        tmp = re.match('^(?P<portA>[BbSs?]{3})-(?P<portB>[BbSs?]{3})$', args.port_type)
        if(tmp):
            portA = tmp.group('portA')
            portB = tmp.group('portB')
        elif(re.match('^[BbSs?]{3}$', args.port_type)):
            portA = args.port_type
            portB = portA.replace("B", "T").replace("S", "B").replace("T", "S")
        else:
            raise argparse.ArgumentTypeError('Enter a 3 character code consisting only of "?", "B", or "S", e.g., "S?B" for a port that sells Fuel Ore and buys Equipment.  Optionally, enter two 3 character codes separated by a "-", e.g., "S?B-?SS".')

    main(args.db, portA, portB, commissioned=args.commissioned)

