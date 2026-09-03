import json
import sqlite3
from dataclasses import dataclass


@dataclass(frozen=True)
class ItemRecord:
    """Represents a single item record from the database."""
    item_id: int
    internal_name: str | None
    display_name: str | None
    description: str
    slot_count: int | None
    equip_type: str | None
    stat_vector: list | None
    onstart_equip_src: str | None
    combi_ids: list[int] | None


class DbReader:
    """Read layer over data/ro_items.db.

    Handles JSON decoding for json-TEXT fields and returns None for missing rows.
    """

    def __init__(self, db_path: str):
        """Initialize DbReader with a database path.

        Args:
            db_path: Path to the SQLite database file.
        """
        self._conn = sqlite3.connect(db_path)

    def close(self) -> None:
        """Close the database connection."""
        self._conn.close()

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()
        return False

    def item(self, item_id: int) -> ItemRecord | None:
        """Retrieve an item by item_id.

        Args:
            item_id: The item ID to search for.

        Returns:
            ItemRecord if found, None otherwise.
        """
        cursor = self._conn.cursor()
        cursor.execute(
            "SELECT item_id, internal_name, display_name, description,"
            " slot_count, equip_type, stat_vector, onstart_equip_src, combi_ids"
            " FROM items WHERE item_id=?",
            (item_id,),
        )
        row = cursor.fetchone()
        if not row:
            return None

        return self._row_to_item_record(row)

    def item_by_internal_name(self, name: str) -> ItemRecord | None:
        """Retrieve an item by internal_name.

        Args:
            name: The internal name to search for.

        Returns:
            ItemRecord if found, None otherwise.
        """
        cursor = self._conn.cursor()
        cursor.execute(
            "SELECT item_id, internal_name, display_name, description,"
            " slot_count, equip_type, stat_vector, onstart_equip_src, combi_ids"
            " FROM items WHERE internal_name=?",
            (name,),
        )
        row = cursor.fetchone()
        if not row:
            return None

        return self._row_to_item_record(row)

    def combo(self, combo_id: int) -> tuple[list[int], str | None] | None:
        """Retrieve a combo by combo_id.

        Args:
            combo_id: The combo ID to search for.

        Returns:
            Tuple of (member_item_ids, onstart_src) if found, None otherwise.
        """
        cursor = self._conn.cursor()
        cursor.execute(
            "SELECT member_item_ids, onstart_src FROM combos WHERE combo_id=?",
            (combo_id,),
        )
        row = cursor.fetchone()
        if not row:
            return None

        member_item_ids_str, onstart_src = row
        member_item_ids = json.loads(member_item_ids_str) if member_item_ids_str else None
        return (member_item_ids, onstart_src)

    def _row_to_item_record(self, row) -> ItemRecord:
        """Convert a database row to ItemRecord.

        Handles JSON decoding for stat_vector and combi_ids fields.

        Args:
            row: A tuple from the database query.

        Returns:
            ItemRecord instance.
        """
        (
            item_id,
            internal_name,
            display_name,
            description,
            slot_count,
            equip_type,
            stat_vector_str,
            onstart_equip_src,
            combi_ids_str,
        ) = row

        # Decode JSON fields
        stat_vector = json.loads(stat_vector_str) if stat_vector_str else None
        combi_ids = json.loads(combi_ids_str) if combi_ids_str else None

        return ItemRecord(
            item_id=item_id,
            internal_name=internal_name,
            display_name=display_name,
            description=description,
            slot_count=slot_count,
            equip_type=equip_type,
            stat_vector=stat_vector,
            onstart_equip_src=onstart_equip_src,
            combi_ids=combi_ids,
        )
