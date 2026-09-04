import json
import sqlite3
from dataclasses import dataclass


@dataclass(frozen=True)
class EnchantRow:
    """enchant_tables裡的一列(一個table+slot下的其中一個詞條option)。

    刻意不去重、不做任何聚合 — M3 §7.5的機率分母是「該(table,slot)實際權重
    總和」, 資料源裡本來就可能有重複列(同一option被來源.lua重複列出多次),
    這是資料驅動分母設計刻意要吸收的情況, 讀取層不能自作主張dedupe。
    """
    slot_index: int
    require_cost: str | None
    option_internal_name: str
    option_weight: int


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

    def enchant_table_for_item(self, internal_name: str) -> int | None:
        """查item internal_name所屬的自動附魔table_index, 查無回傳None。

        target_internal_names欄位存的是JSON陣列字串(如'["Lunar_E_Armor_LT"]'),
        用LIKE比對'"name"'子字串來判斷「在陣列裡」— 不逐列把JSON parse出來
        比對, 是因為一個table常有數百列(每列一個詞條option), 用SQL LIKE直接
        在DB端篩掉不相關列, 比Python端逐列json.loads划算得多。多個table撞到
        同一item(理論上不該發生)時取table_index最小的一筆, 保持穩定。
        """
        cursor = self._conn.cursor()
        cursor.execute(
            "SELECT DISTINCT table_index FROM enchant_tables"
            " WHERE target_internal_names LIKE ? ORDER BY table_index LIMIT 1",
            (f'%"{internal_name}"%',),
        )
        row = cursor.fetchone()
        return row[0] if row else None

    def enchant_rows(self, table_index: int) -> list[EnchantRow]:
        """撈table_index底下所有列, 依slot_index降冪排序(附魔由大槽往小槽的
        資料驅動slot順序, spec §7.5)。同slot內部照插入順序(id)排列, 不去重。
        """
        cursor = self._conn.cursor()
        cursor.execute(
            "SELECT slot_index, require_cost, option_internal_name, option_weight"
            " FROM enchant_tables WHERE table_index=? ORDER BY slot_index DESC, id",
            (table_index,),
        )
        return [
            EnchantRow(
                slot_index=r[0],
                require_cost=r[1],
                option_internal_name=r[2],
                option_weight=r[3],
            )
            for r in cursor.fetchall()
        ]

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
