#!/usr/bin/env python3
"""
Transforms LDBC SNB relationship CSVs into the format expected by neo4j-admin import.

LDBC format:  pipe-separated, optional creationDate, two id columns named after the
              referenced entity, optional extra properties.
Neo4j format: :START_ID(Space)|:END_ID(Space)|properties, relationship type given
              on the command line via --relationships=TYPE=file.csv
"""

import gzip
import sys
import os
import glob
from datetime import datetime, timezone

LONG_COLUMNS = {"creationDate", "joinDate", "birthday", "classYear", "workFrom"}

# LDBC names some id columns after a subtype, but the ids live in the id space of
# the parent entity.
SPACE_ALIASES = {
    "University": "Organisation",
    "Company": "Organisation",
    "City": "Place",
    "Country": "Place",
}


def find_input_files(entity_dir):
    matches = glob.glob(os.path.join(entity_dir, "*.csv.gz"))
    if not matches:
        raise FileNotFoundError(f"No .csv.gz found in {entity_dir}")
    return sorted(matches)


def to_epoch_millis(value):
    value = value.strip()
    if not value:
        return ""
    try:
        dt = datetime.fromisoformat(value)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return str(int(dt.timestamp() * 1000))
    except ValueError:
        return value


def spaces_from_dirname(entity_dir):
    """
    LDBC relationship directories follow the pattern Source_relation_Target,
    e.g. Person_hasInterest_Tag or Comment_replyOf_Post. The column names are not
    reliable (Person_hasInterest_Tag uses 'personId' and 'interestId'), so the id
    spaces are taken from the directory name instead.
    """
    name = os.path.basename(entity_dir.rstrip("/"))
    parts = name.split("_")
    if len(parts) < 3:
        raise ValueError(f"Cannot derive id spaces from directory name '{name}'")
    start = SPACE_ALIASES.get(parts[0], parts[0])
    end = SPACE_ALIASES.get(parts[-1], parts[-1])
    return start, end


def annotate(column):
    if column in LONG_COLUMNS:
        return f"{column}:long"
    return column


def transform(entity_dir, out_path):
    in_paths = find_input_files(entity_dir)

    rows_written = 0
    header = None
    start_idx = end_idx = None
    prop_indices = None
    out_header = None

    with open(out_path, "w", encoding="utf-8") as fout:
        for in_path in in_paths:
            with gzip.open(in_path, "rt", encoding="utf-8") as fin:
                part_header = fin.readline().rstrip("\n").split("|")

                if header is None:
                    header = part_header
                    id_cols = [i for i, c in enumerate(header) if c.lower().endswith("id")]
                    if len(id_cols) != 2:
                        raise ValueError(
                            f"Expected exactly two id columns in {header}, got {id_cols}"
                        )
                    start_idx, end_idx = id_cols
                    prop_indices = [
                        i for i in range(len(header)) if i not in (start_idx, end_idx)
                    ]
                    start_space, end_space = spaces_from_dirname(entity_dir)
                    out_header = [
                        f":START_ID({start_space})",
                        f":END_ID({end_space})",
                    ]
                    out_header += [annotate(header[i]) for i in prop_indices]
                    fout.write("|".join(out_header) + "\n")
                elif part_header != header:
                    raise ValueError(f"Header mismatch in {in_path}")

                for line in fin:
                    fields = line.rstrip("\n").split("|")
                    out_fields = [fields[start_idx], fields[end_idx]]
                    for i in prop_indices:
                        value = fields[i]
                        if header[i] in LONG_COLUMNS:
                            value = to_epoch_millis(value)
                        out_fields.append(value)
                    fout.write("|".join(out_fields) + "\n")
                    rows_written += 1

    return rows_written, out_header, len(in_paths)


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("usage: transform_edges.py <entity_dir> <out_path>")
        sys.exit(1)

    count, hdr, parts = transform(sys.argv[1], sys.argv[2])
    name = os.path.basename(sys.argv[1])
    print(f"{name}: {count} rows from {parts} part file(s) -> {sys.argv[2]}")
    print(f"header: {'|'.join(hdr)}")
