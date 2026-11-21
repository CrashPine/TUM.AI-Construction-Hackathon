"""Find errors and risks in German bills of quantities (LV).

`parse` reads a BoQ file into the model of `boqcheck.model`.
"""

from pathlib import PurePath

from boqcheck.gaeb_xml import parse_gaeb_xml
from boqcheck.model import BoQ

_PARSERS = {".x83": parse_gaeb_xml}


def parse(filename: str, data: bytes) -> BoQ:
    """Parse a BoQ file with the parser for its suffix.

    :param filename: the file name; its suffix selects the parser, in any letter case.
    :param data: the file content.
    :returns: the parsed BoQ.
    :raises ValueError: if no parser handles the suffix, or if the parser rejects the data.
    """
    suffix = PurePath(filename).suffix.lower()
    if suffix not in _PARSERS:
        raise ValueError(f"{filename}: unsupported file type; supported: {', '.join(_PARSERS)}")
    return _PARSERS[suffix](data, filename)
