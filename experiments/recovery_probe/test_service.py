import socket
import unittest
from runtime.service import require_ports_available

class PortPreflightTest(unittest.TestCase):
    def test_live_listener_remains_blocked(self):
        with socket.socket() as server:
            server.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1)
            server.bind(('127.0.0.1',0));server.listen()
            with self.assertRaises(OSError):require_ports_available([server.getsockname()[1]])

    def test_stopped_listener_time_wait_is_not_active(self):
        with socket.socket() as server:
            server.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1)
            server.bind(('127.0.0.1',0));server.listen();port=server.getsockname()[1]
            with socket.create_connection(('127.0.0.1',port),timeout=2) as client:
                with server.accept()[0] as accepted:
                    accepted.shutdown(socket.SHUT_WR)
                    self.assertEqual(client.recv(1),b'')
        with socket.socket() as plain:
            with self.assertRaises(OSError):plain.bind(('127.0.0.1',port))
        require_ports_available([port])

if __name__=='__main__':unittest.main()
