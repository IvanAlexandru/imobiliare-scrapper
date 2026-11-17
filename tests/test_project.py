
from dataclasses import replace
from pathlib import Path
import json
import httpx
import pytest
from apartment_scraper.config import load
from apartment_scraper.filters import partition, eur, usable_area, numeric
from apartment_scraper.deduplication import deduplicate, possible_duplicates
from apartment_scraper.models import SourceResult
from apartment_scraper.reporting import render
from apartment_scraper.scrapers import storia_ro, imobiliare_ro
from apartment_scraper.http import Client, AccessError
from apartment_scraper.email_sender import send

FIX = Path(__file__).parent / "fixtures"
@pytest.fixture
def listing():
    return storia_ro.parse_listing((FIX / "storia-detail.html").read_text())
@pytest.fixture
def config():
    return load()

def test_polygon_and_boundary(listing, config):
    f = config["filters"]
    assert partition([listing], f) == ([listing], [])
    lon, lat = f["polygon"]["coordinates"][0][0]
    edge = replace(listing, longitude=lon, latitude=lat)
    assert partition([edge], f)[0] == [edge]
    assert partition([replace(listing, longitude=25)], f) == ([], [])

@pytest.mark.parametrize("change", [{"price_eur":300000},{"price_eur":300001},{"price_eur":-1},{"price_eur":None},{"year":2015},{"year":None},{"rooms":2},{"rooms":5},{"price_eur":float("nan")},{"year":"broken"},{"id":""},{"url":123},{"title":None},{"transaction":"RENT"},{"city":"Ilfov"},{"property_type":"HOUSE"}])
def test_invalid_filters(listing, config, change):
    assert partition([replace(listing, **change)], config["filters"]) == ([], [])

@pytest.mark.parametrize("change", [{"year":2016},{"rooms":4},{"price_eur":299999.99}])
def test_accepted_filters(listing, config, change):
    assert len(partition([replace(listing, **change)], config["filters"])[0]) == 1

@pytest.mark.parametrize("change", [{"latitude":None},{"latitude":float("nan")},{"latitude":100},{"precise_location":False}])
def test_uncertain(listing, config, change):
    assert len(partition([replace(listing, **change)], config["filters"])[1]) == 1

def test_normalization():
    assert eur("240 000", "EUR") == 240000
    assert eur("240000", "RON") is None
    assert eur("negotiable", "EUR") is None
    assert numeric("NaN") is None
    assert usable_area("80,5") == 80.5
    assert usable_area("100", "built") is None
    assert usable_area("20", "terrace") is None
    assert usable_area(-1) is None

def test_sort(listing, config):
    b = replace(listing, id="b", price_eur=200000)
    assert partition([listing,b],config["filters"])[0] == [b,listing]
    assert listing.price_m2 == 3000

def test_duplicates(listing):
    assert deduplicate([listing, listing]) == [listing]
    other = replace(listing, source="imobiliare_ro")
    assert possible_duplicates([listing,other]) == [(listing,other)]
    assert len(deduplicate([listing,other])) == 2
    assert not possible_duplicates([listing, replace(other,address="Another Street 12")])
    assert not possible_duplicates([replace(listing,address="District"),replace(other,address="District")])

def test_parsers(listing):
    assert listing.rooms == 3 and listing.year == 2020 and listing.usable_area == 80
    assert listing.precise_location and listing.seller == "agency"
    items, p = storia_ro.search_page((FIX/'storia-search.html').read_text())
    assert items[0]['id'] == 123 and p['totalPages'] == 2
    with pytest.raises(ValueError):
        storia_ro.payload((FIX/'imobiliare-blocked.html').read_text())
    with pytest.raises(KeyError):
        storia_ro.search_page('<script id="__NEXT_DATA__">{"props":{"pageProps":{}}}</script>')

def mock_client(monkeypatch, handler):
    original = httpx.Client
    monkeypatch.setattr('apartment_scraper.http.httpx.Client', lambda **kw: original(transport=httpx.MockTransport(handler), **kw))
    monkeypatch.setattr('apartment_scraper.http.time.sleep', lambda _: None)

