# LDBC SNB bulk import prototype

Proof-of-concept scripts that convert the LDBC SNB dataset into the CSV format
expected by `neo4j-admin import`, so that a Neo4j store can be pre-filled
without going through Polypheny's per-record Cypher path.

These are prototypes. The productive version of this transformation is meant to
live in the Neo4j adapter itself; the scripts exist to validate the format and
to measure what bulk import actually costs.

## Why

Ingesting SF1 through the regular Cypher path stalls: the first six node
entities (~136k nodes) take about four minutes, and the run then livelocks on
`Comment` without ever reaching the edges. Bulk import loads the full dataset
— 3.0M nodes and 17.2M relationships — in roughly 32 seconds.

## Usage

Download and extract an LDBC SNB BI dataset, then:

```bash
S=<dataset>/graphs/csv/bi/composite-projected-fk/initial_snapshot

# Nodes: <entity dir> <base label> <output> [type column | -] [extra labels...]
python3 transform_nodes.py "$S/static/Place"        Place        out/place.csv        type
python3 transform_nodes.py "$S/static/Organisation" Organisation out/organisation.csv type
python3 transform_nodes.py "$S/static/Tag"          Tag          out/tag.csv
python3 transform_nodes.py "$S/static/TagClass"     TagClass     out/tagclass.csv
python3 transform_nodes.py "$S/dynamic/Person"      Person       out/person.csv
python3 transform_nodes.py "$S/dynamic/Forum"       Forum        out/forum.csv
python3 transform_nodes.py "$S/dynamic/Comment"     Comment      out/comment.csv - Message
python3 transform_nodes.py "$S/dynamic/Post"        Post         out/post.csv    - Message

# Edges: <entity dir> <output>
for d in "$S"/static/*_*_* "$S"/dynamic/*_*_*; do
  python3 transform_edges.py "$d" "out-edges/$(basename "$d").csv"
done
```

`build_import_cmd.sh` then assembles the `neo4j-admin import` invocation from
whatever is in `out/` and `out-edges/`.

## Format decisions

**Multi-labels via a `:LABEL` column.** LDBC uses a type hierarchy — a Comment
is also a Message, a University is also an Organisation, a City is also a Place.
Rather than writing one file per subtype, each row carries its own semicolon-
separated label list. This keeps the number of files equal to the number of
entities.

**The namespace mapping label.** Polypheny represents graph namespaces by
attaching a synthetic `___n_<id>___` label to every node, since Neo4j Community
has no namespace concept. The scripts prepend this label so that bulk-imported
data is indistinguishable from data written through Polypheny. The id is
currently hardcoded in `NAMESPACE_LABEL` and has to be read from the catalog
once this moves into the adapter.

**Separate id spaces per entity.** LDBC ids are only unique within an entity —
Place, Organisation, Tag and TagClass all start at 0. Without `:ID(Place)` and
friends, `neo4j-admin import` rejects the input with a duplicate id error.

**Timestamps as epoch millis.** `EntityHandler.toEpochMillis()` in the Cypher
path converts LDBC's ISO-8601 timestamps to epoch milliseconds, and interprets
date-only values (birthdays) as UTC midnight. The scripts do the same, so both
ingest paths produce identical property values.

**Id spaces derived from directory names.** LDBC's edge column names are not
consistent — `Person_hasInterest_Tag` uses `personId` and `interestId` rather
than `PersonId` and `TagId`. The directory name follows `Source_relation_Target`
reliably, so the id spaces come from there.

## Known gaps

- `NAMESPACE_LABEL` is hardcoded
- The relationship type derived in `build_import_cmd.sh` is a guess from the
  directory name; it has not been checked against what the Cypher path produces
- Only the initial snapshot is handled, not the insert/delete streams
