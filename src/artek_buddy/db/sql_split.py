"""Split Postgres SQL into statements without a naive ``;`` cut."""

from __future__ import annotations


def split_sql_statements(sql: str) -> list[str]:
    out: list[str] = []
    buf: list[str] = []
    i = 0
    n = len(sql)
    state = "code"
    block_depth = 0
    dollar_tag = ""

    def emit() -> None:
        text = "".join(buf).strip()
        buf.clear()
        if text and not _only_trivia(text):
            out.append(text)

    while i < n:
        ch = sql[i]
        nxt = sql[i + 1] if i + 1 < n else ""

        if state == "line":
            buf.append(ch)
            if ch == "\n":
                state = "code"
            i += 1
            continue

        if state == "block":
            buf.append(ch)
            if ch == "/" and nxt == "*":
                buf.append(nxt)
                block_depth += 1
                i += 2
                continue
            if ch == "*" and nxt == "/":
                buf.append(nxt)
                block_depth -= 1
                i += 2
                if block_depth <= 0:
                    state = "code"
                    block_depth = 0
                continue
            i += 1
            continue

        if state == "squote":
            buf.append(ch)
            if ch == "'":
                if nxt == "'":
                    buf.append(nxt)
                    i += 2
                    continue
                state = "code"
            i += 1
            continue

        if state == "estring":
            buf.append(ch)
            if ch == "\\":
                if i + 1 < n:
                    buf.append(sql[i + 1])
                    i += 2
                    continue
            if ch == "'":
                if nxt == "'":
                    buf.append(nxt)
                    i += 2
                    continue
                state = "code"
            i += 1
            continue

        if state == "dquote":
            buf.append(ch)
            if ch == '"':
                if nxt == '"':
                    buf.append(nxt)
                    i += 2
                    continue
                state = "code"
            i += 1
            continue

        if state == "dollar":
            tag = _dollar_open(sql, i)
            if tag == dollar_tag:
                buf.append(tag)
                i += len(tag)
                state = "code"
                dollar_tag = ""
                continue
            buf.append(ch)
            i += 1
            continue

        if ch == "-" and nxt == "-":
            buf.append(ch)
            buf.append(nxt)
            state = "line"
            i += 2
            continue
        if ch == "/" and nxt == "*":
            buf.append(ch)
            buf.append(nxt)
            state = "block"
            block_depth = 1
            i += 2
            continue
        if ch == "'":
            buf.append(ch)
            state = "estring" if _is_e_string_start(sql, i) else "squote"
            i += 1
            continue
        if ch == '"':
            buf.append(ch)
            state = "dquote"
            i += 1
            continue
        tag = _dollar_open(sql, i)
        if tag is not None:
            buf.append(tag)
            dollar_tag = tag
            state = "dollar"
            i += len(tag)
            continue
        if ch == ";":
            emit()
            i += 1
            continue
        buf.append(ch)
        i += 1

    emit()
    return out


def _dollar_open(sql: str, i: int) -> str | None:
    if i >= len(sql) or sql[i] != "$":
        return None
    j = i + 1
    if j < len(sql) and sql[j] == "$":
        return "$$"
    if j < len(sql) and (sql[j].isalpha() or sql[j] == "_"):
        j += 1
        while j < len(sql) and (sql[j].isalnum() or sql[j] == "_"):
            j += 1
        if j < len(sql) and sql[j] == "$":
            return sql[i : j + 1]
    return None


def _is_e_string_start(sql: str, quote_index: int) -> bool:
    if quote_index < 1 or sql[quote_index - 1] not in "Ee":
        return False
    if quote_index >= 2 and (sql[quote_index - 2].isalnum() or sql[quote_index - 2] == "_"):
        return False
    return True


def _only_trivia(sql: str) -> bool:
    i = 0
    n = len(sql)
    state = "code"
    block_depth = 0
    while i < n:
        ch = sql[i]
        nxt = sql[i + 1] if i + 1 < n else ""
        if state == "line":
            if ch == "\n":
                state = "code"
            i += 1
            continue
        if state == "block":
            if ch == "/" and nxt == "*":
                block_depth += 1
                i += 2
                continue
            if ch == "*" and nxt == "/":
                block_depth -= 1
                i += 2
                if block_depth <= 0:
                    state = "code"
                    block_depth = 0
                continue
            i += 1
            continue
        if ch.isspace():
            i += 1
            continue
        if ch == "-" and nxt == "-":
            state = "line"
            i += 2
            continue
        if ch == "/" and nxt == "*":
            state = "block"
            block_depth = 1
            i += 2
            continue
        return False
    return True
