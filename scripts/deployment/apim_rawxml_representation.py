"""Keep C# expression quotes literal for APIM's rawxml/Razor parser.

XML-tree equality alone does not establish APIM representation acceptance.
Only expression attributes change representation; decoded values stay exact.
"""
import html
import re


def literal_expression_quotes(raw: str) -> tuple[str, int]:
    count = 0

    def replace(match):
        nonlocal count
        value = html.unescape(match[2])
        if not value.startswith('@'):
            return match[0]
        count += 1
        value = value.replace('&', '&amp;').replace('<', '&lt;').replace("'", '&apos;')
        value = value.replace('\r', '&#13;').replace('\n', '&#10;').replace('\t', '&#9;')
        return match[1] + "'" + value + "'"

    # Never reinterpret text, CDATA or comments as attributes.
    parts = re.split(r'(<!\[CDATA\[.*?\]\]>|<!--.*?-->)', raw, flags=re.S)
    for index in range(0, len(parts), 2):
        parts[index] = re.sub(r'(\s[\w:-]+=)"([^"]*)"', replace, parts[index])
    return ''.join(parts), count