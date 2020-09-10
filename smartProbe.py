#!/usr/bin/python3

import sqlite3
import argparse
import queue

database = None
DEFAULT_DB_NAME = 'tw2002.db'

explored = None

def connect_database(filename):
    global database
    database = sqlite3.connect(filename)

def deadend_sectors():
    global database
    sourcemap = {}
    destmap = {}
    conn = database.cursor()
    for source,dest in conn.execute('SELECT source, destination FROM warps'):
        if(not source in sourcemap):
            sourcemap[source] = []
        sourcemap[source].append(dest)

        if(not dest in destmap):
            destmap[dest] = []
        destmap[dest].append(source)
    conn.close()
    dead_ends = []
    for sector in sourcemap:
        try:
            if((len(sourcemap[sector]) == 1) and (len(destmap[sector]) == 1)):
                dead_ends.append(sector)
        except:
            pass
    return dead_ends

def explored_sectors():
    global database
    conn = database.cursor()
    retval = [int(s[0]) for s in conn.execute('SELECT sector FROM explored')]
    conn.close()
    return retval

def fighter_locations():
    global database
    conn = database.cursor()
    query = conn.execute("SELECT sector FROM fighters")
    retval = [int(sector[0]) for sector in query]
    conn.close()
    return retval

def list_all_sectors():
    global database
    conn = database.cursor()
    query = conn.execute("SELECT DISTINCT source FROM warps")
    retval = [int(sector[0]) for sector in query]
    conn.close()
    # print("list_all_sectors", retval)
    return retval

def warps_from(sector):
    global database
    conn = database.cursor()
    query = conn.execute("SELECT destination FROM warps WHERE source=?", (sector,))
    retval = [int(warp[0]) for warp in query]
    conn.close()
    # print("warps_from", sector, "=", retval)
    return retval

def warps_to(sector):
    global database
    conn = database.cursor()
    query = conn.execute("SELECT source FROM warps WHERE destination=?", (sector,))
    retval = [int(warp[0]) for warp in query]
    conn.close()
    # print("warps_from", sector, "=", retval)
    return retval

def backtrace(parent, start, end):
    path = [end]
    while(path[-1] != start):
        path.append(parent[path[-1]])
    path.reverse()
    return path

class Sector:
    sector = None
    warps = None
    path = None

    def __init__(self, sector, path=[]):
        self.sector = sector
        self.warps = warps_from(sector)
        self.path = path

    def __repr__(self):
        return "Sector({}, warps={}, path={})".format(self.sector, self.warps, self.path)

MAX_WARPS = 20
MAX_EXPLORED = 11

def path_walker(start_vertex, end_vertices, avoids=[]):
    explored = explored_sectors()

    if(end_vertices != None and not isinstance(end_vertices, list)):
        end_vertices = [end_vertices]

    lifo = queue.LifoQueue()

    lifo.put(Sector(start_vertex))

    results = []
    maxCnt = 0
    deCnt = 0
    maxExplored = 0
    while(not lifo.empty()):
        # if((maxExplored + maxCnt + deCnt) % 10000 == 0):
        #     print(lifo.qsize(), maxExplored, maxCnt, deCnt)

        sector = lifo.get()
        if(sector.sector in avoids):
            continue
        if(explored_cnt(sector.path) > MAX_EXPLORED):
            maxExplored += 1
            continue
        if(len(sector.path) > MAX_WARPS):
            maxCnt += 1
            if(end_vertices == None or sector.sector in end_vertices):
                results.append((unexplored_cnt(sector.path + [sector.sector]), "max", sector))
            continue
        newPaths = False
        for warp in sector.warps:
            if(not warp in sector.path):
                lifo.put(Sector(warp, path=sector.path + [sector.sector]))
                newPaths = True
        if(not newPaths):
            # print(sector)
            if(end_vertices == None or sector.sector in end_vertices):
                results.append((unexplored_cnt(sector.path + [sector.sector]), "de", sector))
            deCnt += 1

    # print(maxExplored, maxCnt, deCnt)
    # for x in range(10):
    #    print(results[int(x*len(results)/10)])
    maxUnexplored = 0
    for r in results:
        if(r[0] > maxUnexplored):
            maxUnexplored = r[0]

    # print(maxUnexplored)

    retval = []
    for result in sorted(list(results), key=lambda r: r[0]):
    # for r in sorted(list(results), key=lambda r: results[r][1]):
        if(result[0] > (maxUnexplored-3)):
            # print(result)
            sector = result[2]
            retval.append(sector.path + [sector.sector])
    return retval



