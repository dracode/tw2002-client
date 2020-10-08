#!/usr/bin/python3

import sqlite3
import argparse
import re

database = None
DEFAULT_DB_NAME = 'tw2002.db'

def connect_database(filename):
    global database
    database = sqlite3.connect(filename)

def fighter_locations():
    global database
    conn = database.cursor()
    query = conn.execute("SELECT sector FROM fighters")
    retval = [int(sector[0]) for sector in query]
    conn.close()
    return retval

def blind_warps():
    global database
    conn = database.cursor()
    blind_warps = []
    for sector in conn.execute('''
        SELECT sector
        FROM explored
        WHERE NOT EXISTS(
            SELECT sector
            FROM ports
            WHERE explored.sector = ports.sector
            )
        '''):
        blind_warps.append(int(sector[0]))
    return blind_warps

def port_search(searchStr, avoids=[]):
    global database
    searchStr = searchStr.upper().replace("?", "_")
    conn = database.cursor()
    query = conn.execute("SELECT sector FROM ports WHERE class LIKE ?", (searchStr,))
    retval = [int(sector[0]) for sector in query]
    retval = filter(lambda p: p not in avoids, retval)
    conn.close()
    return retval

def deadend_search(avoids=[]):
    global database
    conn = database.cursor()
    query = conn.execute('''
        SELECT source AS sector
        FROM warps
        GROUP BY source
        HAVING count(*)=1
        INTERSECT
        SELECT destination AS sector
        FROM warps
        GROUP BY destination
        HAVING count(*)=1
        ''')
    retval = [int(sector[0]) for sector in query]
    retval = filter(lambda p: p not in avoids, retval)
    conn.close()
    return retval

def list_all_sectors():
    global database
    conn = database.cursor()
    query = conn.execute("SELECT DISTINCT source FROM warps")
    retval = [int(sector[0]) for sector in query]
    conn.close()
    return retval

def warps_from(sector):
    global database
    conn = database.cursor()
    query = conn.execute("SELECT destination FROM warps WHERE source=?", (sector,))
    retval = [int(warp[0]) for warp in query]
    conn.close()
    return retval

def warps_to(sector):
    global database
    conn = database.cursor()
    query = conn.execute("SELECT source FROM warps WHERE destination=?", (sector,))
    retval = [int(warp[0]) for warp in query]
    conn.close()
    return retval

def backtrace(parent, start, end, reverse=False):
    path = [end]
    while(path[-1] != start):
        path.append(parent[path[-1]])
    if(not reverse):
        path.reverse()
    return path

# mainly drawn from http://pythonfiddle.com/dijkstra/
def dijkstra(start_vertex, end_vertices, avoids=[], reverse=False, return_all=False):
    if(not isinstance(end_vertices, list)):
        end_vertices = [end_vertices]
    queue = []
    distance = {}
    visited = {}
    parent = {}
    shortest_distance = {}

    retVal = []

    for node in list_all_sectors():
        distance[node] = None
        visited[node] = False
        parent[node] = None
        shortest_distance[node] = float('inf')

        if(node in avoids):
            visited[node] = True

    queue.append(start_vertex)
    distance[start_vertex] = 0
    while(len(queue)):
        current = queue.pop(0)
        visited[current] = True
        if(current in end_vertices):
            retVal.append(backtrace(parent, start_vertex, current, reverse))
            if(not return_all):
                return retVal
        warp_list = warps_from(current)
        if(reverse):
            warp_list = warps_to(current)
        for neighbor in warp_list:
            if(visited[neighbor] == False):
                distance[neighbor] = distance[current] + 1
                if(distance[neighbor] < shortest_distance[neighbor]):
                    shortest_distance[neighbor] = distance[neighbor]
                    parent[neighbor] = current
                    queue.append(neighbor)
    return retVal


if(__name__ == '__main__'):
    parser = argparse.ArgumentParser(description='Calculate the shortest path between sectors or facilities in a TW2002 game.')
    parser.add_argument('--database', '-d', dest='db', default=DEFAULT_DB_NAME, help='SQLite database file to use; default "{}"'.format(DEFAULT_DB_NAME))
    parser.add_argument('--all-destinations', '-a', dest='all', action='store_true', default=False, help='Show routes to all destinations, not only the nearest')
    parser.add_argument('--reverse', '-r', dest='reverse', action='store_true', default=False, help='Reverse the start/destination; useful when you have a single known destination but want to learn the nearest likely starting point (fighter locations, blind warp locations)')
    parser.add_argument('--port-type', '-p', help='Specify a port type by listing desired commodities in the following order: Ore Org Equ, specifying Buy (B) Sell (S) or don\'t care (?).  e.g., "?S?" for a port that sells Organics.')
    parser.add_argument('--fighters', '-f', action='store_true', help='Adds to your destination list all sectors that currently have one of your deployed fighters')
    parser.add_argument('--fedspace', '-c', action='store_true', help='Adds to your destination list all sectors in FedSpace')
    parser.add_argument('--blind-warps', '-b', action='store_true', help='Adds to your destination list all mapped sectors not known to contain a port.  Use caution when blind warping!')
    parser.add_argument('--avoids', '-v', type=int, default=[], nargs='+', help='Sectors to avoid plotting a route through')
    parser.add_argument('--dead-ends', '-e', action='store_true', help='Adds known presumed to be dead end sectors')
    parser.add_argument('start',  type=int, help='The starting sector for the route calculation')
    parser.add_argument('destination', type=int, nargs='*', help='The desired destination sector')

    args = parser.parse_args()
    # print(args)

    connect_database(args.db)

    if(args.fighters):
        args.destination += fighter_locations()

    if(args.blind_warps):
        args.destination += blind_warps()

    if(args.fedspace):
        fedSpace = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
        starDock = None
        try:
            conn = database.cursor()
            for sd in conn.execute('SELECT value FROM settings WHERE key=?', ('stardock',)):
                starDock = int(sd[0])
            conn.close()
        except:
            pass
        if(starDock):
            fedSpace.append(starDock)
        args.destination += fedSpace

    if(args.port_type):
        if(not re.match('^[BbSs?]{3}$', args.port_type)):
                raise argparse.ArgumentTypeError('Enter a 3 character code consisting only of "?", "B", or "S", e.g., "S?B" for a port that sells Fuel Ore and buys Equipment.')
        args.destination += port_search(args.port_type, args.avoids)

    if(args.dead_ends):
        args.destination += deadend_search(args.avoids)

    results = dijkstra(args.start, args.destination, reverse=args.reverse, avoids=args.avoids, return_all=args.all)
    for result in results:
        result = [str(s) for s in result]
        print(' > '.join(result), "\t({} hops)".format(len(result)-1))
    if(len(results) == 0):
        print('No route found.')

