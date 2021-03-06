
import DTCProtocol_pb2 as DTC
import socket
import struct
import json
from threading import Thread, Timer, Lock
from queue import Queue
import time
from datetime import datetime
from termcolor import colored
import colorama
import  asyncio as aio
import aiofiles
import argparse
colorama.init()

class DTCClient:

    HEARTBEAT_INTERNAL = 10

    def __init__(self, ignore_heartbeat = True):
        self.ip_addr = None
        self.port = None
        self.lock = Lock()
        self.msg_q = Queue(4096)
        self.json_q = Queue(4096)
        self.receiver_thread = None
        self.message_thread = None
        self.heartbeat_timer = None
        self.ignore_heartbeat = ignore_heartbeat

    def send_json_request(self, json_obj):
        req = json.dumps(json_obj).encode("ascii");
        self.lock.acquire()
        self.sock.sendall(req + b"\x00")
        self.lock.release()

    def receiver(self):
        try:
            while True:
                msg = self.sock.recv(4096)
                if len(msg) == 0:
                    print(colored("Receiver handler done", 'green'));
                    break
                self.msg_q.put(msg)
        except Exception as err:
            print(colored("Receiver handler failed - %s" % repr(err), 'red'));

        # final signal for message handler to exit
        self.msg_q.put(b'')

    def message_to_json(self):

        msg = b''

        while True:

            msg += self.msg_q.get()

            if msg == b'':
                break

            while True:
                index = msg.find(b'\x00')
                if index != -1:
                    obj = json.loads(msg[0 : index].decode(encoding = 'ascii'))
                    if self.ignore_heartbeat and obj['Type'] == 3:
                        pass
                    else:
                        self.json_q.put(obj);
                    msg = msg[index + 1:]
                else:
                    break

        print(colored("Message handler done", 'green'));

    def recv_json_response(self):
        msg = '';
        while True:
            c = self.sock.recv(1);
            if c == b'\x00':
                break;
            msg += c.decode(encoding="ascii");
        return json.loads(msg);

    def _heartbeat(self):
        try:
            while True:
                time.sleep(10)
                self.send_json_request({ "Type": DTC.HEARTBEAT });
        except Exception as err:
            print(colored("Heartbeat failed - %s" % repr(err), 'red'));

    def connect(self, ip_addr, port):

        self.ip_addr = ip_addr
        self.port = port
        self.sock = socket.create_connection((ip_addr, port))


    def logon(self, username, password, name = "hello"):
        req = {
            "Type": DTC.LOGON_REQUEST,
            "ProtocolVersion": DTC.CURRENT_VERSION,
            "Username": username,
            "Password": password,
            "HeartbeatIntervalInSeconds": 5,
            "ClientName": name
        }

        self.send_json_request(req);

        # start heartbeat after logon has been sent
        self.heartbeat_timer = Thread(target=self._heartbeat, daemon = True)
        self.heartbeat_timer.start()

        self.receiver_thread = Thread(target=self.receiver, daemon = True)
        self.receiver_thread.start()

        self.message_thread = Thread(target=self.message_to_json, daemon = True)
        self.message_thread.start()

    def close(self):

        if self.sock:
            self.sock.close()

    def run(self, handler):

        while True:
            res = self.json_q.get()
            handler(res)