# inspired by http://pythonfiddle.com/dijkstra/
# modified to use a weighted algorithm
def weighted_dijkstra(start_vertex, end_vertices, avoids=[]):
    
    explored = explored_sectors()

    list_all = list_all_sectors()

    if(end_vertices == None):
        end_vertices = list_all

    if(not isinstance(end_vertices, list)):
        end_vertices = [end_vertices]
    distance = {}
    visited = {}
    parent = {}
    shortest_distance = {}
    weight = {}

    retVal = []

    for node in list_all:
        visited[node] = False
        parent[node] = None
        shortest_distance[node] = float('inf')
        weight[node] = 0
        if(node in explored):
            weight[node] = 100

        if(node in avoids):
            visited[node] = True

    shortest_distance[start_vertex] = 0
    current = None
    while(True):
        choices = {s:shortest_distance[s] for s in shortest_distance if visited[s] == False and shortest_distance[s] < float('inf')}
        # print(choices)
        choices = sorted(choices.keys(), key=lambda s: choices[s])
        # print(choices)
        if(len(choices)==0):
            break
        current = choices[0]
        # print('')
        # print("current", current)
        visited[current] = True
        warp_list = warps_from(current)
        for neighbor in warp_list:
            # print("neighbor", neighbor)
            prospective_distance = shortest_distance[current] + weight[neighbor]
            if(prospective_distance < shortest_distance[neighbor]):
                shortest_distance[neighbor] = prospective_distance
                parent[neighbor] = current
    for v in end_vertices:
        retVal.append(backtrace(parent, start_vertex, v))
    return retVal

def sector_representation(sector):
    global explored
    if(explored == None):
        explored = explored_sectors()
    if(sector in explored):
        return str(sector)
    return "({})".format(sector)

def explored_cnt(route):
    global explored
    if(explored == None):
        explored = explored_sectors()
    cnt = 0
    for sector in route:
        if(sector in explored):
            cnt += 1
    return cnt

def unexplored_cnt(route):
    global explored
    if(explored == None):
        explored = explored_sectors()
    cnt = 0
    for sector in route:
        if(sector not in explored):
            cnt += 1
    return cnt


if(__name__ == '__main__'):
    parser = argparse.ArgumentParser(description='Tool that will attempt to plan an Ether Probe path to an Unexplored dead end that will hit as many Unexplored sectors as possible en route.')
    parser.add_argument('--database', '-d', dest='db', default=DEFAULT_DB_NAME, help='SQLite database file to use; default "{}"'.format(DEFAULT_DB_NAME))
    parser.add_argument('--thorough', '-t', action='store_true', help='Switch to a more thorough algorithm.  Will likely generate longer paths and find more Unexplored sectors along the route, but is MUCH SLOWER to run')
    parser.add_argument('--top', type=int, default=1, help='Show the top <X> probe destination/routes; default 1')
    parser.add_argument('--all', '-a', action='store_true', help='Treat every sector as a destination, not just Unexplored dead ends')
    parser.add_argument('--avoid', '-v', type=int, nargs='+', default=[], help='Sectors to avoid when plotting probe routes')
    parser.add_argument('--fighters', '-f', action='store_true', help='Set the start_sector list to all sectors that currently have one of your deployed fighters')
    parser.add_argument('--no-trim', '-n', action='store_true', help='Do not trim routes greater than 20 hops')
    parser.add_argument('start_sector', type=int, nargs='*', help='The sector to use as the Ether Probe launching site')

    args = parser.parse_args()

    max_route_len = 21
    if(args.no_trim):
        max_route_len = float('inf')

    mapping_algo = weighted_dijkstra
    if(args.thorough):
        mapping_algo = path_walker

    connect_database(args.db)

    explored = explored_sectors()

    if(args.fighters):
        args.start_sector += fighter_locations()

    candidates = None
    if(not args.all):
        # start with a list of dead ends
        candidates = { sector:None for sector in deadend_sectors() }
        # trim the ones we've already explored
        for sector in list(candidates):
            if(sector in explored):
                del candidates[sector]
        candidates = list(candidates)

    routes = []
    for source in args.start_sector:
        routes += mapping_algo(source, candidates, avoids=args.avoid)
    # print(routes)

    buckets = {}
    usableRoutes = []
    for route in routes:
        new = unexplored_cnt(route)

        if(len(route) <= max_route_len):
            if(not new in buckets):
                buckets[new] = 0
            buckets[new] += 1
            usableRoutes.append(route)

    if(len(routes) != len(usableRoutes)):
        print("Trimmed {} routes that were over {} hops.".format(len(routes) - len(usableRoutes), max_route_len))

    for b in sorted(buckets, key=lambda b: b):
        print("Routes hitting {} new sectors: {}".format(b, buckets[b]))

    print('\nRecommended route:')
    for route in sorted(usableRoutes, key=lambda route: (unexplored_cnt(route),len(route)))[-args.top:]:
        print("new={}".format(unexplored_cnt(route)), "hops={}".format(len(route)-1))
        print(' > '.join([sector_representation(s) for s in route]))

        constraints = []
        for sector in route:
            for warp in warps_from(sector):
                if(warp not in route):
                    constraints.append(warp)
        # get to the Computer menu
        print("Copy/Paste the following to set the probe's route:")
        print("QQQQQQQQQNC")
        # clear avoids
        print("V0\nYY")
        # plot the route as normal
        print("F{}\n{}".format(route[0], route[-1]))
        # set all the avoids to ensure the probe follows our desired route
        print("^")
        for sector in constraints:
            print("S{}".format(sector))
        print("Q")
        # plot the route again to verify that it follows our desired route
        print("F{}\n{}".format(route[0], route[-1]))
        print('')


