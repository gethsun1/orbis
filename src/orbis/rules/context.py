"""Bounded canonical source retrieval for PostgreSQL-backed evaluation callers."""


class ContextRepository:
    def __init__(self, connection): self.db = connection

    def block_manifest(self, network_id: int, from_block: int, to_block: int) -> list[dict]:
        if from_block < 0 or to_block < from_block: raise ValueError("invalid explicit block bounds")
        rows = self.db.execute("""SELECT number,hash,parent_hash,timestamp FROM blocks
            WHERE network_id=%s AND number BETWEEN %s AND %s AND canonical ORDER BY number""",
            (network_id,from_block,to_block)).fetchall()
        return [dict(row) for row in rows]

    def logs(self, network_id: int, from_block: int, to_block: int) -> list[dict]:
        if from_block < 0 or to_block < from_block: raise ValueError("invalid explicit block bounds")
        rows = self.db.execute("""SELECT l.block_number,l.block_hash,l.transaction_hash,l.log_index,l.address,l.topics,l.data
            FROM logs l JOIN blocks b ON (b.network_id,b.number,b.hash)=(l.network_id,l.block_number,l.block_hash)
            WHERE l.network_id=%s AND l.block_number BETWEEN %s AND %s AND b.canonical
            ORDER BY l.block_number,l.transaction_hash,l.log_index""",(network_id,from_block,to_block)).fetchall()
        return [dict(row) for row in rows]
