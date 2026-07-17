"""ruamel round-trip configuration: the parser/dumper the formatter uses.

Text-to-tree and tree-to-text only (StringIO); no filesystem access.
"""

from io import StringIO
from typing import Any

from ruamel.yaml import YAML
from ruamel.yaml.comments import CommentedMap


def create_yaml_instance(
    indent: int = 2, sequence_indent: int = 4, sequence_offset: int = 2
) -> YAML:
    """Creates a configured YAML parser/dumper instance."""
    yaml = YAML()
    yaml.preserve_quotes = True
    # In ruamel.yaml, mapping indent controls top-level mapping,
    # sequence controls list item indentation, offset is the indent of dash '-'
    yaml.indent(
        mapping=indent, sequence=sequence_indent, offset=sequence_offset
    )
    yaml.width = (
        4096  # Set large width to avoid automatic wrapping of long lines
    )
    return yaml


def load_yaml(content: str) -> Any:
    """Parses a YAML string into a CommentedMap or CommentedSeq."""
    if not content.strip():
        return CommentedMap()
    return create_yaml_instance().load(content)


def dump_yaml(
    data: Any,
    indent: int = 2,
    sequence_indent: int = 4,
    sequence_offset: int = 2,
) -> str:
    """Serializes a YAML structure to string, maintaining formatting."""
    yaml = create_yaml_instance(indent, sequence_indent, sequence_offset)
    stream = StringIO()
    yaml.dump(data, stream)
    return stream.getvalue()