def test_pagination(monkeypatch, config):
    urls = []
    def handler(req):
        urls.append(str(req.url))
        if req.url.path == '/robots.txt':
            return httpx.Response(200,text='User-agent: *\nAllow: /')
        if '/rezultate/' in req.url.path:
            t = (FIX/'storia-search.html').read_text()
            if req.url.params['page'] == '2':
                t = t.replace('"currentPage": 1','"currentPage": 2').replace('123','124')
            return httpx.Response(200,text=t)
        return httpx.Response(200,text=(FIX/'storia-detail.html').read_text())
    mock_client(monkeypatch, handler)
    result = storia_ro.scan(config)
    assert result.status == 'success' and result.pages == 2 and result.examined == 2
    assert any('page=2' in u for u in urls)

def test_pagination_stalled(monkeypatch, config):
    def handler(req):
        if req.url.path == '/robots.txt': return httpx.Response(200,text='User-agent: *\nAllow: /')
        return httpx.Response(200,text=(FIX/('storia-search.html' if '/rezultate/' in req.url.path else 'storia-detail.html')).read_text())
    mock_client(monkeypatch,handler)
    result = storia_ro.scan(config)
    assert result.status == 'partial' and any('Pagination' in w for w in result.warnings)

@pytest.mark.parametrize('status', [403,429,401])
def test_access_block(monkeypatch, config, status):
    mock_client(monkeypatch,lambda r:httpx.Response(status))
    result = storia_ro.scan(config)
    assert result.status == 'failed' and result.examined == 0

def test_robots_and_redirect(monkeypatch, config):
    mock_client(monkeypatch,lambda r:httpx.Response(200,text='User-agent: *\nDisallow: /'))
    c = Client('www.storia.ro',config['http'])
    with pytest.raises(AccessError): c.get(storia_ro.SEARCH)
    with pytest.raises(AccessError): c.raw('https://evil.example/')
    c.close()

def test_report(listing):
    result = SourceResult('storia_ro',status='partial',examined=1,listings=[listing],warnings=['<incomplete>'])
    subject, html, text = render([result],[listing],[listing],'Apartments')
    assert '[PARTIAL]' in subject and 'Location unverified' in html
    assert '&lt;test&gt;' in html and '<test>' not in html
    assert '&lt;incomplete&gt;' in html and listing.url in html and listing.url in text
    assert 'Confirmed matches: 1' in text and 'Usable m²' in html
    assert 'No confirmed matches' in render([result],[],[],'Apartments')[2]

def test_email(monkeypatch):
    for key in ['RESEND_API_KEY','REPORT_EMAIL_FROM','REPORT_EMAIL_TO']:
        monkeypatch.setenv(key,'placeholder')
    calls=[]
    def post(url, **kw):
        calls.append(kw)
        return httpx.Response(200,json={'id':'email-id'})
    monkeypatch.setattr('apartment_scraper.email_sender.httpx.post',post)
    send('subject','<p>html</p>','text')
    assert len(calls)==1 and calls[0]['json']['text']=='text' and calls[0]['json']['html']=='<p>html</p>'
    monkeypatch.setattr('apartment_scraper.email_sender.httpx.post',lambda *a,**k:httpx.Response(403))
    with pytest.raises(RuntimeError): send('subject','html','text')
    monkeypatch.delenv('RESEND_API_KEY')
    with pytest.raises(RuntimeError): send('subject','html','text')

def test_imobiliare_blocked(monkeypatch,config):
    mock_client(monkeypatch,lambda r:httpx.Response(403,text=(FIX/'imobiliare-blocked.html').read_text()))
    result=imobiliare_ro.scan(config)
    assert result.status=='failed' and '403' in result.warnings[0]

def test_network_backoff(monkeypatch,config):
    calls=[]
    def handler(req):
        calls.append(req)
        raise httpx.ConnectError('offline')
    mock_client(monkeypatch,handler)
    result=storia_ro.scan(config)
    assert result.status=='failed' and len(calls)==config['http']['retries']

