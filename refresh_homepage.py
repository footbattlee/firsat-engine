"""Refresh only homepage candidates, with strict visible purchase-price checks.
Default is preview. --apply writes homepage snapshots, never social queues/offers.
"""
import argparse
import asyncio
import json
import os
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin, urlsplit
import requests
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / '.env')
BASE = os.getenv('SUPABASE_URL', 'https://cmexmobjpeavlppmffqi.supabase.co').rstrip('/')
KEY = os.getenv('SUPABASE_SERVICE_ROLE_KEY', '').strip()
DOMAINS = {'amazon':'amazon.com.tr','trendyol':'trendyol.com','hepsiburada':'hepsiburada.com',
           'n11':'n11.com','mediamarkt':'mediamarkt.com.tr','vatan':'vatanbilgisayar.com'}
HEADERS = {'User-Agent':'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/152.0.0.0 Safari/537.36',
           'Accept-Language':'tr-TR,tr;q=0.9','Accept':'text/html,application/xhtml+xml'}
def utcnow():
    return datetime.now(timezone.utc).isoformat()
def allowed(url, slug):
    try:
        u=urlsplit(url); domain=DOMAINS.get(slug)
        return bool(domain and u.scheme=='https' and not u.username and not u.password and
                    u.port in (None,443) and (u.hostname==domain or (u.hostname or '').endswith('.'+domain)))
    except ValueError:
        return False
def api(table, params=None, row=None):
    if not KEY:
        raise RuntimeError('SUPABASE_SERVICE_ROLE_KEY missing')
    headers={'apikey':KEY,'Authorization':'Bearer '+KEY}
    if row is not None:
        headers['Prefer']='resolution=merge-duplicates,return=minimal'
        r=requests.post(BASE+'/rest/v1/'+table,headers=headers,params=params,json=row,timeout=30)
    else:
        r=requests.get(BASE+'/rest/v1/'+table,headers=headers,params=params,timeout=30)
    r.raise_for_status()
    return r.json() if r.content else None
def all_rows(table, params=None):
    rows=[]; offset=0
    while True:
        page=api(table,dict(params or {},limit=500,offset=offset))
        rows.extend(page)
        if len(page)<500:
            return rows
        offset+=500

def in_rows(table, values, select='*', extra=None):
    if not values:
        return []
    result=[]
    ids=sorted(set(values))
    for start in range(0,len(ids),80):
        result.extend(all_rows(table,dict({'select':select,'id':'in.('+','.join(ids[start:start+80])+')'},**(extra or {}))))
    return result
def find_node():
    candidates=[os.getenv('HOMEPAGE_NODE',''),shutil.which('node'),
        str(Path.home()/'.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node.exe')]
    return next((x for x in candidates if x and Path(x).is_file()),None)
def parse_html(node, html, url, final_url, slug):
    if len(html)>2500000:
        raise ValueError('page-too-large')
    p=subprocess.run([node,str(ROOT/'homepage_price_parse.mjs')],input=json.dumps(
        {'html':html,'url':url,'finalUrl':final_url,'slug':slug}),capture_output=True,text=True,
        encoding='utf-8',timeout=20)
    try:
        result=json.loads(p.stdout)
    except ValueError:
        raise ValueError('price-parser-unavailable')
    if result.get('error'):
        raise ValueError(result['error'])
    return result
def request_price(node, url, slug):
    current=url
    with requests.Session() as session:
        session.headers.update(HEADERS)
        session.cookies.set('i18n-prefs','TRY',domain='.amazon.com.tr')
        for _ in range(4):
            if not allowed(current,slug):
                raise ValueError('product-domain-unverified')
            r=session.get(current,timeout=12,allow_redirects=False)
            if r.is_redirect:
                current=urljoin(current,r.headers['Location']);continue
            if not r.ok:
                raise ValueError('store-http-'+str(r.status_code))
            return parse_html(node,r.text,url,current,slug)
    raise ValueError('redirect-limit')
