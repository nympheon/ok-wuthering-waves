"""把持宏队伍代码改成用 src/combat/MacroKit.py 里的公共方法。

对队伍目录里每个持宏文件 (<角色>.py 和 <角色>.import.py 里, 类上定义了 macro_wait 的那个):
  - 类里和 MacroKit 一样的方法删掉 (按 AST 比, 文档字符串和注释不算)。macro_wait 还是老的切片等待的也删,
    MacroKit 里那份改走 BaseChar.precise_wait (见 SUPERSEDED)。和 MacroKit 不一样的方法留着, 盖过 MacroKit 的。
  - 模块里和 MacroKit 一样的定义 (SendInput 结构体、send_input_left、MacroBroken) 删掉, 改从 MacroKit 导入:
    MacroBroken 得是同一个类, 队伍代码里的 except MacroBroken 才接得住 MacroKit 方法里抛的。
  - 类改成继承 (MacroKit, 原生类), 开头的 import 块后面加一行 from src.combat.MacroKit import ...
  - 删掉的方法上方紧贴的注释一起删; 分节标题 (# ==== ...) 留着;
    "宏原语(引擎) … 改这里要几边同步" 那段说明换成指向 MacroKit 的一句。

下面这些情况整个文件不改, 打印原因:
  - 模块里有和 MacroKit 同名但不一样的东西 (导出时 MacroKit 内联进同一个模块, 会互相盖掉);
  - 类上会多出同队代码或框架按名字探测的方法 (hasattr(char, 'quick_switch') 这种), 队友的判断会变;
  - 留下的方法里有 super().<MacroKit 的方法>(), 原来解析不到、改完会解析到 MacroKit;
  - 改前改后各加载一次, 类上每个名字解析到的东西对不上: 方法的 AST、方法读的全局名字指向的东西、
    常量, 都要和原来一样 (换掉的 macro_wait 除外), 原来有的名字一个都不能少。

用法 (在 coco-ww 根目录):
    python\\python.exe -X utf8 tools\\macrokit_convert.py configs\\custom_teams\\A__B__C ...          只看会改什么
    python\\python.exe -X utf8 tools\\macrokit_convert.py --write configs\\custom_teams\\A__B__C ...  写回
"""
import argparse
import ast
import hashlib
import re
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

KIT_MODULE = 'src.combat.MacroKit'
KIT_PATH = ROOT / 'src' / 'coco' / 'macrokit.py'
IMPORT_SUFFIX = '.import.py'
ENGINE_HEADER = (
    '# ==================== 宏原语 ====================',
    '# 通用的在 src/combat/MacroKit.py (MacroKit); 这里只有这条轴自己的写法, 同名的盖过 MacroKit 的。',
)

# MacroKit 里有意改过的方法: 队伍里还是这些老写法的也删掉, 用 MacroKit 的 (比的时候不看文档字符串)
SUPERSEDED = {
    'macro_wait': (
        '''
def macro_wait(self, sec):
    if sec <= 0:
        self.task.executor.check_enabled(check_pause=False)
        return
    end = time.time() + sec
    while True:
        left = end - time.time()
        if left <= 0:
            return
        time.sleep(min(0.1, left))
        self.task.executor.check_enabled(check_pause=False)
''',
        # 切片写成类常量 (MACRO_SLICE = 0.05, 和 precise_wait 的切片一样长)
        '''
def macro_wait(self, sec):
    if sec <= 0:
        self.task.executor.check_enabled(check_pause=False)
        return
    end = time.time() + sec
    while True:
        left = end - time.time()
        if left <= 0:
            return
        time.sleep(min(self.MACRO_SLICE, left))
        self.task.executor.check_enabled(check_pause=False)
''',
        # 少了 sec <= 0 那个判断 (等 0 秒时不查停任务就返回)
        '''
def macro_wait(self, sec):
    end = time.time() + sec
    while True:
        left = end - time.time()
        if left <= 0:
            return
        time.sleep(min(0.1, left))
        self.task.executor.check_enabled(check_pause=False)
''',
    ),
}

PROBE = re.compile(r'''\b(?:hasattr|getattr)\(\s*[\w.\[\]()]+\s*,\s*['"](\w+)['"]''')
SECTION = re.compile(r'^\s*#\s*[=\-]{4,}')
CLASS_IGNORED = {'__module__', '__qualname__', '__doc__', '__dict__', '__weakref__', '__firstlineno__',
                 '__static_attributes__'}


class Skip(Exception):
    """这个文件不改。"""


# ---------------- AST ----------------

