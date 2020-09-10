# tw2002-client

This is a set of Python 3 scripts that are meant to assist while playing Trade Wars 2002. 
Developed and tested on Debian Linux, Python 3.5.3.  This likely will NOT work under Windows without some modification.

<B>twclient.py</B> is a telnet-emulating client that you use to connect to the game server.  It will read data from the game and use it to populate a SQLite database.  It uses "twparser.py" to parse the data and do the actual databasing.

<B>twparser.py</B> is the main databasing engine.  It will process a log file for you if launched directly, or will parse your session live when using "twclient.py".
Things it reads, currently:
Computer Interrogation Mode (CIM) Warp Display -- lists all sectors you've explored and the warps leading out of each one
Computer Interrogation Mode (CIM) Port Report -- lists all ports in sectors you've explored, and their current levels of each commodity.  Sectors containing hostile fighters will NOT show in this report!
Deployed Fighter Scan -- shows all your personal and corporate deployed fighters
Planet Scan -- both personal and corporate; lists some basic stats about planets owned by you and your team

<B>portPairs.py</B> will read the SQLite database and show you pairs of ports that are in adjacent sectors that Buy/Sell whatever commodity you want to trade.  Also will give you recommendations on how to get there in the most turn-efficient manner, if you have a transwarp drive.

<B>smartProbe.py</B> will use the sector warp mapping data from the SQLite database to generate pathways for Ether Probes, with the goal of hitting as many Unexplored sectors as possible with each probe.  Visiting the sectors with a probe will then allow you to retrieve the port data, greatly expanding your trading options.

<B>twpath.py</B> will use the data in the SQLite database to generate routes to/from: the nearest fighters; the nearest likely blind warps; the nearest port selling <X>.

<B>tw2002.db</B> is my database from an actual game, provided so that you can try out the scripts without having to actually gather your own mapping data first.
