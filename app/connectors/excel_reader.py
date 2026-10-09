import zipfile
import xml.etree.ElementTree as ET
from typing import Dict, List, Any, Optional, Tuple, Union, BinaryIO
import io
import pyarrow as pa

_XLS_MAGIC = b"\xd0\xcf\x11\xe0"
_ZIP_MAGIC = b"PK"
_INT64_MIN = -2**63
_INT64_MAX = 2**63 - 1


def _local(tag: str) -> str:
    if not isinstance(tag, str):
        return ""
    return tag.rsplit("}", 1)[-1]


def _attr(el: ET.Element, name: str) -> Optional[str]:
    for key, val in el.attrib.items():
        if _local(key) == name:
            return val
    return None


class FastExcelReader:
    """XLSX-to-Arrow reader.

    Worksheet XML is parsed incrementally. The returned Arrow table still holds
    every loaded row; legacy .xls (BIFF) workbooks are rejected.
    """

    @staticmethod
    def _col_letter_to_index(col_str: str) -> int:
        """Convert Excel column letters (A, B, ..., Z, AA, AB) to 0-based integer index."""
        result = 0
        for char in col_str:
            result = result * 26 + (ord(char.upper()) - ord("A") + 1)
        return result - 1

    @staticmethod
    def _open_source(file_source: Union[str, bytes, io.BytesIO]) -> Tuple[BinaryIO, bool]:
        if isinstance(file_source, bytes):
            return io.BytesIO(file_source), True
        if isinstance(file_source, io.BytesIO):
            return file_source, False
        return open(file_source, "rb"), True

    @staticmethod
    def _reject_non_xlsx(handle: BinaryIO) -> None:
        pos = handle.tell() if handle.seekable() else None
        head = handle.read(8)
        if pos is not None:
            handle.seek(pos)
        if head.startswith(_XLS_MAGIC):
            raise ValueError(
                "Legacy Excel .xls (BIFF) is not supported. Save the workbook as .xlsx and import again."
            )
        if not head.startswith(_ZIP_MAGIC):
            raise ValueError(
                "Not a valid .xlsx workbook (expected a ZIP package). Legacy .xls is not supported."
            )

    @classmethod
    def _element_text(cls, el: ET.Element) -> str:
        """Visible text of a shared-string or inline-string node, skipping phonetic runs."""
        parts: List[str] = []

        def walk(node: ET.Element) -> None:
            name = _local(node.tag)
            if name in ("rPh", "phoneticPr"):
                return
            if name == "t" and node.text:
                parts.append(node.text)
            for child in list(node):
                walk(child)

        walk(el)
        return "".join(parts)

    @classmethod
    def _load_shared_strings(cls, z: zipfile.ZipFile) -> List[str]:
        """Parse xl/sharedStrings.xml into a string lookup list."""
        if "xl/sharedStrings.xml" not in z.namelist():
            return []
        shared_strings: List[str] = []
        with z.open("xl/sharedStrings.xml") as handle:
            for _event, el in ET.iterparse(handle, events=("end",)):
                if _local(el.tag) != "si":
                    continue
                shared_strings.append(cls._element_text(el))
                el.clear()
        return shared_strings

    @classmethod
    def _workbook_sheets(cls, z: zipfile.ZipFile) -> List[Tuple[str, Optional[str]]]:
        """Return (sheet name, relationship id) in workbook order."""
        if "xl/workbook.xml" not in z.namelist():
            return [("Sheet1", None)]
        with z.open("xl/workbook.xml") as handle:
            root = ET.parse(handle).getroot()
        sheets: List[Tuple[str, Optional[str]]] = []
        for el in root.iter():
            if _local(el.tag) != "sheet":
                continue
            sheets.append((_attr(el, "name") or f"Sheet{len(sheets) + 1}", _attr(el, "id")))
        return sheets or [("Sheet1", None)]

    @classmethod
    def _rel_targets(cls, z: zipfile.ZipFile) -> Dict[str, str]:
        """Map workbook relationship ids to worksheet XML paths."""
        rels_path = "xl/_rels/workbook.xml.rels"
        if rels_path not in z.namelist():
            return {}
        with z.open(rels_path) as handle:
            root = ET.parse(handle).getroot()
        targets: Dict[str, str] = {}
        for el in root.iter():
            if _local(el.tag) != "Relationship":
                continue
            rel_type = _attr(el, "Type") or ""
            if rel_type and not rel_type.endswith("/worksheet"):
                continue
            rid = _attr(el, "Id")
            target = _attr(el, "Target")
            if not rid or not target:
                continue
            target = target.split("?", 1)[0].replace("\\", "/").lstrip("/")
            if target.startswith("../"):
                target = target[3:]
            if not target.startswith("xl/"):
                target = "xl/" + target
            targets[rid] = target
        return targets

    @classmethod
    def list_sheet_names(cls, z: zipfile.ZipFile) -> List[str]:
        """List all worksheet names in the workbook."""
        return [name for name, _rid in cls._workbook_sheets(z)]

    @classmethod
    def list_sheets(cls, file_source: Union[str, bytes, io.BytesIO]) -> List[str]:
        handle, own = cls._open_source(file_source)
        try:
            cls._reject_non_xlsx(handle)
            try:
                with zipfile.ZipFile(handle) as zf:
                    return cls.list_sheet_names(zf)
            except zipfile.BadZipFile as exc:
                raise ValueError(f"Invalid .xlsx package: {exc}") from exc
        finally:
            if own:
                handle.close()

    @classmethod
    def _resolve_sheet_path(
        cls,
        z: zipfile.ZipFile,
        sheet_name: Optional[str],
        sheet_index: int,
    ) -> str:
        sheets = cls._workbook_sheets(z)
        names = [name for name, _rid in sheets]
        # import_excel_or_csv passes the literal "Sheet1" when the caller omits a
        # sheet. Keep that alias as "first sheet" so existing imports still load.
        if sheet_name and sheet_name in names:
            idx = names.index(sheet_name)
        elif sheet_name and sheet_name != "Sheet1":
            raise ValueError(f"Sheet {sheet_name!r} not found. Available: {names}")
        else:
            idx = sheet_index if 0 <= sheet_index < len(sheets) else 0
        _name, rid = sheets[idx]
        rels = cls._rel_targets(z)
        if rid and rels.get(rid) in z.namelist():
            return rels[rid]
        fallback = f"xl/worksheets/sheet{idx + 1}.xml"
        if fallback in z.namelist():
            return fallback
        sheet_files = sorted(
            n for n in z.namelist()
            if n.startswith("xl/worksheets/sheet") and n.endswith(".xml")
        )
        if not sheet_files:
            raise ValueError("No worksheets found in XLSX file.")
        if idx < len(sheet_files):
            return sheet_files[idx]
        return sheet_files[0]

    @staticmethod
    def _parse_number(val: str) -> Any:
        try:
            if any(ch in val for ch in ".eE"):
                return float(val)
            number = int(val)
        except ValueError:
            return val
        if number < _INT64_MIN or number > _INT64_MAX:
            return val
        return number

    @classmethod
    def _cell_value(cls, cell: ET.Element, shared_strings: List[str]) -> Any:
        cell_type = _attr(cell, "t") or "n"
        if cell_type == "inlineStr":
            text = cls._element_text(cell)
            return text or None
        raw = None
        for child in list(cell):
            if _local(child.tag) == "v":
                raw = child.text
                break
        if raw is None:
            return None
        if cell_type == "s":
            try:
                idx = int(raw)
            except ValueError:
                return raw
            if 0 <= idx < len(shared_strings):
                return shared_strings[idx]
            return raw
        if cell_type == "b":
            return raw == "1"
        if cell_type in ("str", "e"):
            return raw
        return cls._parse_number(raw)

    @staticmethod
    def _column_array(values: List[Any]) -> pa.Array:
        present = [v for v in values if v is not None]
        if not present:
            return pa.array(values, type=pa.string())
        kinds = {type(v) for v in present}
        if kinds <= {bool}:
            return pa.array(values, type=pa.bool_())
        if kinds <= {int}:
            return pa.array(values, type=pa.int64())
        if kinds <= {int, float}:
            coerced = [None if v is None else float(v) for v in values]
            return pa.array(coerced, type=pa.float64())
        as_text = [None if v is None else str(v) for v in values]
        return pa.array(as_text, type=pa.string())

    @classmethod
    def read_xlsx_to_arrow(
        cls,
        file_source: Union[str, bytes, io.BytesIO],
        sheet_name: Optional[str] = None,
        sheet_index: int = 0,
        has_header: bool = True,
        limit_rows: Optional[int] = None,
    ) -> pa.Table:
        """Parse one XLSX sheet into a PyArrow table."""
        if limit_rows is not None and int(limit_rows) < 0:
            raise ValueError("limit_rows must be >= 0")
        handle, own = cls._open_source(file_source)
        try:
            cls._reject_non_xlsx(handle)
            try:
                with zipfile.ZipFile(handle) as zf:
                    return cls._read_zip(zf, sheet_name, sheet_index, has_header, limit_rows)
            except zipfile.BadZipFile as exc:
                raise ValueError(f"Invalid .xlsx package: {exc}") from exc
        finally:
            if own:
                handle.close()

    @classmethod
    def _read_zip(
        cls,
        zf: zipfile.ZipFile,
        sheet_name: Optional[str],
        sheet_index: int,
        has_header: bool,
        limit_rows: Optional[int],
    ) -> pa.Table:
        shared_strings = cls._load_shared_strings(zf)
        sheet_xml_path = cls._resolve_sheet_path(zf, sheet_name, sheet_index)
        rows_data: List[List[Any]] = []
        max_cols = 0
        stop_at = None if limit_rows is None else limit_rows + (1 if has_header else 0)

        with zf.open(sheet_xml_path) as sheet_f:
            for _event, el in ET.iterparse(sheet_f, events=("end",)):
                if _local(el.tag) != "row":
                    continue
                row_cells: Dict[int, Any] = {}
                for cell in list(el):
                    if _local(cell.tag) != "c":
                        continue
                    ref = _attr(cell, "r") or ""
                    letters = "".join(ch for ch in ref if ch.isalpha())
                    if not letters:
                        continue
                    row_cells[cls._col_letter_to_index(letters)] = cls._cell_value(cell, shared_strings)
                if row_cells:
                    curr_max = max(row_cells) + 1
                    if curr_max > max_cols:
                        max_cols = curr_max
                    rows_data.append([row_cells.get(i) for i in range(max_cols)])
                el.clear()
                if stop_at is not None and len(rows_data) >= stop_at:
                    break

        if not rows_data:
            return pa.table({})

        for row in rows_data:
            if len(row) < max_cols:
                row.extend([None] * (max_cols - len(row)))

        if has_header:
            headers = [
                str(h) if h is not None and str(h).strip() else f"col_{i + 1}"
                for i, h in enumerate(rows_data[0])
            ]
            seen: Dict[str, int] = {}
            final_headers: List[str] = []
            for header in headers:
                if header in seen:
                    seen[header] += 1
                    final_headers.append(f"{header}_{seen[header]}")
                else:
                    seen[header] = 0
                    final_headers.append(header)
            data_rows = rows_data[1:]
        else:
            final_headers = [f"col_{i + 1}" for i in range(max_cols)]
            data_rows = rows_data

        columns = {header: [] for header in final_headers}
        for row in data_rows:
            for i, header in enumerate(final_headers):
                columns[header].append(row[i] if i < len(row) else None)
        arrays = [cls._column_array(columns[header]) for header in final_headers]
        return pa.Table.from_arrays(arrays, names=final_headers)
