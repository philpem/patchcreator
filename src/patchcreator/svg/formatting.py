"""SVG formatting that does not add visible whitespace to live text."""

import xml.etree.ElementTree as ET


def indent_svg(root: ET.Element) -> None:
    # ElementTree's generic indentation inserts text before a textPath and tail
    # text after it. With xml:space="preserve" those are actual extra characters
    # that change text anchoring, particularly when letter-spacing is large.
    content = []
    for text in root.iter("{http://www.w3.org/2000/svg}text"):
        content.append((text, "text", text.text))
        for child in text.iter():
            if child is not text:
                content.extend(((child, "text", child.text), (child, "tail", child.tail)))
    ET.indent(root, space="  ")
    for node, attribute, value in content:
        setattr(node, attribute, value)
