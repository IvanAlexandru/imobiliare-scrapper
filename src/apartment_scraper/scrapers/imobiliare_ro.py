"""Parser for inspected public Inertia HTML; no private API requests."""
import json
import re
from urllib.parse import urljoin
from bs4 import BeautifulSoup
from ..models import SourceResult, Listing
from ..http import Client, AccessError
from ..filters import numeric, usable_area

BASE = 'https://www.imobiliare.ro'
SEARCH = BASE + '/vanzare-apartamente/bucuresti'


def payload(html):
    node = BeautifulSoup(html, 'html.parser').find(attrs={'data-page': True})
    if node is None:
        raise ValueError('Missing Inertia data-page; layout change or blocked page')
    return json.loads(node['data-page'])['props']


def sections(p):
    return {s['type']: s['data'] for s in p['sections']}


def search_page(html):
    p = payload(html)
    meta = p['searchMeta']
    items = sections(p)['results-list']['listings']
    if not isinstance(items, list) or not isinstance(meta['lastPage'], int):
        raise ValueError('Invalid Imobiliare search schema')
    if not items and meta['totalCount']:
        raise ValueError('Empty search page with nonzero total')
    return items, meta


def number_prefix(value):
    m = re.match(r'^\s*(\d+(?:[,.]\d+)?)', str(value or ''))
    return numeric(m[1]) if m else None


def displayed_eur(value):
    # Verified Romanian presentation: 298.870 € and 78,27 mp.
    if not isinstance(value, str) or not value.strip().endswith('€'):
        return None
    return numeric(value.replace('€', '').replace('.', '').strip())


def parse_listing(html, url):
    p = payload(html)
    s = sections(p)
    title = s['title']
    fields = {i['key']: i['value'] for i in s['summary']['items']}
    coords = s.get('gallery', {}).get('map', {})
    center = coords.get('center') or [None, None]
    crumbs = {i.get('href') for i in s['breadcrumbs']['items']}
    time_on_market = s.get('specifications-panel', {}).get('timeOnMarket') or {}
    rooms, year = number_prefix(fields.get('bedroom_count')), number_prefix(fields.get('year_built'))
    floor = fields.get('floor_number')
    total = re.search(r'/\s*(\d+)\s*$', floor or '')
    seller = (p.get('viewItem', {}).get('ecommerce', {}).get('items') or [{}])[0].get('sellerType')
    # Public specification rows confirm sale; breadcrumbs confirm city/category.
    specs = [row for group in s.get('specifications-panel', {}).get('items', [])
             if group.get('type') == 'specifications' for row in group.get('data', {}).get('items', [])]
    sale = any(row.get('label') == 'Tip tranzacție' and 'vânzare' in row.get('value', '').lower() for row in specs)
    return Listing(source='imobiliare_ro', id=str(p['listingMeta']['id']), url=url,
        title=title['h1'], price_eur=displayed_eur(title['price'].get('price')),
        rooms=int(rooms) if rooms is not None and rooms.is_integer() else None,
        year=int(year) if year is not None and year.is_integer() else None,
        usable_area=usable_area(number_prefix(fields.get('usable_surface'))),
        floor=floor, total_floors=int(total[1]) if total else None,
        address=title.get('address', ''), latitude=numeric(center[0]), longitude=numeric(center[1]),
        precise_location=coords.get('hideExactLocation') is False,
        seller={'agency':'agency', 'owner':'owner', 'private':'owner', 'developer':'developer'}.get(seller),
        published=time_on_market.get('listedLabel'), updated=time_on_market.get('updatedLabel'),
        description=' '.join(seg.get('value', '') for block in s.get('description', {}).get('blocks', [])
                             for seg in block.get('segments', []) if seg.get('type') == 'text'),
        city='Bucuresti' if '/vanzare-apartamente/bucuresti' in crumbs else '',
        transaction='SELL' if sale else '', property_type='FLAT' if '/vanzare-apartamente' in crumbs else '')


def scan(config, smoke=False):
    result = SourceResult('imobiliare_ro')
    client = Client('www.imobiliare.ro', config['http'])
    seen, details, parsed = set(), 0, 0
    try:
        for page in range(1, (1 if smoke else config['http']['max_pages']) + 1):
            url = SEARCH if page == 1 else SEARCH + f'?page={page}'
            items, meta = search_page(client.get(url))
            if meta['currentPage'] != page:
                raise ValueError('Imobiliare pagination did not advance')
            result.pages += 1
            fresh = [i for i in items if str(i['id']) not in seen]
            if items and not fresh:
                raise ValueError('Repeated Imobiliare page')
            for item in fresh:
                seen.add(str(item['id']))
                result.examined += 1
                if not smoke:
                    highlights = {v['key']: v['label'] for v in item.get('highlights', [])}
                    rooms = number_prefix(highlights.get('bedroom_count'))
                    if rooms is not None and rooms not in config['filters']['rooms']:
                        continue
                    price = displayed_eur(item.get('price'))
                    if price is not None and price >= config['filters']['max_price_eur']:
                        continue
                if details >= (2 if smoke else config['http']['max_details']):
                    result.warnings.append('Detail limit reached; coverage incomplete')
                    result.status = 'partial' if parsed else 'failed'
                    return result
                details += 1
                try:
                    direct = urljoin(BASE, item['url'])
                    result.listings.append(parse_listing(client.get(direct), direct))
                    parsed += 1
                except AccessError:
                    raise
                except (KeyError, ValueError, TypeError, IndexError):
                    result.warnings.append('Imobiliare listing schema invalid; one detail skipped')
            if page >= meta['lastPage']:
                # Search can itself impose a result window smaller than totalCount.
                if meta['lastPage'] * meta['perPage'] < meta['totalCount']:
                    result.warnings.append('Website result window truncates total listings')
                result.status = ('failed' if result.examined and not parsed else 'partial') if result.warnings else 'success'
                return result
        result.warnings.append('Page limit reached; coverage incomplete')
        result.status = 'partial' if parsed else 'failed'
    except Exception as exc:
        result.status = 'partial' if parsed else 'failed'
        result.warnings.append(str(exc) if isinstance(exc, (AccessError, ValueError)) else type(exc).__name__ + ': source request/parser failed')
    finally:
        client.close()
    return result