def pool(limit):
    candidates=all_rows('deal_candidates',{'select':'*','status':'eq.candidate','gap_percent':'gte.15',
        'and':'(gap_percent.lt.70)','order':'gap_percent.desc,id.asc'})
    manual=all_rows('homepage_manual_deals',{'select':'*','active':'eq.true','expires_at':'gt.'+utcnow(),'order':'id.asc'})
    ids=[o for c in candidates for o in [c['cheapest_offer_id'],c['competitor_offer_id']] if o]
    offers={o['id']:o for o in in_rows('offers',ids)}
    merchants={m['id']:m for m in api('merchants',{'select':'id,slug,name'})}
    canonical_ids=[c['canonical_product_id'] for c in candidates]
    products={p['id']:p for p in in_rows('canonical_products',canonical_ids,extra={'active':'eq.true'})}
    variants={v['id']:v for v in in_rows('product_variants',[o['product_variant_id'] for o in offers.values() if o.get('product_variant_id')],extra={'active':'eq.true'})}
    matches=[]
    canonical_ids=sorted(set(canonical_ids))
    for start in range(0,len(canonical_ids),80):
        matches.extend(all_rows('product_matches',{'select':'canonical_product_id,product_id','status':'eq.approved',
            'canonical_product_id':'in.('+','.join(canonical_ids[start:start+80])+')','order':'id.asc'}))
    approved={(m['canonical_product_id'],m['product_id']) for m in matches}
    tasks=[]
    for c in candidates:
        cheap=offers.get(c['cheapest_offer_id']); rival=offers.get(c['competitor_offer_id']); p=products.get(c['canonical_product_id'])
        cv=variants.get((cheap or {}).get('product_variant_id')); rv=variants.get((rival or {}).get('product_variant_id'))
        valid=bool(cv and rv and (c['canonical_product_id'],cv['product_id']) in approved and
                   (c['canonical_product_id'],rv['product_id']) in approved and
                   not (cv.get('gtin') and rv.get('gtin') and cv['gtin']!=rv['gtin']))
        tasks.append({'id':c['id'],'candidate_id':c['id'],'manual_id':None,'cheap':cheap,'rival':rival,
                      'product':p,'valid':valid,'expires_at':None})
    for d in manual:
        m=next((m for m in merchants.values() if m['slug']==d['merchant_slug']),None)
        tasks.append({'id':'manual-'+d['id'],'candidate_id':None,'manual_id':d['id'],
                      'cheap':dict(d,merchant_id=(m or {}).get('id')),'rival':None,'product':d,
                      'valid':True,'expires_at':d['expires_at']})
    previous=all_rows('homepage_deals',{'select':'id,attempted_at','order':'id.asc'})
    last={p['id']:p['attempted_at'] for p in previous}
    tasks.sort(key=lambda t:last.get(t['id'],''))
    return (tasks[:limit] if limit else tasks),merchants
