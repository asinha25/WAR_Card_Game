"""
Name: Aditya Sinha
CS 450 - Assignment 3
War card game client and server
"""
import asyncio
from collections import namedtuple
from enum import Enum
import logging
import random
# import socket
# import socketserver
# import threading
import sys

Game = namedtuple("Game", ["p1", "p2"])

QUEUE = asyncio.Queue()


class Command(Enum):
    """
    The byte values sent as the first byte of any message in the war protocol.
    """
    WANTGAME = 0
    GAMESTART = 1
    PLAYCARD = 2
    PLAYRESULT = 3


class Result(Enum):
    """
    The byte values sent as the payload byte of a PLAYRESULT message.
    """
    WIN = 0
    DRAW = 1
    LOSE = 2


def compare_cards(card1, card2):
    """
    TODO: Given an integer card representation, return -1 for card1 < card2,
    0 for card1 = card2, and 1 for card1 > card2
    """
    if (card1 % 13) < (card2 % 13):
        return -1
    elif (card1 % 13) > (card2 % 13):
        return 1
    # else:
    #     return 0


def deal_cards():
    """
    TODO: Randomize a deck of cards (list of ints 0..51), and return two
    26 card "hands."
    """
    cards = list(range(52))
    random.shuffle(cards)
    return cards[:26], cards[26:]


async def play_game(player1, player2):
    """
    play a game between two connected clients who have not
    sent any messages yet...
    """
    def killthis():
        """
        close connection for both clients
        """
        logging.debug("killing game...")
        player1[1].close()
        player2[1].close()
        return

    pl1_hello = await player1[0].readexactly(2)
    pl2_hello = await player2[0].readexactly(2)
    if pl1_hello != b'\0\0' or pl2_hello != b'\0\0':
        killthis()
        return
    pl1_hand, pl2_hand = deal_cards()
    player1[1].write(bytes([1] + pl1_hand))
    player2[1].write(bytes([1] + pl2_hand))
    for hand in range(26):
        # reads in 2 bytes, or else nukes
        pl1_play = await player1[0].readexactly(2)
        pl2_play = await player2[0].readexactly(2)
        # compare and send win or lose
        pl1_card = pl1_play[1]
        pl2_card = pl2_play[1]
        play_result = compare_cards(pl1_card, pl2_card)
        if play_result == -1:
            player1[1].write(bytes([3, 2]))
            player2[1].write(bytes([3, 0]))
            # send "win" to 2 and "lose" to 1
        elif play_result == 1:
            player1[1].write(bytes([3, 0]))
            player2[1].write(bytes([3, 2]))
            # send "win" to 1 and "lose" to 2
        else:
            # draw to both players
            player1[1].write(bytes([3, 1]))
            player2[1].write(bytes([3, 1]))
    killthis()


async def new_player(reader, writer):
    """
    receive a player, if there's another player waiting, then start a new game
    otherwise, hold onto this player until another player shows up...
    """
    if QUEUE.empty():
        await QUEUE.put((reader, writer))
        logging.debug("new client connected - pushed to queue...")
    else:
        # assignment is immediate,
        # queue.get is a coroutine since it might take time
        player1 = await QUEUE.get()
        player2 = (reader, writer)
        await play_game(player1, player2)
        logging.debug("new client connected with waiting client,"
                      "starting game...")


def serve_game(host, port):
    """
    TODO: Open a socket for listening for new connections on host:port, and
    perform the war protocol to serve a game of war between each client.
    This function should run forever, continually serving clients.
    """
    loop = asyncio.get_event_loop()
    coro = asyncio.start_server(new_player, host, port, loop=loop)
    server = loop.run_until_complete(coro)

    logging.debug('Serving on %s', server.sockets[0].getsockname())
    try:
        loop.run_forever()
    except KeyboardInterrupt:
        pass

async def limit_client(host, port, loop, sem):
    """
    Limit the number of clients currently executing.
    You do not need to change this function.
    """
    async with sem:
        return await client(host, port, loop)

async def client(host, port, loop):
    """
    Run an individual client on a given event loop.
    You do not need to change this function.
    """
    try:
        reader, writer = await asyncio.open_connection(host, port, loop=loop)
        # send want game
        writer.write(b"\0\0")
        card_msg = await reader.readexactly(27)
        myscore = 0
        for card in card_msg[1:]:
            writer.write(bytes([Command.PLAYCARD.value, card]))
            result = await reader.readexactly(2)
            if result[1] == Result.WIN.value:
                myscore += 1
            elif result[1] == Result.LOSE.value:
                myscore -= 1
        if myscore > 0:
            result = "won"
        elif myscore < 0:
            result = "lost"
        else:
            result = "drew"
        logging.debug("Game complete, I %s", result)
        writer.close()
        return 1
    except ConnectionResetError:
        logging.error("ConnectionResetError")
        return 0
    except asyncio.streams.IncompleteReadError:
        logging.error("asyncio.streams.IncompleteReadError")
        return 0
    except OSError:
        logging.error("OSError")
        return 0


def main(args):
    """
    launch a client/server
    """
    host = args[1]
    port = int(args[2])
    if args[0] == "server":
        try:
            # your server should serve clients until the user presses ctrl+c
            serve_game(host, port)
        except KeyboardInterrupt:
            pass
        return
    else:
        loop = asyncio.get_event_loop()

    if args[0] == "client":
        loop.run_until_complete(client(host, port, loop))
    elif args[0] == "clients":
        sem = asyncio.Semaphore(1000)
        num_clients = int(args[3])
        clients = [limit_client(host, port, loop, sem)
                   for x in range(num_clients)]
        async def run_all_clients():
            """
            use `as_completed` to spawn all clients simultaneously
            and collect their results in arbitrary order.
            """
            completed_clients = 0
            for client_result in asyncio.as_completed(clients):
                completed_clients += await client_result
            return completed_clients
        res = loop.run_until_complete(
            asyncio.Task(run_all_clients(), loop=loop))
        logging.info("%d completed clients", res)

    loop.close()

if __name__ == "__main__":
    # change to logging.DEBUG to see debug statements...
    logging.basicConfig(level=logging.INFO)
    main(sys.argv[1:])