def strip_docstrings(node):
    node = ast.parse(ast.unparse(node)).body[0]
    for n in ast.walk(node):
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            body = n.body
            if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant) \
                    and isinstance(body[0].value.value, str):
                n.body = body[1:] or [ast.Pass()]
    return node


def fingerprint(node):
    return hashlib.sha1(ast.unparse(strip_docstrings(node)).encode('utf-8')).hexdigest()


SUPERSEDED_KEYS = {name: {fingerprint(ast.parse(text).body[0]) for text in texts}
                   for name, texts in SUPERSEDED.items()}


def first_line(node):
    return min([d.lineno for d in getattr(node, 'decorator_list', [])] + [node.lineno])


def binding_key(node):
    """模块顶层一条语句绑定的名字 -> 怎么绑的。import 按来源比, 定义按 AST 比。"""
    out = {}
    if isinstance(node, ast.Import):
        for a in node.names:
            out[a.asname or a.name.split('.')[0]] = ('import', a.name, a.asname)
    elif isinstance(node, ast.ImportFrom):
        for a in node.names:
            out[a.asname or a.name] = ('from', node.module, node.level, a.name)
    elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
        out[node.name] = ('def', fingerprint(node))
    elif isinstance(node, (ast.Assign, ast.AnnAssign, ast.AugAssign)):
        targets = node.targets if isinstance(node, ast.Assign) else [node.target]
        for target in targets:
            for n in ast.walk(target):
                if isinstance(n, ast.Name):
                    out[n.id] = ('assign', fingerprint(node))
    return out


def module_bindings(tree):
    """顶层(连同顶层 try/if/with 里面)绑定的名字: 名字 -> [(语句, 绑定方式, 是否直接在顶层)]。"""
    out = {}

    def visit(statements, top):
        for node in statements:
            for name, how in binding_key(node).items():
                out.setdefault(name, []).append((node, how, top))
            if isinstance(node, (ast.Try, ast.If, ast.With, ast.For, ast.While)):
                for field in ('body', 'orelse', 'finalbody'):
                    visit(getattr(node, field, []), False)
                for handler in getattr(node, 'handlers', []):
                    visit(handler.body, False)
    visit(tree.body, True)
    return out


def loaded_names(tree):
    return {n.id for n in ast.walk(tree) if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load)}


# ---------------- 运行时比对 ----------------

class Loaded:
    """从一段源码加载出来的模块, 记着源码的 AST, 好按行号找回每个函数的定义。"""
    counter = 0

    def __init__(self, text, path):
        Loaded.counter += 1
        self.filename = f'{path} [macrokit_convert {Loaded.counter}]'
        self.tree = ast.parse(text)
        self.functions = {}
        for n in ast.walk(self.tree):
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
                self.functions[first_line(n)] = n
                self.functions.setdefault(n.lineno, n)
        name = f'coco_ww_macrokit_convert_{Loaded.counter}'
        self.module = types.ModuleType(name)
        self.module.__file__ = str(path)
        sys.modules[name] = self.module
        try:
            exec(compile(text, self.filename, 'exec'), self.module.__dict__)
        finally:
            sys.modules.pop(name, None)