def test_main_exit_and_delivery(monkeypatch,config):
    from apartment_scraper import main
    monkeypatch.setattr(main,'load',lambda _:config)
    monkeypatch.setattr(main.storia_ro,'scan',lambda *a,**k:SourceResult('storia_ro'))
    monkeypatch.setattr(main.imobiliare_ro,'scan',lambda *a,**k:SourceResult('imobiliare_ro'))
    sent=[]
    monkeypatch.setattr(main,'send',lambda *args:sent.append(args))
    monkeypatch.setattr('sys.argv',['scraper'])
    with pytest.raises(SystemExit) as e: main.main()
    assert e.value.code==1 and len(sent)==1 and '[FAILED]' in sent[0][0]
    monkeypatch.setattr(main.storia_ro,'scan',lambda *a,**k:SourceResult('storia_ro',status='success'))
    with pytest.raises(SystemExit) as e: main.main()
    assert e.value.code==0 and '[PARTIAL]' in sent[-1][0]
    def fail(*args): raise RuntimeError('Email delivery failed')
    monkeypatch.setattr(main,'send',fail)
    with pytest.raises(SystemExit) as e: main.main()
    assert e.value.code==1


def test_imobiliare_parser():
    x=imobiliare_ro.parse_listing((FIX/'imobiliare-detail.html').read_text(),'https://www.imobiliare.ro/oferta/synthetic-321')
    assert x.price_eur==240000 and x.rooms==3 and x.year==2020 and x.usable_area==80.5
    assert x.total_floors==8 and x.precise_location and x.transaction=='SELL'
    assert imobiliare_ro.displayed_eur('298.870 €')==298870
    assert imobiliare_ro.displayed_eur('La cerere') is None
    with pytest.raises(ValueError): imobiliare_ro.payload((FIX/'imobiliare-blocked.html').read_text())

def test_imobiliare_pagination(monkeypatch,config):
    def handler(req):
        if req.url.path=='/robots.txt':return httpx.Response(200,text='User-agent: *\nAllow: /')
        if '/oferta/' in req.url.path:return httpx.Response(200,text=(FIX/'imobiliare-detail.html').read_text())
        t=(FIX/'imobiliare-search.html').read_text()
        if req.url.params.get('page')=='2':t=t.replace('currentPage&quot;: 1','currentPage&quot;: 2').replace('321','322')
        return httpx.Response(200,text=t)
    mock_client(monkeypatch,handler)
    r=imobiliare_ro.scan(config)
    assert r.status=='success' and r.pages==2 and r.examined==2

def test_robots_wildcards_and_allow_precedence(monkeypatch,config):
    policy='User-agent: *\nDisallow: /*page=*\nAllow: /*?page=2$\nDisallow: /api/'
    requested=[]
    def handler(req):
        requested.append(str(req.url))
        return httpx.Response(200,text=policy if req.url.path=='/robots.txt' else '<html>permitted</html>')
    mock_client(monkeypatch,handler)
    c=Client('www.imobiliare.ro',config['http'])
    assert c.get(imobiliare_ro.SEARCH+'?page=2')
    with pytest.raises(AccessError):c.get(imobiliare_ro.SEARCH+'?page=11')
    with pytest.raises(AccessError):c.get('https://www.imobiliare.ro/api/private')
    assert len(requested)==2
    c.close()

def test_robots_groups_normalization_and_delays():
    from apartment_scraper.robots import Robots
    policy='User-agent: *\nDisallow: /\nUser-agent: BucharestApartmentMonitor\nCrawl-delay: 3\nAllow: /\nDisallow: /private/*\nAllow: /private/public$'
    r=Robots(policy,'BucharestApartmentMonitor/1.0')
    assert r.delay==3 and r.allows('https://example.com/index')
    assert not r.allows('https://example.com/private/secret')
    assert r.allows('https://example.com/private/public')
    assert not r.allows('https://example.com/private/public/more')
    assert not Robots(policy,'OtherBot').allows('https://example.com/index')
    assert not Robots('User-agent: *\nDisallow: /secret','Bot').allows('https://example.com/%73ecret')
