"""Bounded three-valued parser for game conditions. Never executes catalog text."""
import re

TOKEN = re.compile(r'\s*(>=|<=|==|!=|&&|\|\||[!<>() ,]|-?\d+(?:\.\d+)?|[A-Za-z_][A-Za-z_0-9.]*)')


def evaluate(expression, state):
    if not expression or not expression.strip():
        return True
    if len(expression) > 1000:
        return None
    tokens, end = [], 0
    while end < len(expression.rstrip()):
        match = TOKEN.match(expression, end)
        if not match or len(tokens) >= 180:
            return None
        tokens.append(match.group(1))
        end = match.end()
    pos = 0

    def take(token=None):
        nonlocal pos
        if pos >= len(tokens) or (token is not None and tokens[pos] != token):
            raise ValueError('Unsupported condition')
        value = tokens[pos]
        pos += 1
        return value

    def call(name, args):
        keys = {'EnemyCount': 'enemy_count', 'IsEnemyCharge': 'charged', 'EnemyChargeStep': 'charge_step',
                'DpRate': 'dp_rate', 'HpRate': 'hp_rate', 'Turn': 'turn', 'DamageRate': 'damage_rate'}
        if name in keys and not args:
            return state.get(keys[name])
        if name == 'PlayedSkillCount' and len(args) == 1 and isinstance(args[0], str):
            counts = state.get('played_counts', {})
            return counts.get(args[0], 0 if state.get('played_complete') else None)
        return None

    def atom():
        nonlocal pos
        token = take()
        if token == '!':
            value = atom()
            return None if value is None or isinstance(value, str) else not value
        if token == '(':
            value = logical_or()
            take(')')
            return value
        if re.fullmatch(r'-?\d+(?:\.\d+)?', token):
            return float(token)
        if token in ('true', 'false'):
            return token == 'true'
        if pos < len(tokens) and tokens[pos] == '(':
            take('(')
            args = []
            if pos < len(tokens) and tokens[pos] != ')':
                args.append(logical_or())
                while pos < len(tokens) and tokens[pos] == ',':
                    take(',')
                    args.append(logical_or())
            take(')')
            return call(token, args)
        return token

    def compare():
        left = atom()
        if pos < len(tokens) and tokens[pos] in ('==', '!=', '<', '>', '<=', '>='):
            op = take()
            right = atom()
            if left is None or right is None or isinstance(left, str) or isinstance(right, str):
                return None
            return {'==': lambda: left == right, '!=': lambda: left != right,
                    '<': lambda: left < right, '>': lambda: left > right,
                    '<=': lambda: left <= right, '>=': lambda: left >= right}[op]()
        return left

    def logical_and():
        value = compare()
        while pos < len(tokens) and tokens[pos] == '&&':
            take('&&')
            other = compare()
            value = None if isinstance(value, str) else value
            other = None if isinstance(other, str) else other
            value = False if value is False or other is False else None if value is None or other is None else bool(value and other)
        return value

    def logical_or():
        value = logical_and()
        while pos < len(tokens) and tokens[pos] == '||':
            take('||')
            other = logical_and()
            value = None if isinstance(value, str) else value
            other = None if isinstance(other, str) else other
            value = True if value is True or other is True else None if value is None or other is None else bool(value or other)
        return value

    try:
        value = logical_or()
        return bool(value) if pos == len(tokens) and isinstance(value, (bool, int, float)) else None
    except (ValueError, RecursionError, TypeError):
        return None