class Comparer:
    def __init__(self, sources):
        self.by_filename = {s.filename: s for s in sources}
        self.memo = {}

    def function_node(self, func):
        code = func.__code__
        source = self.by_filename.get(code.co_filename)
        if source is None:
            return None
        return source.functions.get(code.co_firstlineno)

    def same(self, a, b):
        if a is b:
            return True
        memo_key = (id(a), id(b))
        if memo_key in self.memo:
            return self.memo[memo_key]
        self.memo[memo_key] = True   # 递归到自己 (结构体互相引用) 先当一样
        result = self._same(a, b)
        self.memo[memo_key] = result
        return result

    def _same(self, a, b):
        if isinstance(a, types.ModuleType) or isinstance(b, types.ModuleType):
            return isinstance(a, types.ModuleType) and isinstance(b, types.ModuleType) and a.__name__ == b.__name__
        if isinstance(a, (staticmethod, classmethod)) or isinstance(b, (staticmethod, classmethod)):
            return type(a) is type(b) and self.same(a.__func__, b.__func__)
        if isinstance(a, property) or isinstance(b, property):
            return type(a) is type(b) and all(self.same(getattr(a, f), getattr(b, f))
                                              for f in ('fget', 'fset', 'fdel'))
        if isinstance(a, types.FunctionType) or isinstance(b, types.FunctionType):
            return isinstance(a, types.FunctionType) and isinstance(b, types.FunctionType) and self.same_function(a, b)
        if isinstance(a, type) or isinstance(b, type):
            return isinstance(a, type) and isinstance(b, type) and self.same_class(a, b)
        if isinstance(a, (list, tuple)) or isinstance(b, (list, tuple)):
            return type(a) is type(b) and len(a) == len(b) and all(self.same(x, y) for x, y in zip(a, b))
        if isinstance(a, dict) or isinstance(b, dict):
            return type(a) is type(b) and a.keys() == b.keys() and all(self.same(a[k], b[k]) for k in a)
        if type(a).__name__ == 'CField' and type(b).__name__ == 'CField':   # ctypes 结构体的字段描述
            return repr(a) == repr(b)
        try:
            return type(a) is type(b) and bool(a == b)
        except Exception:
            return False

    def same_function(self, a, b):
        node_a, node_b = self.function_node(a), self.function_node(b)
        if node_a is None or node_b is None:
            return False   # 不是从被比的这几份源码里来的, 又不是同一个对象
        if a.__name__ != b.__name__ or fingerprint(node_a) != fingerprint(node_b):
            return False
        return self.same_globals(a, b)

    def same_globals(self, a, b):
        missing = object()
        for name in global_names(a.__code__):
            if name.startswith('__') and name.endswith('__'):
                continue   # __name__ / __file__ 这些是加载方给的, 改前改后都一样由加载方定
            x, y = a.__globals__.get(name, missing), b.__globals__.get(name, missing)
            if (x is missing) != (y is missing):
                return False
            if x is not missing and not self.same(x, y):
                return False
        return True

    def same_class(self, a, b):
        if a.__name__ != b.__name__ or len(a.__bases__) != len(b.__bases__):
            return False
        if not all(self.same(x, y) for x, y in zip(a.__bases__, b.__bases__)):
            return False
        names = (set(vars(a)) | set(vars(b))) - CLASS_IGNORED
        return all(name in vars(a) and name in vars(b) and self.same(vars(a)[name], vars(b)[name])
                   for name in names)


def global_names(code):
    names = set(code.co_names)
    for const in code.co_consts:
        if isinstance(const, types.CodeType):
            names |= global_names(const)
    return names


def resolve(cls, name):
    for klass in cls.__mro__:
        if name in vars(klass):
            return klass, vars(klass)[name]
    return None, None


# ---------------- 转换一个文件 ----------------

class Kit:
    def __init__(self):
        self.text = KIT_PATH.read_text(encoding='utf-8')
        self.tree = ast.parse(self.text)
        self.cls = next(n for n in self.tree.body if isinstance(n, ast.ClassDef) and n.name == 'MacroKit')
        self.methods = {n.name: n for n in self.cls.body if isinstance(n, ast.FunctionDef)}
        self.method_keys = {name: fingerprint(n) for name, n in self.methods.items()}
        self.bindings = {}
        for node in self.tree.body:
            self.bindings.update(binding_key(node))
        import importlib
        self.module = importlib.import_module(KIT_MODULE)


def probed_names(folder):
    names = set()
    paths = list(folder.glob('*.py')) + list((ROOT / 'src').rglob('*.py'))
    for path in paths:
        if path.resolve() == KIT_PATH.resolve():
            continue
        names |= set(PROBE.findall(path.read_text(encoding='utf-8', errors='replace')))
    return names


def attached_comments(lines, start):
    """start(1 起) 那行上方紧贴的注释行: 返回第一行的行号 (没有就是 start)。"""
    i = start - 1
    while i - 1 >= 0 and lines[i - 1].strip().startswith('#'):
        i -= 1
    return i + 1


