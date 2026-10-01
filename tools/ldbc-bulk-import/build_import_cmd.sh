#!/bin/bash
# Assembles the neo4j-admin import command for all node and relationship files.

CMD="neo4j-admin import --database=neo4j"

for f in ~/ldbc-transform/out/*.csv; do
  CMD="$CMD --nodes=/import-nodes/$(basename "$f")"
done

for f in ~/ldbc-transform/out-edges/*.csv; do
  name=$(basename "$f" .csv)
  # Comment_hasCreator_Person -> hasCreator -> HAS_CREATOR
  rel=$(echo "$name" | cut -d_ -f2 | sed 's/\([A-Z]\)/_\1/g' | tr '[:lower:]' '[:upper:]')
  CMD="$CMD --relationships=${rel}=/import-edges/$(basename "$f")"
done

CMD="$CMD --delimiter='|' --array-delimiter=';' --force"
echo "$CMD"