async def refresh(args):
    node=find_node()
    if not node:
        raise RuntimeError('Node runtime missing; set HOMEPAGE_NODE')
    tasks,merchants=await asyncio.to_thread(pool,args.limit)
    from playwright.async_api import async_playwright
    started=time.monotonic()
    locks={slug:asyncio.Lock() for slug in DOMAINS}
    cache={}; results=[]
    async with async_playwright() as pw:
        browser=await pw.chromium.launch(headless=True)
        context=await browser.new_context(locale='tr-TR',user_agent=HEADERS['User-Agent'])
        async def restrict(route):
            request=route.request
            if request.resource_type in ('image','font','media'):
                await route.abort()
            elif request.is_navigation_request() and request.frame.parent_frame is None and not any(allowed(request.url,s) for s in DOMAINS):
                await route.abort()
            else:
                await route.continue_()
        await context.route('**/*',restrict)
        async def check(url,slug):
            if not allowed(url,slug):
                raise ValueError('product-domain-unverified')
            async with locks[slug]:
                try:
                    return await asyncio.to_thread(request_price,node,url,slug)
                except Exception as initial:
                    if time.monotonic()-started>args.budget:
                        raise ValueError('check-timeout')
                    page=await context.new_page()
                    try:
                        response=await page.goto(url,wait_until='domcontentloaded',timeout=18000)
                        if not response or response.status>=400:
                            raise ValueError('store-http-'+str(response.status if response else 500))
                        await page.wait_for_timeout(1500)
                        html=await page.content()
                        return await asyncio.to_thread(parse_html,node,html,url,page.url,slug)
                    except ValueError:
                        raise
                    except Exception:
                        raise ValueError(str(initial)[:100])
                    finally:
                        await page.close()
        async def live(offer,slug):
            url=offer['product_url']; key=(url,slug)
            async def observed():
                started_at=utcnow()
                try:
                    result=await check(url,slug)
                    if args.apply and offer.get('id'):
                        await asyncio.to_thread(api,'rpc/website_save_offer_check',row={'p_offer_id':offer['id'],'p_product_url':url,'p_observed_at':started_at,'p_price':result['price']})
                    return result
                except Exception as e:
                    if args.apply and offer.get('id'):
                        await asyncio.to_thread(api,'rpc/website_save_offer_check',row={'p_offer_id':offer['id'],'p_product_url':url,'p_observed_at':started_at,'p_error':str(e)[:120]})
                    raise
            if key not in cache: cache[key]=asyncio.create_task(observed())
            return await cache[key]
        sem=asyncio.Semaphore(3)
        async def one(t):
            async with sem:
                if time.monotonic()-started>args.budget:
                    return
                cheap=t['cheap']; p=t['product']; m=merchants.get((cheap or {}).get('merchant_id'))
                if not cheap or not p or not m:
                    results.append({'id':t['id'],'status':'missing-data'});return
                row={k:t[k] for k in ('id','candidate_id','manual_id','expires_at')}
                row.update(offer_id=None if t['manual_id'] else cheap['id'],title=p['title'],
                    brand=p.get('brand') or '',merchant_slug=m['slug'],merchant_name=m['name'],
                    product_url=cheap['product_url'],affiliate_url=cheap.get('affiliate_url'),
                    image_url=cheap.get('image_url'),attempted_at=utcnow(),price=None,competitor_price=None,
                    competitor_name=None,status='unverified',checked_at=None,price_checked_at=None,error_code=None)
                try:
                    if not t['valid']:
                        raise ValueError('match-no-longer-approved')
                    errors=[]; current=None; other=None
                    try:
                        current=await live(cheap,m['slug'])
                        row.update(price=current['price'],title=current['title'],price_checked_at=utcnow())
                    except Exception as e: errors.append(str(e))
                    if t['rival']:
                        rival=t['rival']; rm=merchants.get(rival['merchant_id'])
                        if not rm or rm['id']==m['id']: errors.append('competitor-unverified')
                        else:
                            try:
                                other=await live(rival,rm['slug'])
                                row.update(competitor_price=other['price'],competitor_name=rm['name'])
                            except Exception as e: errors.append(str(e))
                    if current and (not t['rival'] or other):
                        gap=(other['price']-current['price'])/other['price']*100 if other else 15
                        row['status']='verified' if 15<=gap<70 else 'unverified'
                        row['error_code']=None if row['status']=='verified' else 'advantage-lost'
                        row['checked_at']=utcnow()
                    elif errors: row['error_code']=errors[0][:120]
                except Exception as e:
                    row['error_code']=str(e)[:120] or 'check-failed'
                if args.apply:
                    await asyncio.to_thread(api,'homepage_deals',{'on_conflict':'id'},row)
                result={'id':t['id'],'status':row['status'],'price':row['price'],'price_verified':bool(row['price_checked_at']),'error':row['error_code']}
                results.append(result)
                print('HOMEPAGE | '+json.dumps(result,ensure_ascii=True),flush=True)
        try:
            await asyncio.wait_for(asyncio.gather(*(one(t) for t in tasks)),timeout=args.budget+60)
        finally:
            await browser.close()
    summary={'time':utcnow(),'mode':'apply' if args.apply else 'preview','checked':len(results),
             'purchase_prices_verified':sum(bool(r.get('price_verified')) for r in results),
             'comparisons_verified':sum(r['status']=='verified' for r in results),
             'seconds':round(time.monotonic()-started,1),'results':results}
    print('HOMEPAGE SUMMARY | '+json.dumps({k:v for k,v in summary.items() if k!='results'}),flush=True)
    (ROOT/'logs').mkdir(exist_ok=True)
    (ROOT/'logs/homepage-refresh-last.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
    return summary
def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--apply',action='store_true')
    parser.add_argument('--limit',type=int,default=0)
    parser.add_argument('--budget',type=int,default=1100)
    args=parser.parse_args();args.limit=max(0,args.limit)
    # Scheduled Task also ignores overlaps; file lock protects manual invocation.
    (ROOT/'logs').mkdir(exist_ok=True)
    lock=(ROOT/'logs/homepage-refresh.lock').open('a+b')
    if os.name=='nt':
        import msvcrt
        try:
            lock.seek(0);lock.write(b'0');lock.flush();lock.seek(0);msvcrt.locking(lock.fileno(),msvcrt.LK_NBLCK,1)
        except OSError:
            print('HOMEPAGE | already running',flush=True);return
    try:
        asyncio.run(refresh(args))
    finally:
        lock.close()
if __name__=='__main__':
    main()