def convert_text(text, path, class_name, kit, probes):
    """返回 (新源码, 报告)。不该改的抛 Skip。"""
    crlf = '\r\n' in text
    text = text.replace('\r\n', '\n')
    lines = text.split('\n')
    tree = ast.parse(text)
    cls = next((n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == class_name), None)
    if cls is None:
        raise Skip(f'没有类 {class_name}')
    methods = {n.name: n for n in cls.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
    if 'macro_wait' not in methods:
        raise Skip('不是持宏角色 (类上没有 macro_wait)')
    if any(isinstance(b, ast.Name) and b.id == 'MacroKit' for b in cls.bases):
        raise Skip('已经用 MacroKit 了')
    if len(cls.bases) != 1 or not isinstance(cls.bases[0], ast.Name) or cls.keywords:
        raise Skip(f'类的继承写法不是 class {class_name}(原生类)')

    # 模块级: 和 MacroKit 同名的要一模一样; 一样的定义删掉改导入
    bindings = module_bindings(tree)
    remove_module = {}
    for name, how in kit.bindings.items():
        for node, team_how, top in bindings.get(name, []):
            if team_how != how:
                raise Skip(f'模块里的 {name} 和 MacroKit 的不一样 ({team_how[0]} vs {how[0]})')
            if how[0] in ('def', 'assign'):
                if not top:
                    raise Skip(f'模块里的 {name} 定义在 try/if 里面, 删不干净')
                remove_module[id(node)] = node
    remove_module = list(remove_module.values())

    # 类里: 一样的方法删掉
    remove_methods, superseded, differs = [], [], []
    for name, node in methods.items():
        if name not in kit.methods:
            continue
        key = fingerprint(node)
        if key == kit.method_keys[name]:
            remove_methods.append(node)
        elif key in SUPERSEDED_KEYS.get(name, ()):
            remove_methods.append(node)
            superseded.append(name)
        else:
            differs.append(name)
    if not remove_methods:
        raise Skip('没有和 MacroKit 一样的方法')

    gained = sorted(set(kit.methods) - set(methods))
    probed = [name for name in gained if name in probes]
    if probed:
        raise Skip(f'类上会多出被按名字探测的方法 {probed}, 队友代码的判断会变')
    kept = [n for n in methods.values() if n not in remove_methods]
    for node in kept:
        for n in ast.walk(node):
            if isinstance(n, ast.Attribute) and n.attr in kit.methods and isinstance(n.value, ast.Call) \
                    and isinstance(n.value.func, ast.Name) and n.value.func.id == 'super':
                raise Skip(f'{node.name} 里 super().{n.attr}: 改完会解析到 MacroKit')

    # ---- 改源码: 记成 (起始行, 结束行, 换成的行), 行号 1 起, 从下往上改 ----
    edits = []
    for node in remove_module:
        start = attached_comments(lines, first_line(node))
        edits.append((start, node.end_lineno, None))
    engine_blocks = set()
    for node in methods.values():
        start = attached_comments(lines, first_line(node))
        block = lines[start - 1:first_line(node) - 1]
        if any('宏原语' in line for line in block):
            indent = re.match(r'\s*', lines[first_line(node) - 1]).group()
            edits.append((start, first_line(node) - 1, [indent + line for line in ENGINE_HEADER]))
            engine_blocks.add(id(node))
    for node in remove_methods:
        start, def_line = attached_comments(lines, first_line(node)), first_line(node)
        block = lines[start - 1:def_line - 1]
        if id(node) in engine_blocks or (block and SECTION.match(block[0])):
            start = def_line   # 分节标题 / 换过的引擎说明留在原处, 管下面的方法
        edits.append((start, node.end_lineno, None))

    base = cls.bases[0]
    edits.append((base.lineno, base.lineno, 'base'))

    import_after = 0
    for node in tree.body:
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            import_after = node.end_lineno
        elif isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant) and import_after == 0:
            import_after = node.end_lineno   # 模块文档字符串
        else:
            break
    edits.append((import_after + 1, import_after, 'import'))

    removed_names = sorted({name for node in remove_module for name in binding_key(node)})
    new_lines = list(lines)
    for start, end, replacement in sorted(edits, key=lambda e: (e[0], e[1]), reverse=True):
        if replacement == 'base':
            line = new_lines[start - 1]
            col = len(line.encode('utf-8')[:base.col_offset].decode('utf-8'))
            new_lines[start - 1] = line[:col] + 'MacroKit, ' + line[col:]
        elif replacement == 'import':
            new_lines[start - 1:start - 1] = ['@@MACROKIT_IMPORT@@']
        elif replacement is not None:
            new_lines[start - 1:end] = replacement
        else:
            before = 0
            while start - 2 - before >= 0 and new_lines[start - 2 - before].strip() == '':
                before += 1
            after = 0
            while end + after < len(new_lines) and new_lines[end + after].strip() == '':
                after += 1
            del new_lines[start - 1:end + min(before, after)]

    body = '\n'.join(line for line in new_lines if line != '@@MACROKIT_IMPORT@@')
    still_used = loaded_names(ast.parse(body))
    names = ['MacroKit'] + [n for n in ('MacroBroken', 'send_input_left') if n in removed_names and n in still_used]
    names += [n for n in removed_names if n in still_used and n not in names]
    import_line = f'from {KIT_MODULE} import {", ".join(names)}'
    if len(import_line) > 120:
        import_line = f'from {KIT_MODULE} import (\n    ' + ',\n    '.join(names) + ',\n)'
    new_text = '\n'.join(import_line if line == '@@MACROKIT_IMPORT@@' else line for line in new_lines)
    ast.parse(new_text)

    report = {'removed': [n.name for n in remove_methods], 'superseded': superseded, 'differs': differs,
              'gained': gained, 'module_removed': removed_names, 'import': names,
              'lines': (len(lines), len(new_text.split('\n')))}
    verify(text, new_text, path, class_name, kit, set(superseded), set(removed_names) - still_used, report)
    if crlf:
        new_text = new_text.replace('\n', '\r\n')
    return new_text, report


