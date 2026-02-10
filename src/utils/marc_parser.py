"""
Module: marc_parser.py
Part of the LCCN Harvester Project.
"""

import xml.etree.ElementTree as ET
from typing import Dict, List


def extract_marc_fields_from_json(record: Dict) -> Dict[str, Dict[str, List[str]]]:
    """
    Extract MARC 050 and 060 subfields from a MARC JSON record.
    """
    result = {
        "050": {"a": [], "b": []},
        "060": {"a": [], "b": []},
    }

    fields = record.get("fields", [])

    for field in fields:
        for tag in ("050", "060"):
            if tag in field:
                subfields = field[tag].get("subfields", [])
                for sf in subfields:
                    if "a" in sf:
                        result[tag]["a"].append(sf["a"])
                    elif "b" in sf:
                        result[tag]["b"].append(sf["b"])

    return result

def extract_marc_fields_from_xml(xml_path: str) -> Dict[str, Dict[str, List[str]]]:
    """
    Extract MARC 050 and 060 subfields from a MARCXML file.
    """
    result = {
        "050": {"a": [], "b": []},
        "060": {"a": [], "b": []},
    }

    tree = ET.parse(xml_path)
    root = tree.getroot()

    # Handle MARCXML namespace if present
    ns = {"marc": "http://www.loc.gov/MARC21/slim"}

    for datafield in root.findall(".//marc:datafield", ns):
        tag = datafield.get("tag")
        if tag in result:
            for subfield in datafield.findall("marc:subfield", ns):
                code = subfield.get("code")
                if code in ("a", "b"):
                    result[tag][code].append(subfield.text.strip())

    return result
