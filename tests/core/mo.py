"""Write a GNU .mo file from a dict, for tests that need a real catalog.

Format: https://www.gnu.org/software/gettext/manual/html_node/MO-Files.html
Keys are msgids, or (singular, plural) tuples whose value is the list of
plural translations.
"""

import struct


def write_mo(path, entries, *, plural_forms=None):
    header = "Content-Type: text/plain; charset=UTF-8\n"
    if plural_forms:
        header += f"Plural-Forms: {plural_forms}\n"
    messages = {"": header}
    for key, value in entries.items():
        if isinstance(key, tuple):
            messages["\x00".join(key)] = "\x00".join(value)
        else:
            messages[key] = value
    ids = sorted(messages)
    id_bytes = [i.encode() for i in ids]
    str_bytes = [messages[i].encode() for i in ids]
    count = len(ids)
    table_start = 7 * 4
    ids_start = table_start + count * 16
    offsets, data = [], b""
    for blob in id_bytes + str_bytes:
        offsets.append((len(blob), ids_start + len(data)))
        data += blob + b"\x00"
    out = struct.pack("<7I", 0x950412DE, 0, count, table_start, table_start + count * 8, 0, 0)
    for length, offset in offsets:
        out += struct.pack("<2I", length, offset)
    path.write_bytes(out + data)
