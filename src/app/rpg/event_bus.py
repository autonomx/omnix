from collections import defaultdict


class EventBus:
    def __init__(self):
        self.listeners = defaultdict(list)

    def subscribe(self, event_type, handler):
        self.listeners[event_type].append(handler)

    def emit(self, event):
        if hasattr(self, "session"):
            self.session.event_log.append(event)

        for handler in self.listeners[event["type"]]:
            handler(event)


# Global bus (simple version)
event_bus = EventBus()