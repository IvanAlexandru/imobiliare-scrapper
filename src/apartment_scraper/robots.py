"""Robots rules with wildcard, end-anchor and longest-match/Allow precedence.

Only access decisions and crawl delay are needed; sitemaps and request-rate hints
are not used. Paths retain reserved percent escapes and normalize unreserved ones.
"""
import re
from urllib.parse import urlsplit, quote


def normalize(value):
    def percent(match):
        char = chr(int(match[1], 16))
        return char if char.isascii() and (char.isalnum() or char in '-._~') else '%' + match[1].upper()
    return re.sub(r'%([0-9a-fA-F]{2})', percent, quote(value, safe="/%?=&;:+,@!$'()*-._~"))


class Robots:
    def __init__(self, text, user_agent):
        groups = []
        agents, rules, delays = [], [], []
        has_directives = False
        for line in text.splitlines():
            line = line.split('#', 1)[0].strip()
            if ':' not in line:
                continue
            key, value = (part.strip() for part in line.split(':', 1))
            key = key.lower()
            if key == 'user-agent':
                if has_directives:
                    groups.append((agents, rules, delays))
                    agents, rules, delays = [], [], []
                    has_directives = False
                agents.append(value.lower())
            elif agents:
                has_directives = True
                if key in ('allow', 'disallow') and value:
                    rules.append((key, normalize(value)))
                elif key == 'crawl-delay':
                    try:
                        delays.append(max(0, float(value)))
                    except ValueError:
                        pass
        if agents:
            groups.append((agents, rules, delays))
        ua = user_agent.lower()
        ranked = [(max((0 if a == '*' else len(a) for a in agents if a == '*' or a in ua), default=-1), rules, delays)
                  for agents, rules, delays in groups]
        best = max((rank for rank, _, _ in ranked), default=-1)
        self.rules = [rule for rank, rules, _ in ranked if rank == best for rule in rules]
        self.delay = max((d for rank, _, delays in ranked if rank == best for d in delays), default=0)

    def allows(self, url):
        p = urlsplit(url)
        path = normalize((p.path or '/') + ('?' + p.query if p.query else ''))
        matches = []
        for kind, value in self.rules:
            anchored = value.endswith('$')
            pattern = value[:-1] if anchored else value
            regex = '^' + '.*'.join(re.escape(part) for part in pattern.split('*')) + ('$' if anchored else '')
            if re.search(regex, path):
                matches.append((len(pattern.replace('*', '')), kind == 'allow'))
        return max(matches, default=(0, True))[1]