class DTCClientAsync:

    HEARTBEAT_INTERNAL = 10

    def __init__(self, decode_message=True, ignore_heartbeat=True):
        self.ip_addr = None
        self.port = None
        self.queue = aio.Queue()
        self.sock_reader = None
        self.sock_writter = None
        self.heartbeat_task = None
        self.ignore_heartbeat = ignore_heartbeat if decode_message else False
        self.decode_message = decode_message

    async def send_json_request(self, json_obj):
        req = json.dumps(json_obj).encode("ascii");
        self.sock_writter.write(req + b"\x00")
        await self.sock_writter.drain()

    async def receiver(self):

        try:
            while True:
                msg = await self.sock_reader.readuntil(b'\x00')
                if len(msg) == 0:
                    print(colored("Receiver handler done", 'green'));
                    break
                assert(msg[-1] == 0)
                if self.decode_message:
                    obj = json.loads(msg[:-1].decode(encoding='ascii'))
                    if self.ignore_heartbeat and obj['Type'] == 3:
                        continue
                    await self.queue.put(obj)
                else:
                    await self.queue.put(msg)
        except Exception as err:
            #print(colored("Receiver handler failed - %s" % repr(err), 'red'));
            pass

        await self.queue.put(b'')
        print(colored("Receiver exiting", 'red'));

    async def _heartbeat(self):
        try:
            while True:
                await aio.sleep(self.HEARTBEAT_INTERNAL)
                await self.send_json_request({ "Type": DTC.HEARTBEAT });
        except Exception as err:
            #print(colored("Heartbeat failed - %s" % repr(err), 'red'));
            pass

    async def set_encoding_to_json(self):
        _type = DTC.ENCODING_REQUEST.to_bytes(2, byteorder='little', signed=True)
        pv = DTC.CURRENT_VERSION.to_bytes(4, byteorder='little', signed=True)
        encoding = DTC.JSON_ENCODING.to_bytes(4, byteorder='little', signed=True)
        pt = b'DTC\x00'
        size = 2 + len(_type) + len(pv) + len(encoding) + len(pt)
        assert(size == 16)
        size = size.to_bytes(2, byteorder='little', signed=True)

        req = size + _type + pv + encoding + pt
        self.sock_writter.write(req)
        await self.sock_writter.drain()
        res = await self.sock_reader.read(16)
        assert(res == b'\x10\x00\x07\x00\x08\x00\x00\x00\x02\x00\x00\x00DTC\x00')

    async def connect(self, ip_addr, port):

        self.ip_addr = ip_addr
        self.port = port
        self.sock_reader, self.sock_writter = await aio.open_connection(ip_addr, port)
        await self.set_encoding_to_json()


    async def logon(self, username, password, name = "hello"):
        req = {
            "Type": DTC.LOGON_REQUEST,
            "ProtocolVersion": DTC.CURRENT_VERSION,
            "Username": username,
            "Password": password,
            "HeartbeatIntervalInSeconds": 5,
            "ClientName": name
        }

        await self.send_json_request(req);

        # start heartbeat after logon has been sent
        loop = aio.get_event_loop()
        self.heartbeat_task = loop.create_task(self._heartbeat())
        self.receiver_task = loop.create_task(self.receiver())

    async def close(self):
        try:
            if not self.heartbeat_task.done():
                self.heartbeat_task.cancel()
            await self.heartbeat_task
        except aio.CancelledError:
            pass
        try:
            if not self.receiver_task.done():
                self.receiver_task.cancel()
            await self.receiver_task
        except aio.CancelledError:
            pass

        if self.sock_writter:
            self.sock_writter.close()
            await self.sock_writter.wait_closed()

        await self.queue.put(b'')

    async def messages(self):

        while True:
            res = await self.queue.get()
            if res == b'':
                return
            yield res


async def main():

    parser = argparse.ArgumentParser()
    parser.add_argument('--address', "-a", default="192.168.122.142", help="IP Address of Sierra Chart instance")
    parser.add_argument('--port', "-p", type=int, default=11199, help="Port number of Sierra Chart instance")
    parser.add_argument('--symbol', "-s", required=True, help="Symbol Name")
    parser.add_argument('--exchange', "-e", default="CME", help="Exchange Name")
    parser.add_argument('--logFile', "-f", default='async-client.log', help="Output file name")
    parser.add_argument('--append', default=False, action='store_true', help="Do we append to output file?")

    args = parser.parse_args()

    ADDR = args.address
    PORT = args.port
    SYMBOL = args.symbol
    EXCHANGE = args.exchange

    username = 'dtc_client'
    password = 'password'

    dtc = DTCClientAsync(True, True)
    await dtc.connect(ADDR, PORT)
    await dtc.logon(username, password)

    await dtc.send_json_request({
        "Type": DTC.MARKET_DATA_REQUEST,
        "RequestAction": DTC.SUBSCRIBE,
        "SymbolID": 1,
        "Symbol": SYMBOL,
        "Exchange": EXCHANGE
    })

    await dtc.send_json_request({
        "Type": DTC.MARKET_DEPTH_REQUEST,
        "RequestAction": DTC.SUBSCRIBE,
        "SymbolID": 1,
        "Symbol": SYMBOL,
        "Exchange": EXCHANGE,
        "NumLevels": 100
    })

    mode = 'a' if args.append else 'w'
    async with aiofiles.open(args.logFile, mode) as log:
        async for message in dtc.messages():
            await log.write(json.dumps(message) + '\n')
            await log.flush()

if __name__ == '__main__':
    try:
        loop = aio.get_event_loop()
        loop.run_until_complete(main())
    except KeyboardInterrupt:
        print('Exiting')