def verify(old_text, new_text, path, class_name, kit, superseded, unused_removed, report):
    """改前改后各加载一次逐个比。unused_removed: 删掉后没人再用的模块级名字, 允许消失。"""
    old, new = Loaded(old_text, path), Loaded(new_text, path)
    kit_source = Loaded.__new__(Loaded)
    kit_source.filename = kit.module.__spec__.origin
    kit_source.tree = kit.tree
    kit_source.functions = {}
    for n in ast.walk(kit.tree):
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
            kit_source.functions[first_line(n)] = n
            kit_source.functions.setdefault(n.lineno, n)
    comparer = Comparer([old, new, kit_source])
    old_cls, new_cls = getattr(old.module, class_name), getattr(new.module, class_name)
    expected_mro = (new_cls, kit.module.MacroKit) + old_cls.__mro__[1:]
    if new_cls.__mro__ != expected_mro:
        raise Skip(f'改完的 MRO 不对: {[c.__name__ for c in new_cls.__mro__]}')
    for name in sorted((set(dir(old_cls)) | set(dir(new_cls))) - CLASS_IGNORED):
        old_owner, old_value = resolve(old_cls, name)
        new_owner, new_value = resolve(new_cls, name)
        if old_owner is None:
            continue   # 多出来的名字 (gained), 前面查过探测
        if new_owner is None:
            raise Skip(f'改完类上没有 {name} 了')
        if name in superseded:
            if new_owner is not kit.module.MacroKit:
                raise Skip(f'{name} 应该换成 MacroKit 的')
            continue
        if not comparer.same(old_value, new_value):
            raise Skip(f'{name} 改前改后不一样 (原来在 {old_owner.__name__}, 现在在 {new_owner.__name__})')
    for name, value in vars(old.module).items():
        if name.startswith('__') or name == class_name:
            continue
        if name not in vars(new.module):
            if name in unused_removed:
                continue
            raise Skip(f'模块里没有 {name} 了')
        if not comparer.same(value, vars(new.module)[name]):
            raise Skip(f'模块里的 {name} 改前改后不一样')
    extra = set(vars(new.module)) - set(vars(old.module))
    if extra - {'MacroKit'}:
        raise Skip(f'模块里多出 {sorted(extra)}')
    report['verified'] = True


def convert_folder(folder, kit, write):
    folder = Path(folder)
    probes = probed_names(folder)
    results = []
    for class_name in folder.name.split('__'):
        for path in (folder / f'{class_name}.py', folder / f'{class_name}{IMPORT_SUFFIX}'):
            if not path.is_file():
                continue
            raw = path.read_bytes().decode('utf-8')
            try:
                new_text, report = convert_text(raw, path, class_name, kit, probes)
            except Skip as e:
                results.append((path, None, str(e)))
                continue
            if write:
                path.write_bytes(new_text.encode('utf-8'))
            results.append((path, report, None))
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('folders', nargs='+')
    parser.add_argument('--write', action='store_true', help='写回 (不加只打印)')
    args = parser.parse_args()
    kit = Kit()
    for folder in args.folders:
        for path, report, skipped in convert_folder(folder, kit, args.write):
            where = f'{Path(folder).name}/{path.name}'
            if report is None:
                if '不是持宏角色' not in skipped:
                    print(f'不改 {where}: {skipped}')
                continue
            old_n, new_n = report['lines']
            print(f'{"改了" if args.write else "会改"} {where}: {old_n} -> {new_n} 行, 删 {len(report["removed"])} 个方法'
                  f'{" (含换掉的 " + ",".join(report["superseded"]) + ")" if report["superseded"] else ""}, '
                  f'留着自己的 {len(report["differs"])} 个, 模块里删 {len(report["module_removed"])} 个名字, '
                  f'导入 {",".join(report["import"])}')


if __name__ == '__main__':
    main()
