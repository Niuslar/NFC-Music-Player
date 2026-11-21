"""A small reader and writer for KiCad's S-expression files, enough to copy library symbols."""


class Str(str):
    """A quoted string, so it is written back with quotes."""


def parse(text):
    tokens, i, n = [], 0, len(text)
    stack = [[]]
    while i < n:
        ch = text[i]
        if ch in " \t\r\n":
            i += 1
        elif ch == "(":
            stack.append([])
            i += 1
        elif ch == ")":
            done = stack.pop()
            stack[-1].append(done)
            i += 1
        elif ch == '"':
            j, out = i + 1, []
            while text[j] != '"':
                if text[j] == "\\":
                    out.append(text[j : j + 2])
                    j += 2
                else:
                    out.append(text[j])
                    j += 1
            stack[-1].append(Str("".join(out)))
            i = j + 1
        else:
            j = i
            while j < n and text[j] not in ' \t\r\n()"':
                j += 1
            stack[-1].append(text[i:j])
            i = j
    del tokens
    return stack[0][0]


def dump(node, depth=0):
    pad = "\t" * depth
    if not isinstance(node, list):
        return f'"{node}"' if isinstance(node, Str) else str(node)
    simple = all(not isinstance(c, list) for c in node)
    if simple:
        return pad + "(" + " ".join(dump(c) for c in node) + ")"
    head = []
    rest = list(node)
    while rest and not isinstance(rest[0], list):
        head.append(dump(rest.pop(0)))
    lines = [pad + "(" + " ".join(head)]
    for c in rest:
        lines.append(dump(c, depth + 1) if isinstance(c, list) else "\t" * (depth + 1) + dump(c))
    lines.append(pad + ")")
    return "\n".join(lines)


def find(node, key):
    return [c for c in node if isinstance(c, list) and c and c[0] == key]


def library_symbol(lib_path, name):
    tree = parse(open(lib_path, encoding="utf-8").read())
    for sym in find(tree, "symbol"):
        if sym[1] == name:
            if find(sym, "extends"):
                raise ValueError(f"{name} extends another symbol; use the base symbol")
            return sym
    raise KeyError(name)
