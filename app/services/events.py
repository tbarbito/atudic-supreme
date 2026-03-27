import queue
import threading

class EventManager:
    def __init__(self):
        self.clients = []
        self.lock = threading.Lock()

    def subscribe(self):
        q = queue.Queue()
        with self.lock:
            self.clients.append(q)
        return q

    def unsubscribe(self, q):
        with self.lock:
            self.clients.remove(q)

    def broadcast(self, message):
        with self.lock:
            for q in self.clients:
                q.put(message)

# Instância global para ser importada
event_manager = EventManager()
