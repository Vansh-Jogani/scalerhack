"""MapStateManager — batches all GeoJSON writes on 1s interval. Stub for Stage 1."""


class MapStateManager:
    def __init__(self):
        self.pending_updates = []

    def queue_update(self, geojson: dict):
        self.pending_updates.append(geojson)

    def flush(self) -> list[dict]:
        updates = self.pending_updates[:]
        self.pending_updates.clear()
        return updates
