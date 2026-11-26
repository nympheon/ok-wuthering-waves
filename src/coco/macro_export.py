import ast
import re
from pathlib import Path
from textwrap import indent

_MODULES = {'src.combat.MacroKit', 'src.coco.macrokit'}


def inline_macrokit(code):
    """Include the shared macro implementation in portable team archives."""
    if not any(module in code for module in _MODULES):
        return code
    tree = ast.parse(code)
    for node in ast.walk(tree):
        if node in tree.body:
            continue
        if ((isinstance(node, ast.ImportFrom) and node.level == 0 and node.module in _MODULES)
                or (isinstance(node, ast.Import) and any(alias.name in _MODULES for alias in node.names))):
            raise ValueError('Move the MacroKit import to the top level before exporting the team')
    imports = []
    for node in tree.body:
        if isinstance(node, ast.ImportFrom) and node.level == 0 and node.module in _MODULES:
            bindings = [f'{item.asname or item.name} = _echodesk_macrokit.{item.name}' for item in node.names]
            if any(item.name == '*' for item in node.names):
                raise ValueError('Import MacroKit members by name before exporting the team')
            imports.append((node, bindings))
        elif isinstance(node, ast.Import) and any(item.name in _MODULES for item in node.names):
            bindings = []
            for item in node.names:
                if item.name in _MODULES:
                    if not item.asname:
                        raise ValueError('Give the MacroKit module an alias before exporting the team')
                    bindings.append(f'{item.asname} = _echodesk_macrokit')
                else:
                    bindings.append(ast.unparse(ast.Import(names=[item])))
            imports.append((node, bindings))
    if not imports:
        return code

    source = Path(__file__).with_name('macrokit.py').read_text(encoding='utf-8')
    shared = ('# Shared MacroKit from coco-ww\n'
              'def _echodesk_make_macrokit():\n'
              '    from types import SimpleNamespace\n'
              f'{indent(source, "    ")}\n'
              '    return SimpleNamespace(MacroKit=MacroKit, MacroBroken=MacroBroken, send_input_left=send_input_left)\n'
              '_echodesk_macrokit = _echodesk_make_macrokit()\n')
    data = code.encode('utf-8')
    starts = [0]
    for line in data.splitlines(keepends=True):
        starts.append(starts[-1] + len(line))
    for index in range(len(imports) - 1, -1, -1):
        node, bindings = imports[index]
        before = starts[node.lineno - 1] + node.col_offset
        after = starts[node.end_lineno - 1] + node.end_col_offset
        suffix = re.sub(rb'^[ \t]*;[ \t]*', b'', data[after:], count=1)
        block = ('\n' + (shared if index == 0 else '') + '\n'.join(bindings) + '\n').encode('utf-8')
        data = data[:before] + block + suffix
    return data.decode('utf-8')
