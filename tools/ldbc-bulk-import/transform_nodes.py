#!/usr/bin/env python3
"""
Transforms LDBC SNB node CSVs into the format expected by neo4j-admin import.

LDBC format:  pipe-separated, header row per part file, optional 'type' column
              holding the subtype. Spark splits entities across several part files.
Neo4j format: :ID column, :LABEL column (semicolon-separated), property columns
"""

import gzip
import sys
import os
import glob
from datetime import datetime, timezone

NAMESPACE_LABEL = "___n_4___"

# Columns holding timestamps that should become epoch millis, matching what the
# Cypher-based ingest in the Polypheny simple client produces.
DATE_COLUMNS = {"creationDate", "joinDate", "birthday"}


# Columns that LDBC stores as semicolon-separated lists
ARRAY_COLUMNS = {"language", "email"}

# Columns that should be imported as numbers rather than strings
LONG_COLUMNS = {"creationDate", "joinDate", "birthday", "length", "classYear",
                "workFrom"}


def annotate(column):
    """Adds the neo4j-admin type annotation to a property column name."""
    if column in ARRAY_COLUMNS:
        return f"{column}:string[]"
    if column in LONG_COLUMNS:
        return f"{column}:long"
    return column


def find_input_files(entity_dir):
    matches = glob.glob(os.path.join(entity_dir, "*.csv.gz"))
    if not matches:
        raise FileNotFoundError(f"No .csv.gz found in {entity_dir}")
    return sorted(matches)


def to_epoch_millis(value):
    """LDBC uses ISO-8601 with offset for timestamps and plain dates for birthdays."""
    value = value.strip()
    if not value:
        return ""
    try:
        # e.g. 2010-01-03T15:10:31.499+00:00, but also plain dates like 1984-03-11
        dt = datetime.fromisoformat(value)
        if dt.tzinfo is None:
            # No offset in the source, so interpret it as UTC. This matches
            # EntityHandler.toEpochMillis() in the simple client, which uses
            # ZoneOffset.UTC for date-only values.
            dt = dt.replace(tzinfo=timezone.utc)
        return str(int(dt.timestamp() * 1000))
    except ValueError:
        pass
    try:
        # e.g. 1984-03-11 -- interpreted as UTC midnight, matching the Cypher ingest
        dt = datetime.strptime(value, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        return str(int(dt.timestamp() * 1000))
    except ValueError:
        return value


def transform(entity_dir, base_label, out_path, type_column=None,
              id_column="id", extra_labels=()):
    in_paths = find_input_files(entity_dir)

    rows_written = 0
    out_header = None
    header = None
    id_idx = None
    type_idx = None
    prop_indices = None

    with open(out_path, "w", encoding="utf-8") as fout:
        for part_no, in_path in enumerate(in_paths):
            with gzip.open(in_path, "rt", encoding="utf-8") as fin:
                part_header = fin.readline().rstrip("\n").split("|")

                if header is None:
                    header = part_header
                    if id_column not in header:
                        raise ValueError(f"No '{id_column}' column in {header}")
                    id_idx = header.index(id_column)
                    type_idx = header.index(type_column) if type_column else None
                    prop_indices = [
                        i for i, name in enumerate(header)
                        if i != id_idx and i != type_idx
                    ]
                    out_header = [f":ID({base_label})"]
                    out_header += [annotate(header[i]) for i in prop_indices]
                    out_header.append(":LABEL")
                    fout.write("|".join(out_header) + "\n")
                elif part_header != header:
                    raise ValueError(
                        f"Header mismatch in {in_path}: {part_header} != {header}"
                    )

                for line in fin:
                    fields = line.rstrip("\n").split("|")

                    labels = [NAMESPACE_LABEL, base_label]
                    labels.extend(extra_labels)
                    if type_idx is not None:
                        subtype = fields[type_idx].strip()
                        if subtype:
                            labels.append(subtype)

                    out_fields = [fields[id_idx]]
                    for i in prop_indices:
                        value = fields[i]
                        if header[i] in DATE_COLUMNS:
                            value = to_epoch_millis(value)
                        out_fields.append(value)
                    out_fields.append(";".join(labels))

                    fout.write("|".join(out_fields) + "\n")
                    rows_written += 1

    return rows_written, out_header, len(in_paths)


if __name__ == "__main__":
    if len(sys.argv) < 4:
        print("usage: transform_nodes.py <entity_dir> <base_label> <out_path> "
              "[type_column] [extra_label]")
        sys.exit(1)

    entity_dir = sys.argv[1]
    base_label = sys.argv[2]
    out_path = sys.argv[3]
    type_column = sys.argv[4] if len(sys.argv) > 4 and sys.argv[4] != "-" else None
    extra_labels = tuple(sys.argv[5:]) if len(sys.argv) > 5 else ()

    count, hdr, parts = transform(
        entity_dir, base_label, out_path, type_column, extra_labels=extra_labels
    )
    print(f"{base_label}: {count} rows from {parts} part file(s) -> {out_path}")
    print(f"header: {'|'.join(hdr)}")
